"""
UF Stock Assistant — Trading Executor (QuantDinger parity)

Ported from QuantDinger's daemon-thread strategy runner.
Each strategy runs in a dedicated daemon thread.  The executor manages
lifecycle (start / stop / stop-all), the per-strategy tick loop,
signal processing, server-side risk controls, and position state
management backed by SQLAlchemy + SQLite.

Key enhancements over original UF version:
  - 8-way signals (open/close/add/reduce × long/short)
  - In-memory + DB signal dedup
  - PriceCache integration
  - Bot mode (per-tick on_bar evaluation)
  - Indicator realtime recompute between candle boundaries
  - Script runtime state persistence
  - Fee rate caching
  - Pending-order enqueue with DB-level dedup
  - execution_mode support (signal=local sim, live=enqueue)
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Callable

import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.safe_exec import validate_code_safety
from app.strategies.indicator_params import IndicatorParamsParser, StrategyConfigParser
from app.strategies.models import (
    BacktestTrade,
    PendingOrder,
    StrategyFeeRate,
    StrategyLog,
    StrategyModel,
    StrategyPosition,
    StrategyTrade,
)
from app.strategies.price_cache import PriceCache
from app.strategies.script_runtime import (
    ScriptBar,
    ScriptPosition,
    StrategyScriptContext,
    compile_strategy_script_handlers,
)

logger = get_logger("app.strategies.trading_executor")

# ── Database session (shared engine for strategies DB) ─────────────────────

_db_engine = None
_db_session_factory = None


def _get_db_engine():
    global _db_engine
    if _db_engine is None:
        _db_engine = create_engine(get_settings().database.url, echo=False, future=True)
    return _db_engine


def _get_db_session_factory():
    global _db_session_factory
    if _db_session_factory is None:
        _db_session_factory = sessionmaker(bind=_get_db_engine())
    return _db_session_factory


def get_strategy_db_session() -> Session:
    """Create a new SQLAlchemy session for the strategies database."""
    return _get_db_session_factory()()


def init_strategy_tables() -> None:
    """Create all strategy-related tables."""
    from app.strategies.models import Base

    Base.metadata.create_all(_get_db_engine())
    logger.info("strategy_tables_initialized")


def append_strategy_log(strategy_id: str, level: str, message: str) -> None:
    """Write a strategy log entry to the database."""
    session = get_strategy_db_session()
    try:
        session.add(StrategyLog(
            strategy_id=str(strategy_id),
            level=level.upper(),
            message=str(message or ""),
        ))
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.warning("append_strategy_log_failed", strategy_id=strategy_id, error=str(exc))
    finally:
        session.close()


# ── Constants ──────────────────────────────────────────────────────────────


class PositionState(StrEnum):
    """Position state machine values."""
    FLAT = "flat"
    LONG = "long"
    SHORT = "short"


class NormalizedSignal(StrEnum):
    """Eight-way signal types after normalisation."""
    OPEN_LONG = "open_long"
    CLOSE_LONG = "close_long"
    OPEN_SHORT = "open_short"
    CLOSE_SHORT = "close_short"
    ADD_LONG = "add_long"
    ADD_SHORT = "add_short"
    REDUCE_LONG = "reduce_long"
    REDUCE_SHORT = "reduce_short"


class TriggerMode(StrEnum):
    """How a signal is triggered."""
    PRICE = "price"         # trigger when price crosses entry level
    IMMEDIATE = "immediate" # execute on next tick


# Timeframe string -> seconds mapping
_TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "1H": 3600, "2h": 7200, "4h": 14400, "4H": 14400,
    "6h": 21600, "8h": 28800, "12h": 43200,
    "1D": 86400, "1d": 86400, "daily": 86400,
    "1W": 604800, "1w": 604800, "weekly": 604800,
    "1M": 2592000, "monthly": 2592000,
}


def _timeframe_to_seconds(timeframe: str) -> int:
    """Convert a timeframe string to seconds, defaulting to 86400 (1 day)."""
    return _TIMEFRAME_SECONDS.get(timeframe, 86400)


def _timeframe_to_akshare_period(timeframe: str) -> str:
    """Map a timeframe string to the AKShare period name."""
    tf = timeframe.lower()
    if tf in ("1w", "weekly"):
        return "weekly"
    if tf in ("1m", "monthly"):
        return "monthly"
    return "daily"


def _timeframe_to_ccxt(timeframe: str) -> str:
    """Map a timeframe string to CCXT notation."""
    mapping = {
        "1D": "1d", "1d": "1d", "daily": "1d",
        "1W": "1w", "1w": "1w", "weekly": "1w",
        "1M": "1M", "monthly": "1M",
        "1h": "1h", "1H": "1h", "2h": "2h", "4h": "4h", "4H": "4h",
        "6h": "6h", "8h": "8h", "12h": "12h",
        "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    }
    return mapping.get(timeframe, "1d")


# Tick interval constants
DEFAULT_TICK_INTERVAL = 10  # seconds between loop iterations
KLINE_LIMIT = 500           # number of bars to fetch
MAX_THREADS = 64             # default max strategy threads


# ── Signal container ───────────────────────────────────────────────────────


@dataclass
class NormalizedSignalEvent:
    """A normalised signal ready for processing."""
    signal_type: NormalizedSignal
    price: float
    timestamp: float
    source: str = ""            # "indicator" / "script" / "risk_control"
    trigger_mode: TriggerMode = TriggerMode.IMMEDIATE
    trigger_price: float | None = None
    position_size: float | None = None
    expiry_seconds: float = 0.0


# ── TradingExecutor ────────────────────────────────────────────────────────


class TradingExecutor:
    """
    Manages daemon threads that run live strategy loops.

    Each strategy is started via :meth:`start_strategy` which spawns a
    daemon thread executing :meth:`_run_strategy_loop`.  Stop signals
    propagate through :class:`threading.Event` objects stored per
    strategy.
    """

    def __init__(self) -> None:
        self.running_strategies: dict[str, threading.Thread] = {}
        self._stop_flags: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self.max_threads: int = MAX_THREADS
        self._last_start_failure: str = ""

        # Price cache (shared across strategies, reduces redundant API calls).
        self._price_cache = PriceCache(default_ttl=10.0)

        # In-memory per-strategy signal dedup: {strategy_id: {dedup_key: expiry_ts}}
        self._signal_dedup: dict[str, dict[str, float]] = {}
        self._signal_dedup_lock = threading.Lock()

        # Per-strategy fee rate cache: {strategy_id: {maker, taker} or None}
        self._exchange_fee_cache: dict[str, dict[str, float] | None] = {}
        self._exchange_fee_cache_lock = threading.Lock()

    # ── Public lifecycle API ───────────────────────────────────────────────

    def start_strategy(self, strategy_id: str) -> bool:
        """
        Start a strategy in a daemon thread.

        Returns ``True`` if the thread was spawned, ``False`` if the
        strategy is already running or the thread limit is reached.
        """
        with self._lock:
            self._last_start_failure = ""

            # Clean up dead threads.
            stale = [sid for sid, th in self.running_strategies.items() if not th.is_alive()]
            for sid in stale:
                self._cleanup_strategy(sid)

            if strategy_id in self.running_strategies:
                self._last_start_failure = "Strategy thread already running"
                logger.warning("strategy_already_running", strategy_id=strategy_id)
                return False

            if len(self.running_strategies) >= self.max_threads:
                msg = f"Thread limit reached ({self.max_threads})"
                self._last_start_failure = msg
                logger.error("start_strategy_failed", strategy_id=strategy_id, reason=msg)
                return False

            # Validate strategy exists in DB.
            session = get_strategy_db_session()
            try:
                strategy = session.query(StrategyModel).filter_by(id=str(strategy_id)).first()
                if strategy is None:
                    msg = f"Strategy {strategy_id} not found in database"
                    self._last_start_failure = msg
                    logger.error("start_strategy_failed", strategy_id=strategy_id, reason=msg)
                    return False
                strategy.status = "running"
                strategy.updated_at = datetime.now(timezone.utc)
                session.commit()
            except Exception as exc:
                session.rollback()
                self._last_start_failure = f"DB error: {exc}"
                logger.error("start_strategy_db_error", strategy_id=strategy_id, error=str(exc))
                return False
            finally:
                session.close()

        stop_event = threading.Event()
        self._stop_flags[strategy_id] = stop_event

        thread = threading.Thread(
            target=self._run_strategy_loop,
            args=(strategy_id, stop_event),
            name=f"strategy-{strategy_id}",
            daemon=True,
        )
        self.running_strategies[strategy_id] = thread
        thread.start()

        append_strategy_log(strategy_id, "INFO", "Strategy execution thread started")
        logger.info("strategy_started", strategy_id=strategy_id)
        return True

    def stop_strategy(self, strategy_id: str) -> bool:
        """
        Stop a running strategy.

        Sets the stop flag and waits up to 15 seconds for the thread to
        finish.  Returns ``True`` if the strategy was stopped.
        """
        if strategy_id not in self._stop_flags:
            logger.warning("strategy_not_running", strategy_id=strategy_id)
            return False

        self._stop_flags[strategy_id].set()

        thread = self.running_strategies.get(strategy_id)
        if thread is not None and thread.is_alive():
            thread.join(timeout=15)
            if thread.is_alive():
                logger.warning("strategy_thread_still_alive", strategy_id=strategy_id)

        self._cleanup_strategy(strategy_id)
        self._update_strategy_status(strategy_id, "stopped")
        # Clean up caches for this strategy.
        with self._exchange_fee_cache_lock:
            self._exchange_fee_cache.pop(strategy_id, None)
        with self._signal_dedup_lock:
            self._signal_dedup.pop(strategy_id, None)

        append_strategy_log(strategy_id, "INFO", "Strategy stopped")
        logger.info("strategy_stopped", strategy_id=strategy_id)
        return True

    def get_running_strategies(self) -> list[str]:
        """Return a list of IDs for strategies whose threads are alive."""
        alive: list[str] = []
        for sid, thread in list(self.running_strategies.items()):
            if thread.is_alive():
                alive.append(sid)
            else:
                self._cleanup_strategy(sid)
        return alive

    def stop_all(self) -> None:
        """Stop every running strategy."""
        for sid in list(self.running_strategies.keys()):
            self.stop_strategy(sid)
        logger.info("all_strategies_stopped")

    def get_last_start_failure(self) -> str:
        """Return the reason for the most recent start failure."""
        return self._last_start_failure

    # ── Internal helpers ───────────────────────────────────────────────────

    def _cleanup_strategy(self, strategy_id: str) -> None:
        """Remove bookkeeping entries for a strategy."""
        self.running_strategies.pop(strategy_id, None)
        self._stop_flags.pop(strategy_id, None)

    def _update_strategy_status(self, strategy_id: str, status: str) -> None:
        """Write the ``status`` column of a strategy row."""
        session = get_strategy_db_session()
        try:
            strategy = session.query(StrategyModel).filter_by(id=str(strategy_id)).first()
            if strategy is not None:
                strategy.status = status
                strategy.updated_at = datetime.now(timezone.utc)
                session.commit()
        except Exception as exc:
            session.rollback()
            logger.error("update_status_failed", strategy_id=strategy_id, error=str(exc))
        finally:
            session.close()

    # ── QuantDinger utility methods ────────────────────────────────────────

    @staticmethod
    def _to_ratio(v: Any, default: float = 0.0) -> float:
        """Convert a value to a 0-1 ratio. Values > 1 are treated as percentages."""
        try:
            x = float(v) if v is not None else float(default)
        except (ValueError, TypeError):
            x = float(default or 0.0)
        if x > 1.0:
            x /= 100.0
        return max(0.0, min(1.0, x))

    @staticmethod
    def _build_cfg_from_trading_config(trading_config: dict[str, Any]) -> dict[str, Any]:
        """Build nested config dict from flat trading_config keys."""
        tc = trading_config or {}

        def _ratio(key: str, default: float = 0.0) -> float:
            val = tc.get(key, default)
            try:
                x = float(val) if val is not None else float(default)
            except (ValueError, TypeError):
                x = float(default)
            if x > 1.0:
                x /= 100.0
            return max(0.0, min(1.0, x))

        def _int(key: str, default: int = 0) -> int:
            try:
                return int(tc.get(key, default) or default)
            except (ValueError, TypeError):
                return default

        def _bool(key: str, default: bool = False) -> bool:
            return bool(tc.get(key, default))

        return {
            "risk": {
                "stopLossPct": _ratio("stop_loss_pct"),
                "takeProfitPct": _ratio("take_profit_pct"),
                "trailing": {
                    "enabled": _bool("trailing_enabled"),
                    "pct": _ratio("trailing_stop_pct"),
                    "activationPct": _ratio("trailing_activation_pct"),
                },
            },
            "position": {
                "entryPct": _ratio("entry_pct", 0.06),
            },
            "scale": {
                "trendAdd": {
                    "enabled": _bool("trend_add_enabled"),
                    "stepPct": _ratio("trend_add_step_pct"),
                    "sizePct": _ratio("trend_add_size_pct"),
                    "maxTimes": _int("trend_add_max_times"),
                },
                "dcaAdd": {
                    "enabled": _bool("dca_add_enabled"),
                    "stepPct": _ratio("dca_add_step_pct"),
                    "sizePct": _ratio("dca_add_size_pct"),
                    "maxTimes": _int("dca_add_max_times"),
                },
                "trendReduce": {
                    "enabled": _bool("trend_reduce_enabled"),
                    "stepPct": _ratio("trend_reduce_step_pct"),
                    "sizePct": _ratio("trend_reduce_size_pct"),
                    "maxTimes": _int("trend_reduce_max_times"),
                },
                "adverseReduce": {
                    "enabled": _bool("adverse_reduce_enabled"),
                    "stepPct": _ratio("adverse_reduce_step_pct"),
                    "sizePct": _ratio("adverse_reduce_size_pct"),
                    "maxTimes": _int("adverse_reduce_max_times"),
                },
            },
        }

    def _is_signal_allowed(self, state: str, signal_type: str) -> bool:
        """Strict position state machine: flat→open, long→add/reduce/close, short→add/reduce/close."""
        s = (state or "flat").lower()
        t = signal_type.lower()
        if s == "flat":
            return t in ("open_long", "open_short")
        if s == "long":
            return t in ("add_long", "reduce_long", "close_long")
        if s == "short":
            return t in ("add_short", "reduce_short", "close_short")
        return False

    @staticmethod
    def _signal_priority(signal_type: str) -> int:
        """Lower value = higher priority. Close before reduce before open before add."""
        t = signal_type.lower()
        if t.startswith("close"):
            return 0
        if t.startswith("reduce"):
            return 1
        if t.startswith("open"):
            return 2
        if t.startswith("add"):
            return 3
        return 99

    def _should_skip_signal_once_per_candle(
        self,
        strategy_id: str,
        symbol: str,
        signal_type: str,
        signal_ts: float,
        timeframe_seconds: int,
        now_ts: float | None = None,
    ) -> bool:
        """In-memory dedup: same strategy+symbol+signal_type+candle_ts → skip."""
        now = now_ts or time.time()
        tf = max(timeframe_seconds, 60)
        ttl_sec = max(tf * 2, 120)
        expiry = now + ttl_sec

        sym = symbol.upper().replace(":SETTLE", "")
        key = f"{strategy_id}|{sym}|{signal_type}|{int(signal_ts)}"

        with self._signal_dedup_lock:
            bucket = self._signal_dedup.setdefault(strategy_id, {})
            # Opportunistic cleanup: remove up to 512 expired keys.
            if len(bucket) > 512:
                expired = [k for k, exp in bucket.items() if now >= exp]
                for k in expired[:512]:
                    bucket.pop(k, None)
            if key in bucket and bucket[key] > now:
                return True
            bucket[key] = expiry
            return False

    def _update_dataframe_with_current_price(
        self,
        df: pd.DataFrame,
        current_price: float,
        timeframe: str,
    ) -> pd.DataFrame:
        """Update the last candle (or append a new one) with the current price."""
        if df is None or df.empty:
            return df

        tf_sec = _timeframe_to_seconds(timeframe)

        # The DataFrame uses a 'time' column, not an index.
        if "time" not in df.columns:
            return df

        last_time = df["time"].iloc[-1]
        # Convert to epoch seconds.
        try:
            if isinstance(last_time, pd.Timestamp):
                last_ts = float(last_time.timestamp())
            else:
                last_ts = float(pd.Timestamp(last_time).timestamp())
        except Exception:
            last_ts = 0.0

        now_ts = time.time()
        current_period_start = int(now_ts // tf_sec) * tf_sec

        if abs(last_ts - current_period_start) < tf_sec:
            # Same candle: update high/low/close in-place.
            idx = len(df) - 1
            df.at[idx, "close"] = current_price
            df.at[idx, "high"] = max(float(df.at[idx, "high"] or 0), current_price)
            df.at[idx, "low"] = min(float(df.at[idx, "low"] or float("inf")), current_price)
        elif current_period_start > last_ts:
            # New candle: append a row.
            new_row = pd.DataFrame([{
                "time": pd.to_datetime(current_period_start, unit="s", utc=True),
                "open": current_price,
                "high": current_price,
                "low": current_price,
                "close": current_price,
                "volume": 0.0,
            }])
            df = pd.concat([df, new_row], ignore_index=True)

        return df

    # ── Main strategy loop ─────────────────────────────────────────────────

    def _run_strategy_loop(self, strategy_id: str, stop_event: threading.Event) -> None:
        """
        Main loop for a single strategy thread.

        Loads the strategy from DB, fetches data, compiles code, and
        enters a tick loop.  Exceptions in the outer load phase are
        fatal; exceptions inside the tick loop are caught and logged so
        the thread survives transient failures.
        """
        logger.info("strategy_loop_starting", strategy_id=strategy_id)

        # ── 1. Load strategy from DB ───────────────────────────────────────
        session = get_strategy_db_session()
        try:
            strategy_model = session.query(StrategyModel).filter_by(id=str(strategy_id)).first()
            if strategy_model is None:
                logger.error("strategy_not_found", strategy_id=strategy_id)
                self._update_strategy_status(strategy_id, "error")
                return

            strategy_type = strategy_model.strategy_type or "indicator"
            symbol = strategy_model.symbol or ""
            timeframe = strategy_model.timeframe or "1D"
            market = strategy_model.market_type or "stock"
            code = strategy_model.strategy_code or ""
            initial_capital = float(strategy_model.initial_capital or 100000.0)
            leverage = int(strategy_model.leverage or 1)
            trade_direction = strategy_model.trade_direction or "long"
            commission = float(strategy_model.commission or 0.001)
            trading_config = strategy_model.trading_config or {}
            indicator_config = strategy_model.indicator_config or {}
            execution_mode = getattr(strategy_model, "execution_mode", None) or "signal"
            strategy_mode = getattr(strategy_model, "strategy_mode", None) or "signal"
            notification_config = getattr(strategy_model, "notification_config", None) or {}
            user_id = strategy_model.user_id or "default"
        finally:
            session.close()

        if not symbol:
            logger.error("strategy_no_symbol", strategy_id=strategy_id)
            self._update_strategy_status(strategy_id, "error")
            return

        # Parse @strategy annotations from code.
        strategy_config = StrategyConfigParser.parse(code)
        cfg = self._build_cfg_from_trading_config(trading_config)

        # ── 2. Fetch historical klines ─────────────────────────────────────
        try:
            kline_df = self._fetch_kline_data(market, symbol, timeframe, KLINE_LIMIT)
        except Exception as exc:
            logger.error("kline_fetch_failed", strategy_id=strategy_id, error=str(exc))
            self._update_strategy_status(strategy_id, "error")
            return

        if kline_df is None or kline_df.empty:
            logger.error("kline_empty", strategy_id=strategy_id)
            self._update_strategy_status(strategy_id, "error")
            return

        # ── 3. Compile strategy code ───────────────────────────────────────
        on_init: Callable | None = None
        on_bar: Callable | None = None
        indicator_exec_env: dict[str, Any] = {}
        is_script = strategy_type in ("script", "ScriptStrategy")

        if is_script:
            try:
                on_init, on_bar = compile_strategy_script_handlers(code)
            except Exception as exc:
                logger.error("script_compile_failed", strategy_id=strategy_id, error=str(exc))
                append_strategy_log(strategy_id, "ERROR", f"Script compile failed: {exc}")
                self._update_strategy_status(strategy_id, "error")
                return
        else:
            # Indicator strategy — validate and parse params.
            is_safe, err = validate_code_safety(code)
            if not is_safe:
                logger.error("indicator_code_unsafe", strategy_id=strategy_id, error=err)
                append_strategy_log(strategy_id, "ERROR", f"Unsafe indicator code: {err}")
                self._update_strategy_status(strategy_id, "error")
                return
            declared_params = IndicatorParamsParser.parse_params(code)
            merged_params = IndicatorParamsParser.merge_params(
                declared_params, {**indicator_config, **trading_config}
            )
            indicator_exec_env = self._build_indicator_env(
                code, kline_df.copy(), merged_params, user_id=user_id
            )
            if indicator_exec_env is None:
                self._update_strategy_status(strategy_id, "error")
                return

        # ── 4. Sync positions on startup ───────────────────────────────────
        position_state = self._load_position_state(strategy_id, symbol)

        # ── 5. Script context initialization ───────────────────────────────
        script_ctx: StrategyScriptContext | None = None
        last_closed_ts: pd.Timestamp | None = None
        if is_script and on_bar is not None:
            script_ctx, last_closed_ts = self._init_script_strategy_context(
                strategy_id, kline_df.copy(), trading_config, initial_capital,
            )
            # Hydrate from DB positions.
            self._hydrate_script_ctx_from_positions(
                script_ctx, strategy_id, symbol,
                initial_capital=initial_capital,
                current_price=float(kline_df.iloc[-1].get("close", 0) or 0),
            )
            if on_init is not None:
                try:
                    on_init(script_ctx)
                except Exception as exc:
                    logger.warning("on_init_error", strategy_id=strategy_id, error=str(exc))

        # ── 6. Tick loop ───────────────────────────────────────────────────
        tick_interval = DEFAULT_TICK_INTERVAL
        timeframe_sec = _timeframe_to_seconds(timeframe)
        signal_queue: deque[NormalizedSignalEvent] = deque(maxlen=200)
        last_candle_ts: float = 0.0
        trailing_high: float = 0.0
        trailing_low: float = float("inf")
        is_bot = strategy_mode == "bot"

        append_strategy_log(strategy_id, "INFO", f"Strategy loop started: {symbol} ({timeframe})")

        while not stop_event.is_set():
            try:
                # ── 6a. Get current price ──────────────────────────────────
                current_price = self._fetch_current_price(market, symbol)
                if current_price is None or current_price <= 0:
                    logger.warning("price_fetch_failed", strategy_id=strategy_id)
                    stop_event.wait(timeout=tick_interval)
                    continue

                now_ts = time.time()

                # ── 6b. Refresh klines on candle boundary ──────────────────
                candle_ts = self._candle_boundary_ts(now_ts, timeframe_sec)
                new_candle = False
                if candle_ts != last_candle_ts and candle_ts > 0:
                    last_candle_ts = candle_ts
                    new_candle = True
                    try:
                        new_df = self._fetch_kline_data(market, symbol, timeframe, KLINE_LIMIT)
                        if new_df is not None and not new_df.empty:
                            kline_df = new_df
                            # Rebuild indicator env on candle boundary.
                            if not is_script:
                                declared_params = IndicatorParamsParser.parse_params(code)
                                merged_params = IndicatorParamsParser.merge_params(
                                    declared_params, {**indicator_config, **trading_config}
                                )
                                indicator_exec_env = self._build_indicator_env(
                                    code, kline_df.copy(), merged_params, user_id=user_id
                                )
                            # Update script context bars.
                            if script_ctx is not None:
                                script_ctx._bars_df = kline_df.copy()
                                script_ctx.current_index = len(kline_df) - 1
                                script_ctx._orders.clear()
                    except Exception as exc:
                        logger.warning("kline_refresh_failed", strategy_id=strategy_id, error=str(exc))

                # ── 6c. Update df with current price (realtime) ────────────
                if not is_script and kline_df is not None:
                    kline_df = self._update_dataframe_with_current_price(
                        kline_df, current_price, timeframe,
                    )

                # ── 6d. Evaluate strategy and collect signals ──────────────
                signals: list[NormalizedSignalEvent] = []

                if is_script and script_ctx is not None and on_bar is not None:
                    if is_bot:
                        # Bot mode: evaluate on_bar every tick with a synthetic bar.
                        signals.extend(
                            self._evaluate_script_bot_tick(
                                script_ctx, on_bar, current_price, now_ts,
                                timeframe_sec, position_state, trading_config,
                            )
                        )
                    elif new_candle:
                        # Script non-bot: evaluate on new closed bar.
                        new_signals, last_closed_ts = self._script_evaluate_new_closed_bar(
                            kline_df, script_ctx, on_bar, trade_direction,
                            last_closed_ts, strategy_id, symbol, trading_config,
                        )
                        signals.extend(new_signals)
                elif not is_script and indicator_exec_env:
                    # Indicator strategy: re-evaluate on every tick with realtime price.
                    signals.extend(
                        self._evaluate_indicator_strategy(
                            indicator_exec_env, current_price, now_ts,
                            timeframe_sec, position_state, kline_df,
                        )
                    )

                # ── 6e. Server-side risk controls ──────────────────────────
                if position_state["state"] != PositionState.FLAT:
                    if position_state["state"] == PositionState.LONG:
                        trailing_high = max(trailing_high, current_price)
                    elif position_state["state"] == PositionState.SHORT:
                        trailing_low = min(trailing_low, current_price)

                    risk_signal = self._server_side_risk_signal(
                        position_state, current_price, trailing_high,
                        trailing_low, cfg, leverage, now_ts, timeframe_sec,
                    )
                    if risk_signal is not None:
                        signals.append(risk_signal)

                # ── 6f. Filter and dedup signals ───────────────────────────
                for sig in signals:
                    # State machine filter.
                    if not self._is_signal_allowed(
                        position_state["state"], sig.signal_type.value,
                    ):
                        continue
                    # In-memory per-candle dedup.
                    if self._should_skip_signal_once_per_candle(
                        strategy_id, symbol, sig.signal_type.value,
                        sig.timestamp, timeframe_sec, now_ts,
                    ):
                        continue
                    signal_queue.append(sig)

                # ── 6g. Sort by priority and process ───────────────────────
                if signal_queue:
                    sorted_signals = sorted(
                        signal_queue,
                        key=lambda s: self._signal_priority(s.signal_type.value),
                    )
                    signal_queue.clear()

                    for sig in sorted_signals:
                        # Apply trade direction filter.
                        if not self._passes_direction_filter(sig.signal_type, trade_direction):
                            continue
                        # Check trigger mode.
                        if sig.trigger_mode == TriggerMode.PRICE and sig.trigger_price is not None:
                            if not self._price_trigger_met(sig, current_price):
                                signal_queue.append(sig)
                                continue
                        # Remove expired signals.
                        if sig.expiry_seconds > 0 and (now_ts - sig.timestamp) > sig.expiry_seconds:
                            continue

                        if execution_mode == "live":
                            # Live mode: enqueue to pending_orders for worker to execute.
                            self._enqueue_pending_order(
                                strategy_id=strategy_id,
                                symbol=symbol,
                                signal_type=sig.signal_type.value,
                                amount=sig.position_size or 0.0,
                                price=current_price,
                                signal_ts=int(sig.timestamp),
                                market_type=market,
                                leverage=float(leverage),
                                execution_mode="live",
                                notification_config=notification_config,
                            )
                        else:
                            # Signal mode: local simulation.
                            executed = self._execute_signal(
                                sig, position_state, current_price,
                                strategy_id, symbol, market, commission,
                                leverage, initial_capital,
                            )
                            if executed:
                                self._save_position_state(strategy_id, symbol, position_state)
                                if position_state["state"] == PositionState.LONG:
                                    trailing_high = current_price
                                    trailing_low = float("inf")
                                elif position_state["state"] == PositionState.SHORT:
                                    trailing_low = current_price
                                    trailing_high = 0.0

                # ── 6h. Update unrealised PnL in DB ────────────────────────
                if position_state["state"] != PositionState.FLAT:
                    self._update_unrealized_pnl(
                        strategy_id, symbol, position_state, current_price, leverage
                    )

            except Exception as exc:
                logger.error(
                    "tick_error", strategy_id=strategy_id,
                    error=str(exc), exc_info=True,
                )
                append_strategy_log(strategy_id, "ERROR", f"Tick error: {exc}")

            stop_event.wait(timeout=tick_interval)

        # ── Cleanup on stop ────────────────────────────────────────────────
        append_strategy_log(strategy_id, "INFO", "Strategy loop stopped")
        logger.info("strategy_loop_finished", strategy_id=strategy_id)

    # ── Script strategy: new closed bar evaluation ─────────────────────────

    def _script_evaluate_new_closed_bar(
        self,
        df: pd.DataFrame,
        ctx: StrategyScriptContext,
        on_bar: Callable,
        trade_direction: str,
        last_closed_ts: pd.Timestamp | None,
        strategy_id: str,
        symbol: str,
        trading_config: dict[str, Any],
    ) -> tuple[list[NormalizedSignalEvent], pd.Timestamp | None]:
        """Evaluate the newly closed bar for script strategies."""
        if df is None or len(df) < 2:
            return [], last_closed_ts

        # The second-to-last row is the most recently closed bar.
        closed_row = df.iloc[-2]
        closed_ts_val = closed_row.get("time")
        if closed_ts_val is not None:
            try:
                closed_ts = pd.Timestamp(closed_ts_val)
                if last_closed_ts is not None:
                    try:
                        if closed_ts <= last_closed_ts:
                            return [], last_closed_ts
                    except Exception:
                        pass
            except Exception:
                closed_ts = None
        else:
            closed_ts = None

        # Hydrate position from DB.
        init_cap = float(trading_config.get("initial_capital", 0) or 0)
        bar_close = float(closed_row.get("close", 0) or 0)
        self._hydrate_script_ctx_from_positions(
            ctx, strategy_id, symbol,
            initial_capital=init_cap if init_cap > 0 else None,
            current_price=bar_close,
        )

        # Set context to the closed bar.
        ctx.current_index = len(df) - 2
        ctx._orders.clear()

        bar = ScriptBar(
            open=float(closed_row.get("open", 0) or 0),
            high=float(closed_row.get("high", 0) or 0),
            low=float(closed_row.get("low", 0) or 0),
            close=bar_close,
            volume=float(closed_row.get("volume", 0) or 0),
            timestamp=closed_row.get("time"),
        )

        try:
            on_bar(ctx, bar)
        except Exception as exc:
            logger.error("on_bar_error", strategy_id=strategy_id, error=str(exc))
            return [], last_closed_ts

        # Convert script orders to execution signals (8-way).
        signals = self._script_orders_to_execution_signals(
            ctx, trade_direction, bar_close, closed_ts, trading_config,
        )

        # Persist script runtime state.
        self._persist_script_runtime_state(strategy_id, closed_ts, ctx._params)

        logger.info(
            "script_closed_bar", strategy_id=strategy_id,
            closed_ts=str(closed_ts), signals=len(signals),
        )
        return signals, closed_ts

    def _script_orders_to_execution_signals(
        self,
        ctx: StrategyScriptContext,
        trade_direction: str,
        bar_close: float,
        closed_ts: pd.Timestamp | None,
        trading_config: dict[str, Any],
    ) -> list[NormalizedSignalEvent]:
        """Convert script ctx._orders to 8-way NormalizedSignalEvent list."""
        signals: list[NormalizedSignalEvent] = []
        td = (trade_direction or "both").lower()
        if td not in ("long", "short", "both"):
            td = "both"

        tc = trading_config or {}
        default_ratio = self._to_ratio(tc.get("entry_pct", 0.06), 0.06)
        leverage = float(tc.get("leverage", 1) or 1)
        is_bot_script = bool(tc.get("bot_type") or tc.get("strategy_mode") == "bot")

        def _to_qty(usdt_or_ratio: float, ref_price: float) -> float:
            if is_bot_script and usdt_or_ratio > 1.0 and ref_price > 0:
                return usdt_or_ratio * leverage / ref_price
            return usdt_or_ratio

        ts = float(closed_ts.timestamp()) if closed_ts is not None else time.time()

        # Track virtual position for multi-signal bars.
        virtual_side = ctx.position.side  # "long", "short", or ""
        virtual_size = ctx.position.size

        for order in ctx._orders:
            action = order.get("action", "")
            order_price = float(order.get("price") or bar_close)
            order_amount = order.get("amount")
            if order_amount is not None:
                order_amount = float(order_amount)

            if action == "close":
                if virtual_side == "long" and virtual_size > 0:
                    signals.append(NormalizedSignalEvent(
                        signal_type=NormalizedSignal.CLOSE_LONG,
                        price=order_price, timestamp=ts, source="script",
                        position_size=virtual_size,
                    ))
                    virtual_side = ""
                    virtual_size = 0.0
                elif virtual_side == "short" and virtual_size > 0:
                    signals.append(NormalizedSignalEvent(
                        signal_type=NormalizedSignal.CLOSE_SHORT,
                        price=order_price, timestamp=ts, source="script",
                        position_size=virtual_size,
                    ))
                    virtual_side = ""
                    virtual_size = 0.0

            elif action == "buy":
                # If short, close first.
                if virtual_side == "short" and virtual_size > 0:
                    signals.append(NormalizedSignalEvent(
                        signal_type=NormalizedSignal.CLOSE_SHORT,
                        price=order_price, timestamp=ts, source="script",
                        position_size=virtual_size,
                    ))
                    virtual_side = ""
                    virtual_size = 0.0

                if td in ("long", "both"):
                    qty = _to_qty(order_amount or default_ratio, order_price)
                    if virtual_side != "long":
                        signals.append(NormalizedSignalEvent(
                            signal_type=NormalizedSignal.OPEN_LONG,
                            price=order_price, timestamp=ts, source="script",
                            position_size=qty,
                        ))
                        virtual_side = "long"
                        virtual_size = qty
                    else:
                        signals.append(NormalizedSignalEvent(
                            signal_type=NormalizedSignal.ADD_LONG,
                            price=order_price, timestamp=ts, source="script",
                            position_size=qty,
                        ))
                        virtual_size += qty

            elif action == "sell":
                # If long, close first.
                if virtual_side == "long" and virtual_size > 0:
                    signals.append(NormalizedSignalEvent(
                        signal_type=NormalizedSignal.CLOSE_LONG,
                        price=order_price, timestamp=ts, source="script",
                        position_size=virtual_size,
                    ))
                    virtual_side = ""
                    virtual_size = 0.0

                if td in ("short", "both"):
                    qty = _to_qty(order_amount or default_ratio, order_price)
                    if virtual_side != "short":
                        signals.append(NormalizedSignalEvent(
                            signal_type=NormalizedSignal.OPEN_SHORT,
                            price=order_price, timestamp=ts, source="script",
                            position_size=qty,
                        ))
                        virtual_side = "short"
                        virtual_size = qty
                    else:
                        signals.append(NormalizedSignalEvent(
                            signal_type=NormalizedSignal.ADD_SHORT,
                            price=order_price, timestamp=ts, source="script",
                            position_size=qty,
                        ))
                        virtual_size += qty

        return signals

    def _persist_script_runtime_state(
        self,
        strategy_id: str,
        closed_ts: Any,
        params: dict[str, Any],
    ) -> None:
        """Save script runtime state (last_closed_bar_ts + params) to DB trading_config."""
        try:
            safe_params = json.loads(json.dumps(params or {}, default=str))
        except Exception:
            safe_params = {}

        ts_str = ""
        try:
            if closed_ts is not None:
                ts_str = pd.Timestamp(closed_ts).isoformat()
        except Exception:
            ts_str = ""

        state = {"last_closed_bar_ts": ts_str, "params": safe_params}

        session = get_strategy_db_session()
        try:
            strategy = session.query(StrategyModel).filter_by(id=str(strategy_id)).first()
            if strategy is None:
                return
            tc = strategy.trading_config or {}
            if isinstance(tc, str):
                try:
                    tc = json.loads(tc)
                except Exception:
                    tc = {}
            if not isinstance(tc, dict):
                tc = {}
            tc["script_runtime_state"] = state
            strategy.trading_config = tc
            strategy.updated_at = datetime.now(timezone.utc)
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.warning("persist_script_state_failed", strategy_id=strategy_id, error=str(exc))
        finally:
            session.close()

    def _hydrate_script_ctx_from_positions(
        self,
        ctx: StrategyScriptContext,
        strategy_id: str,
        symbol: str,
        initial_capital: float | None = None,
        current_price: float | None = None,
    ) -> None:
        """Sync DB positions into script context."""
        ctx.position.clear_position()

        session = get_strategy_db_session()
        try:
            pos = (
                session.query(StrategyPosition)
                .filter_by(strategy_id=str(strategy_id), symbol=symbol)
                .first()
            )
            if pos is not None:
                side = (pos.side or "").strip().lower()
                size = float(pos.size or 0)
                ep = float(pos.entry_price or 0)
                if side in ("long", "short") and size > 0:
                    ctx.position.open_position(side, ep, size)
        except Exception as exc:
            logger.warning("hydrate_positions_failed", error=str(exc))
        finally:
            session.close()

        # Refresh balance/equity.
        try:
            if initial_capital is not None and initial_capital > 0:
                eq = self._calculate_current_equity(
                    strategy_id, initial_capital, symbol, current_price,
                )
                ctx.balance = float(eq)
                ctx.equity = float(eq)
        except Exception:
            pass

    def _init_script_strategy_context(
        self,
        strategy_id: str,
        df: pd.DataFrame,
        trading_config: dict[str, Any],
        initial_capital: float,
    ) -> tuple[StrategyScriptContext, pd.Timestamp | None]:
        """Initialize script context with persisted params."""
        ctx = StrategyScriptContext(df.copy(), float(initial_capital or 0))

        tc = trading_config or {}
        raw = tc.get("script_runtime_state") or {}
        params = raw.get("params") if isinstance(raw, dict) else {}
        persisted = dict(params) if isinstance(params, dict) else {}
        bot_params_raw = tc.get("bot_params")
        bot_params = dict(bot_params_raw) if isinstance(bot_params_raw, dict) else {}

        # Bot params take precedence over persisted runtime state.
        ctx._params = {**persisted, **bot_params}

        # Restore last_closed_bar_ts.
        last_ts = None
        ts_s = raw.get("last_closed_bar_ts") if isinstance(raw, dict) else None
        if ts_s:
            try:
                last_ts = pd.Timestamp(ts_s)
                if last_ts.tzinfo is None:
                    last_ts = last_ts.tz_localize("UTC")
                else:
                    last_ts = last_ts.tz_convert("UTC")
            except Exception:
                last_ts = None

        return ctx, last_ts

    def _calculate_current_equity(
        self,
        strategy_id: str,
        initial_capital: float,
        symbol: str,
        current_price: float | None,
    ) -> float:
        """Calculate current equity = initial_capital + realized PnL + unrealized PnL."""
        session = get_strategy_db_session()
        try:
            # Sum realized PnL from trades.
            from sqlalchemy import func as sa_func
            realized = (
                session.query(sa_func.coalesce(sa_func.sum(StrategyTrade.profit), 0.0))
                .filter(StrategyTrade.strategy_id == str(strategy_id))
                .scalar()
            ) or 0.0

            # Unrealized PnL from current position.
            pos = (
                session.query(StrategyPosition)
                .filter_by(strategy_id=str(strategy_id), symbol=symbol)
                .first()
            )
            unrealized = 0.0
            if pos is not None and float(pos.size or 0) > 0 and current_price:
                side = (pos.side or "").lower()
                ep = float(pos.entry_price or 0)
                sz = float(pos.size or 0)
                if side == "long" and ep > 0:
                    unrealized = (current_price - ep) * sz
                elif side == "short" and ep > 0:
                    unrealized = (ep - current_price) * sz

            return initial_capital + float(realized) + unrealized
        except Exception as exc:
            logger.warning("calc_equity_failed", error=str(exc))
            return initial_capital
        finally:
            session.close()

    def _evaluate_script_bot_tick(
        self,
        ctx: StrategyScriptContext,
        on_bar: Callable,
        current_price: float,
        now_ts: float,
        timeframe_sec: int,
        position_state: dict[str, Any],
        trading_config: dict[str, Any],
    ) -> list[NormalizedSignalEvent]:
        """Bot mode: evaluate on_bar every tick with a synthetic bar from current price."""
        signals: list[NormalizedSignalEvent] = []

        # Build a synthetic bar at the current price.
        ctx._orders.clear()
        bar = ScriptBar(
            open=current_price,
            high=current_price,
            low=current_price,
            close=current_price,
            volume=0.0,
            timestamp=pd.Timestamp.now(tz="UTC"),
        )

        try:
            on_bar(ctx, bar)
        except Exception as exc:
            logger.warning("bot_on_bar_error", error=str(exc))
            return signals

        # Convert orders to 8-way signals.
        for order in ctx._orders:
            action = order.get("action", "")
            order_price = float(order.get("price") or current_price)
            order_amount = order.get("amount")
            if order_amount is not None:
                order_amount = float(order_amount)

            sig = self._normalize_bot_order(action, position_state, order_price, order_amount)
            if sig is not None:
                sig.timestamp = now_ts
                sig.source = "script_bot"
                signals.append(sig)

        return signals

    @staticmethod
    def _normalize_bot_order(
        action: str,
        position_state: dict[str, Any],
        price: float,
        amount: float | None,
    ) -> NormalizedSignalEvent | None:
        """Convert a bot script order to an 8-way signal."""
        current_state = position_state.get("state", PositionState.FLAT)

        if action == "close":
            if current_state == PositionState.LONG:
                return NormalizedSignalEvent(
                    signal_type=NormalizedSignal.CLOSE_LONG, price=price, timestamp=0.0,
                )
            if current_state == PositionState.SHORT:
                return NormalizedSignalEvent(
                    signal_type=NormalizedSignal.CLOSE_SHORT, price=price, timestamp=0.0,
                )
            return None

        if action == "buy":
            if current_state == PositionState.SHORT:
                return NormalizedSignalEvent(
                    signal_type=NormalizedSignal.CLOSE_SHORT, price=price, timestamp=0.0,
                )
            if current_state == PositionState.FLAT:
                return NormalizedSignalEvent(
                    signal_type=NormalizedSignal.OPEN_LONG, price=price, timestamp=0.0,
                    position_size=amount,
                )
            if current_state == PositionState.LONG:
                return NormalizedSignalEvent(
                    signal_type=NormalizedSignal.ADD_LONG, price=price, timestamp=0.0,
                    position_size=amount,
                )
            return None

        if action == "sell":
            if current_state == PositionState.LONG:
                return NormalizedSignalEvent(
                    signal_type=NormalizedSignal.CLOSE_LONG, price=price, timestamp=0.0,
                )
            if current_state == PositionState.FLAT:
                return NormalizedSignalEvent(
                    signal_type=NormalizedSignal.OPEN_SHORT, price=price, timestamp=0.0,
                    position_size=amount,
                )
            if current_state == PositionState.SHORT:
                return NormalizedSignalEvent(
                    signal_type=NormalizedSignal.ADD_SHORT, price=price, timestamp=0.0,
                    position_size=amount,
                )
            return None

        return None

    # ── Indicator strategy evaluation ──────────────────────────────────────

    def _build_indicator_env(
        self,
        code: str,
        df: pd.DataFrame,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> dict[str, Any] | None:
        """
        Execute indicator code against *df* and return the exec env.

        The env will contain the mutated ``df`` (with ``buy``/``sell``
        columns) plus any helper variables.  Returns ``None`` on failure.
        """
        from app.core.safe_exec import build_safe_builtins, safe_exec_with_validation

        exec_env: dict[str, Any] = {
            "__builtins__": build_safe_builtins(),
            "np": np,
            "pd": pd,
            "df": df,
        }
        exec_env.update(params)

        # 注入 DB-aware call_indicator（支持环形检测 + 深度限制）
        from app.strategies.indicator_caller import IndicatorCaller

        indicator_caller = IndicatorCaller(user_id=user_id)
        exec_env["call_indicator"] = lambda ref, d, p=None: indicator_caller.call_indicator(
            ref, d, p, _depth=0
        )

        result = safe_exec_with_validation(
            code=code,
            exec_globals=exec_env,
            exec_locals=exec_env,
            timeout=30,
        )
        if not result["success"]:
            logger.error("indicator_exec_failed", error=result.get("error"))
            return None
        return exec_env

    def _evaluate_indicator_strategy(
        self,
        env: dict[str, Any],
        current_price: float,
        now_ts: float,
        timeframe_sec: int,
        position_state: dict[str, Any],
        kline_df: pd.DataFrame | None,
    ) -> list[NormalizedSignalEvent]:
        """
        Inspect the ``df`` produced by an indicator script and emit
        signals for the latest bar.  Supports 8-way signals.
        """
        signals: list[NormalizedSignalEvent] = []
        df: pd.DataFrame | None = env.get("df")
        if df is None or df.empty:
            return signals

        last_row = df.iloc[-1]
        buy_val = self._coerce_numeric(last_row.get("buy", 0))
        sell_val = self._coerce_numeric(last_row.get("sell", 0))

        state = position_state["state"]

        # Buy signal logic (4-way: open/add long, close/reduce short).
        if buy_val > 0:
            if state == PositionState.SHORT:
                # Close short on buy signal.
                signals.append(NormalizedSignalEvent(
                    signal_type=NormalizedSignal.CLOSE_SHORT,
                    price=current_price, timestamp=now_ts, source="indicator",
                ))
            if state == PositionState.FLAT:
                signals.append(NormalizedSignalEvent(
                    signal_type=NormalizedSignal.OPEN_LONG,
                    price=current_price, timestamp=now_ts, source="indicator",
                    trigger_mode=TriggerMode.PRICE, trigger_price=current_price,
                ))
            elif state == PositionState.LONG:
                signals.append(NormalizedSignalEvent(
                    signal_type=NormalizedSignal.ADD_LONG,
                    price=current_price, timestamp=now_ts, source="indicator",
                ))

        # Sell signal logic (4-way: open/add short, close/reduce long).
        if sell_val > 0:
            if state == PositionState.LONG:
                signals.append(NormalizedSignalEvent(
                    signal_type=NormalizedSignal.CLOSE_LONG,
                    price=current_price, timestamp=now_ts, source="indicator",
                ))
            if state == PositionState.FLAT:
                signals.append(NormalizedSignalEvent(
                    signal_type=NormalizedSignal.OPEN_SHORT,
                    price=current_price, timestamp=now_ts, source="indicator",
                    trigger_mode=TriggerMode.PRICE, trigger_price=current_price,
                ))
            elif state == PositionState.SHORT:
                signals.append(NormalizedSignalEvent(
                    signal_type=NormalizedSignal.ADD_SHORT,
                    price=current_price, timestamp=now_ts, source="indicator",
                ))

        return signals

    @staticmethod
    def _coerce_numeric(value: Any) -> float:
        """Safely convert a value to float, returning 0.0 on failure."""
        try:
            return float(value) if value is not None else 0.0
        except (ValueError, TypeError):
            return 0.0

    # ── Server-side risk controls ──────────────────────────────────────────

    def _is_server_side_exit_enabled(
        self,
        trading_config: dict[str, Any] | None,
        config_key: str,
    ) -> bool:
        """Check if server-side exit (SL/TP) is enabled in config."""
        tc = trading_config if isinstance(trading_config, dict) else {}
        bot_type = tc.get("bot_type", "")

        # Explicit key check.
        if config_key in tc:
            v = tc[config_key]
            if isinstance(v, str):
                return v.lower() not in ("0", "false", "no", "off")
            return bool(v)

        # Non-bot strategies: enabled by default.
        if not bot_type:
            return True

        # Bot strategies: enabled if the percentage is configured.
        if config_key == "enable_server_side_stop_loss":
            return self._to_ratio(tc.get("stop_loss_pct", 0)) > 0
        if config_key == "enable_server_side_take_profit":
            return self._to_ratio(tc.get("take_profit_pct", 0)) > 0

        return False

    def _server_side_risk_signal(
        self,
        position_state: dict[str, Any],
        current_price: float,
        trailing_high: float,
        trailing_low: float,
        cfg: dict[str, Any],
        leverage: int,
        now_ts: float,
        timeframe_sec: int,
    ) -> NormalizedSignalEvent | None:
        """
        Evaluate server-side stop-loss, take-profit, and trailing stop
        conditions.  Returns a close signal if any threshold is hit.
        """
        state = position_state.get("state", PositionState.FLAT)
        if state == PositionState.FLAT:
            return None

        entry_price = float(position_state.get("entry_price", 0) or 0)
        if entry_price <= 0:
            return None

        risk = cfg.get("risk", {})
        sl_pct = risk.get("stopLossPct", 0)
        tp_pct = risk.get("takeProfitPct", 0)
        trailing = risk.get("trailing", {})
        trailing_enabled = trailing.get("enabled", False)
        trailing_pct = trailing.get("pct", 0)
        trailing_act = trailing.get("activationPct", 0)

        lev = max(leverage, 1)

        if state == PositionState.LONG:
            return self._check_long_risk(
                entry_price, current_price, trailing_high,
                sl_pct, tp_pct, trailing_enabled, trailing_pct, trailing_act,
                lev, now_ts,
            )
        if state == PositionState.SHORT:
            return self._check_short_risk(
                entry_price, current_price, trailing_low,
                sl_pct, tp_pct, trailing_enabled, trailing_pct, trailing_act,
                lev, now_ts,
            )
        return None

    def _check_long_risk(
        self,
        entry_price: float,
        current_price: float,
        trailing_high: float,
        stop_loss_pct: float,
        take_profit_pct: float,
        trailing_enabled: bool,
        trailing_stop_pct: float,
        trailing_activation_pct: float,
        leverage: int,
        now_ts: float,
    ) -> NormalizedSignalEvent | None:
        """Check risk thresholds for a long position."""
        # Stop loss.
        if stop_loss_pct > 0:
            effective_sl = stop_loss_pct / leverage
            sl_price = entry_price * (1 - effective_sl)
            if current_price <= sl_price:
                logger.info("stop_loss_triggered", price=current_price, sl_price=sl_price)
                return NormalizedSignalEvent(
                    signal_type=NormalizedSignal.CLOSE_LONG,
                    price=current_price, timestamp=now_ts, source="risk_control_stop_loss",
                )

        # Trailing stop (takes precedence over fixed TP when enabled).
        if trailing_enabled and trailing_stop_pct > 0:
            effective_act = trailing_activation_pct / leverage
            effective_trail = trailing_stop_pct / leverage
            activation_price = entry_price * (1 + effective_act)
            if trailing_high >= activation_price:
                trail_price = trailing_high * (1 - effective_trail)
                if current_price <= trail_price:
                    logger.info("trailing_stop_triggered", price=current_price, trail_price=trail_price)
                    return NormalizedSignalEvent(
                        signal_type=NormalizedSignal.CLOSE_LONG,
                        price=current_price, timestamp=now_ts, source="risk_control_trailing",
                    )
            return None

        # Fixed take profit (only when trailing is disabled).
        if take_profit_pct > 0:
            effective_tp = take_profit_pct / leverage
            tp_price = entry_price * (1 + effective_tp)
            if current_price >= tp_price:
                logger.info("take_profit_triggered", price=current_price, tp_price=tp_price)
                return NormalizedSignalEvent(
                    signal_type=NormalizedSignal.CLOSE_LONG,
                    price=current_price, timestamp=now_ts, source="risk_control_take_profit",
                )

        return None

    def _check_short_risk(
        self,
        entry_price: float,
        current_price: float,
        trailing_low: float,
        stop_loss_pct: float,
        take_profit_pct: float,
        trailing_enabled: bool,
        trailing_stop_pct: float,
        trailing_activation_pct: float,
        leverage: int,
        now_ts: float,
    ) -> NormalizedSignalEvent | None:
        """Check risk thresholds for a short position."""
        # Stop loss.
        if stop_loss_pct > 0:
            effective_sl = stop_loss_pct / leverage
            sl_price = entry_price * (1 + effective_sl)
            if current_price >= sl_price:
                logger.info("stop_loss_triggered", price=current_price, sl_price=sl_price)
                return NormalizedSignalEvent(
                    signal_type=NormalizedSignal.CLOSE_SHORT,
                    price=current_price, timestamp=now_ts, source="risk_control_stop_loss",
                )

        # Trailing stop.
        if trailing_enabled and trailing_stop_pct > 0:
            effective_act = trailing_activation_pct / leverage
            effective_trail = trailing_stop_pct / leverage
            activation_price = entry_price * (1 - effective_act)
            if trailing_low <= activation_price and trailing_low < float("inf"):
                trail_price = trailing_low * (1 + effective_trail)
                if current_price >= trail_price:
                    logger.info("trailing_stop_triggered", price=current_price, trail_price=trail_price)
                    return NormalizedSignalEvent(
                        signal_type=NormalizedSignal.CLOSE_SHORT,
                        price=current_price, timestamp=now_ts, source="risk_control_trailing",
                    )
            return None

        # Fixed take profit.
        if take_profit_pct > 0:
            effective_tp = take_profit_pct / leverage
            tp_price = entry_price * (1 - effective_tp)
            if current_price <= tp_price:
                logger.info("take_profit_triggered", price=current_price, tp_price=tp_price)
                return NormalizedSignalEvent(
                    signal_type=NormalizedSignal.CLOSE_SHORT,
                    price=current_price, timestamp=now_ts, source="risk_control_take_profit",
                )

        return None

    @staticmethod
    def _margin_pnl_to_price(
        entry_price: float,
        pnl_pct: float,
        leverage: int,
        is_long: bool,
    ) -> float:
        """
        Convert a margin PnL percentage to an absolute price threshold.

        For a long position a ``pnl_pct`` of 0.02 with 10x leverage
        means the price can move 0.2% against the entry before the
        margin PnL reaches 2%.
        """
        effective_pct = pnl_pct / max(leverage, 1)
        if is_long:
            return entry_price * (1 - effective_pct)
        return entry_price * (1 + effective_pct)

    # ── Signal queue management ────────────────────────────────────────────

    @staticmethod
    def _passes_direction_filter(signal_type: NormalizedSignal, trade_direction: str) -> bool:
        """Check if the signal is allowed by the trade_direction setting."""
        if trade_direction == "both":
            return True
        if trade_direction == "long":
            return signal_type.value in (
                "open_long", "close_long", "add_long", "reduce_long",
            )
        if trade_direction == "short":
            return signal_type.value in (
                "open_short", "close_short", "add_short", "reduce_short",
            )
        return True

    @staticmethod
    def _price_trigger_met(signal: NormalizedSignalEvent, current_price: float) -> bool:
        """Check whether a price-based trigger condition is satisfied."""
        tp = signal.trigger_price
        if tp is None:
            return True
        if signal.signal_type in (NormalizedSignal.OPEN_LONG, NormalizedSignal.CLOSE_SHORT):
            return current_price <= tp
        if signal.signal_type in (NormalizedSignal.OPEN_SHORT, NormalizedSignal.CLOSE_LONG):
            return current_price >= tp
        return True

    # ── Signal execution (8-way) ───────────────────────────────────────────

    def _execute_signal(
        self,
        signal: NormalizedSignalEvent,
        position_state: dict[str, Any],
        current_price: float,
        strategy_id: str,
        symbol: str,
        market: str,
        commission: float,
        leverage: int,
        initial_capital: float,
    ) -> bool:
        """
        Execute a single normalised signal (8-way).

        Updates in-memory ``position_state``, creates DB trade and log
        records.  Returns ``True`` on success.
        """
        state = position_state.get("state", PositionState.FLAT)
        sig = signal.signal_type
        price = current_price
        entry_pct = 0.06  # Default position ratio.

        # Determine trade amount.
        amount = signal.position_size
        if amount is None or amount <= 0:
            if sig in (NormalizedSignal.OPEN_LONG, NormalizedSignal.OPEN_SHORT):
                amount = initial_capital * entry_pct * leverage / price if price > 0 else 0.0
            elif sig in (NormalizedSignal.ADD_LONG, NormalizedSignal.ADD_SHORT):
                # Add: use a fraction of current position or default ratio.
                current_size = position_state.get("size", 0.0)
                amount = current_size * 0.5 if current_size > 0 else 0.0
            elif sig in (NormalizedSignal.REDUCE_LONG, NormalizedSignal.REDUCE_SHORT):
                amount = position_state.get("size", 0.0) * 0.5
            else:
                amount = position_state.get("size", 0.0)

        if amount is None or amount <= 0:
            return False

        comm_cost = amount * price * commission
        profit = 0.0

        # ── OPEN LONG ──────────────────────────────────────────────────
        if sig == NormalizedSignal.OPEN_LONG:
            if state != PositionState.FLAT:
                return False
            position_state["state"] = PositionState.LONG
            position_state["side"] = "long"
            position_state["entry_price"] = price
            position_state["size"] = amount
            position_state["amount"] = amount

        # ── CLOSE LONG ─────────────────────────────────────────────────
        elif sig == NormalizedSignal.CLOSE_LONG:
            if state != PositionState.LONG:
                return False
            entry = float(position_state.get("entry_price", 0) or 0)
            profit = (price - entry) * amount - comm_cost
            self._clear_position(position_state)

        # ── OPEN SHORT ─────────────────────────────────────────────────
        elif sig == NormalizedSignal.OPEN_SHORT:
            if state != PositionState.FLAT:
                return False
            position_state["state"] = PositionState.SHORT
            position_state["side"] = "short"
            position_state["entry_price"] = price
            position_state["size"] = amount
            position_state["amount"] = amount

        # ── CLOSE SHORT ────────────────────────────────────────────────
        elif sig == NormalizedSignal.CLOSE_SHORT:
            if state != PositionState.SHORT:
                return False
            entry = float(position_state.get("entry_price", 0) or 0)
            profit = (entry - price) * amount - comm_cost
            self._clear_position(position_state)

        # ── ADD LONG ───────────────────────────────────────────────────
        elif sig == NormalizedSignal.ADD_LONG:
            if state != PositionState.LONG:
                return False
            # Weighted average entry price.
            old_size = float(position_state.get("size", 0) or 0)
            old_entry = float(position_state.get("entry_price", 0) or 0)
            new_size = old_size + amount
            if new_size > 0:
                position_state["entry_price"] = (old_entry * old_size + price * amount) / new_size
            position_state["size"] = new_size
            position_state["amount"] = new_size

        # ── ADD SHORT ──────────────────────────────────────────────────
        elif sig == NormalizedSignal.ADD_SHORT:
            if state != PositionState.SHORT:
                return False
            old_size = float(position_state.get("size", 0) or 0)
            old_entry = float(position_state.get("entry_price", 0) or 0)
            new_size = old_size + amount
            if new_size > 0:
                position_state["entry_price"] = (old_entry * old_size + price * amount) / new_size
            position_state["size"] = new_size
            position_state["amount"] = new_size

        # ── REDUCE LONG ────────────────────────────────────────────────
        elif sig == NormalizedSignal.REDUCE_LONG:
            if state != PositionState.LONG:
                return False
            entry = float(position_state.get("entry_price", 0) or 0)
            current_size = float(position_state.get("size", 0) or 0)
            # Cap to current size.
            reduce_amount = min(amount, current_size)
            profit = (price - entry) * reduce_amount - comm_cost
            remaining = current_size - reduce_amount
            if remaining <= current_size * 0.001:
                # ≥99.9% reduced = full close.
                self._clear_position(position_state)
            else:
                position_state["size"] = remaining
                position_state["amount"] = remaining

        # ── REDUCE SHORT ───────────────────────────────────────────────
        elif sig == NormalizedSignal.REDUCE_SHORT:
            if state != PositionState.SHORT:
                return False
            entry = float(position_state.get("entry_price", 0) or 0)
            current_size = float(position_state.get("size", 0) or 0)
            reduce_amount = min(amount, current_size)
            profit = (entry - price) * reduce_amount - comm_cost
            remaining = current_size - reduce_amount
            if remaining <= current_size * 0.001:
                self._clear_position(position_state)
            else:
                position_state["size"] = remaining
                position_state["amount"] = remaining

        else:
            return False

        # Record trade in DB.
        self._record_trade(
            strategy_id=strategy_id, symbol=symbol, trade_type=sig.value,
            price=price, amount=amount, profit=profit, commission=comm_cost,
            value=amount * price,
        )

        append_strategy_log(
            strategy_id, "INFO",
            f"Executed {sig.value} {symbol} @ {price:.4f} x {amount:.4f} "
            f"(profit={profit:.2f}, commission={comm_cost:.2f})",
        )
        logger.info(
            "signal_executed", strategy_id=strategy_id,
            signal=sig.value, price=price, amount=amount, profit=profit,
        )
        return True

    @staticmethod
    def _clear_position(position_state: dict[str, Any]) -> None:
        """Reset position state to flat."""
        position_state["state"] = PositionState.FLAT
        position_state["side"] = ""
        position_state["entry_price"] = 0.0
        position_state["size"] = 0.0
        position_state["amount"] = 0.0

    # ── Pending order enqueue ──────────────────────────────────────────────

    def _enqueue_pending_order(
        self,
        strategy_id: str,
        symbol: str,
        signal_type: str,
        amount: float,
        price: float,
        signal_ts: int,
        market_type: str,
        leverage: float,
        execution_mode: str,
        notification_config: dict[str, Any] | None = None,
        extra_payload: dict[str, Any] | None = None,
    ) -> int | None:
        """
        Enqueue a signal to the pending_orders table with DB-level dedup.

        Returns the pending order ID, or None if deduped.
        """
        mode = execution_mode if execution_mode in ("signal", "live") else "signal"

        payload: dict[str, Any] = {
            "signal_type": signal_type,
            "symbol": symbol,
            "amount": amount,
            "price": price,
            "signal_ts": signal_ts,
            "market_type": market_type,
            "leverage": leverage,
            "execution_mode": mode,
            "notification_config": notification_config,
        }
        if extra_payload:
            payload.update(extra_payload)

        session = get_strategy_db_session()
        try:
            # DB-based dedup: cooldown 30s for same signal_type+symbol.
            cooldown_sec = 30
            strict_candle_dedup = (
                signal_ts > 0
                and signal_type in ("open_long", "open_short", "close_long", "close_short")
            )

            if strict_candle_dedup:
                existing = (
                    session.query(PendingOrder)
                    .filter_by(
                        strategy_id=str(strategy_id),
                        symbol=symbol,
                        signal_type=signal_type,
                        signal_ts=signal_ts,
                    )
                    .first()
                )
                if existing is not None:
                    return None

            # Check last order for cooldown.
            last_order = (
                session.query(PendingOrder)
                .filter_by(strategy_id=str(strategy_id), symbol=symbol, signal_type=signal_type)
                .order_by(PendingOrder.id.desc())
                .first()
            )
            if last_order is not None:
                if last_order.status in ("pending", "processing"):
                    return None
                if last_order.created_at is not None:
                    elapsed = (datetime.now(timezone.utc) - last_order.created_at).total_seconds()
                    if elapsed < cooldown_sec:
                        return None

            order = PendingOrder(
                strategy_id=str(strategy_id),
                symbol=symbol,
                signal_type=signal_type,
                signal_ts=signal_ts,
                trigger_price=price,
                position_size=amount,
                payload_json=json.dumps(payload, ensure_ascii=False, default=str),
                execution_mode=mode,
                status="pending",
                priority=self._signal_priority(signal_type),
                attempts=0,
                max_attempts=10,
            )
            session.add(order)
            session.commit()
            pending_id = order.id
            logger.info(
                "pending_order_enqueued", strategy_id=strategy_id,
                signal_type=signal_type, pending_id=pending_id,
            )
            return pending_id
        except Exception as exc:
            session.rollback()
            logger.error("enqueue_pending_order_failed", error=str(exc))
            return None
        finally:
            session.close()

    def _execute_exchange_order(
        self,
        strategy_id: str,
        symbol: str,
        signal_type: str,
        amount: float,
        ref_price: float,
        market_type: str = "swap",
        leverage: float = 1.0,
        execution_mode: str = "signal",
        notification_config: dict[str, Any] | None = None,
        signal_ts: int = 0,
    ) -> dict[str, Any]:
        """Build payload and enqueue to pending_orders. Does NOT connect to exchange."""
        extra_payload = {
            "ref_price": ref_price,
            "signal_ts": signal_ts,
        }

        pending_id = self._enqueue_pending_order(
            strategy_id=strategy_id,
            symbol=symbol,
            signal_type=signal_type,
            amount=amount,
            price=ref_price,
            signal_ts=signal_ts,
            market_type=market_type,
            leverage=leverage,
            execution_mode=execution_mode,
            notification_config=notification_config,
            extra_payload=extra_payload,
        )

        if pending_id is None:
            return {"success": False, "error": "信号去重或入队失败，请稍后重试"}

        if execution_mode == "live":
            return {
                "success": True,
                "pending": True,
                "order_id": f"pending_{pending_id}",
                "filled_amount": 0,
                "filled_price": 0,
                "total_cost": 0,
                "fee": 0,
                "message": "Order enqueued to pending_orders for live execution",
            }
        else:
            return {
                "success": True,
                "pending": False,
                "order_id": f"pending_{pending_id}",
                "filled_amount": amount,
                "filled_price": ref_price,
                "total_cost": amount * ref_price,
                "fee": 0,
                "message": "Order enqueued (signal mode)",
            }

    # ── Fee rate caching ───────────────────────────────────────────────────

    def _query_exchange_fee_rate(
        self,
        strategy_id: str,
        symbol: str,
        market_type: str = "swap",
    ) -> dict[str, float] | None:
        """Query and cache fee rate for a strategy. Per-strategy negative cache."""
        with self._exchange_fee_cache_lock:
            if strategy_id in self._exchange_fee_cache:
                return self._exchange_fee_cache[strategy_id]

        # Try to get from DB StrategyFeeRate table first.
        session = get_strategy_db_session()
        try:
            fee_rate = (
                session.query(StrategyFeeRate)
                .filter_by(strategy_id=str(strategy_id))
                .first()
            )
            if fee_rate is not None:
                result = {"maker": float(fee_rate.maker or 0.0002), "taker": float(fee_rate.taker or 0.0005)}
                with self._exchange_fee_cache_lock:
                    self._exchange_fee_cache[strategy_id] = result
                return result
        except Exception as exc:
            logger.warning("query_fee_rate_db_failed", error=str(exc))
        finally:
            session.close()

        # Fallback to default.
        result: dict[str, float] = {"maker": 0.0002, "taker": 0.0005}
        with self._exchange_fee_cache_lock:
            self._exchange_fee_cache[strategy_id] = result
        return result

    # ── Position state management ──────────────────────────────────────────

    @staticmethod
    def _load_position_state(strategy_id: str, symbol: str) -> dict[str, Any]:
        """Load position from DB or initialise a flat position."""
        session = get_strategy_db_session()
        try:
            pos = (
                session.query(StrategyPosition)
                .filter_by(strategy_id=str(strategy_id), symbol=symbol)
                .first()
            )
            if pos is not None and float(pos.size or 0) > 0:
                side = pos.side or ""
                return {
                    "state": side if side in ("long", "short") else PositionState.FLAT,
                    "side": side,
                    "entry_price": float(pos.entry_price or 0),
                    "size": float(pos.size or 0),
                    "amount": float(pos.amount or 0),
                    "highest_price": float(pos.highest_price or 0),
                    "lowest_price": float(pos.lowest_price or 0),
                }
        except Exception as exc:
            logger.warning("load_position_failed", error=str(exc))
        finally:
            session.close()

        return {
            "state": PositionState.FLAT,
            "side": "",
            "entry_price": 0.0,
            "size": 0.0,
            "amount": 0.0,
            "highest_price": 0.0,
            "lowest_price": float("inf"),
        }

    @staticmethod
    def _save_position_state(
        strategy_id: str, symbol: str, position_state: dict[str, Any]
    ) -> None:
        """Upsert the position row in the database."""
        session = get_strategy_db_session()
        try:
            pos = (
                session.query(StrategyPosition)
                .filter_by(strategy_id=str(strategy_id), symbol=symbol)
                .first()
            )
            if position_state["state"] == PositionState.FLAT:
                if pos is not None:
                    pos.size = 0.0
                    pos.amount = 0.0
                    pos.entry_price = 0.0
                    pos.side = ""
                    pos.unrealized_pnl = 0.0
                    pos.updated_at = datetime.now(timezone.utc)
            else:
                if pos is None:
                    pos = StrategyPosition(strategy_id=str(strategy_id), symbol=symbol)
                    session.add(pos)
                pos.side = position_state.get("side", "")
                pos.size = float(position_state.get("size", 0) or 0)
                pos.entry_price = float(position_state.get("entry_price", 0) or 0)
                pos.amount = float(position_state.get("amount", 0) or 0)
                pos.highest_price = float(position_state.get("highest_price", 0) or 0)
                pos.lowest_price = float(position_state.get("lowest_price", 0) or 0)
                pos.updated_at = datetime.now(timezone.utc)
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.error("save_position_failed", error=str(exc))
        finally:
            session.close()

    @staticmethod
    def _update_unrealized_pnl(
        strategy_id: str,
        symbol: str,
        position_state: dict[str, Any],
        current_price: float,
        leverage: int,
    ) -> None:
        """Write unrealised PnL to the position row."""
        state = position_state.get("state", PositionState.FLAT)
        if state == PositionState.FLAT:
            return

        entry = float(position_state.get("entry_price", 0) or 0)
        size = float(position_state.get("size", 0) or 0)
        if entry <= 0 or size <= 0:
            return

        if state == PositionState.LONG:
            pnl = (current_price - entry) * size * leverage
            position_state["highest_price"] = max(
                float(position_state.get("highest_price", 0) or 0), current_price
            )
        else:
            pnl = (entry - current_price) * size * leverage
            current_low = float(position_state.get("lowest_price", float("inf")) or float("inf"))
            position_state["lowest_price"] = min(current_low, current_price)

        session = get_strategy_db_session()
        try:
            pos = (
                session.query(StrategyPosition)
                .filter_by(strategy_id=str(strategy_id), symbol=symbol)
                .first()
            )
            if pos is not None:
                pos.unrealized_pnl = round(pnl, 4)
                pos.current_price = current_price
                pos.highest_price = position_state.get("highest_price", 0)
                pos.lowest_price = position_state.get("lowest_price", 0)
                pos.updated_at = datetime.now(timezone.utc)
                session.commit()
        except Exception as exc:
            session.rollback()
            logger.warning("update_pnl_failed", error=str(exc))
        finally:
            session.close()

    # ── Trade & log recording ──────────────────────────────────────────────

    @staticmethod
    def _record_trade(
        strategy_id: str,
        symbol: str,
        trade_type: str,
        price: float,
        amount: float,
        profit: float,
        commission: float,
        value: float = 0.0,
    ) -> None:
        """Insert a :class:`StrategyTrade` row."""
        session = get_strategy_db_session()
        try:
            session.add(StrategyTrade(
                strategy_id=str(strategy_id),
                symbol=symbol,
                trade_type=trade_type,
                price=round(price, 6),
                amount=round(amount, 6),
                profit=round(profit, 4),
                commission=round(commission, 4),
                value=round(value, 4),
                balance=0.0,
            ))
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.error("record_trade_failed", error=str(exc))
        finally:
            session.close()

    # ── Data fetching ──────────────────────────────────────────────────────

    def _fetch_current_price(self, market: str, symbol: str) -> float | None:
        """
        Fetch the latest price for *symbol* using UF's data tools.

        Uses PriceCache to reduce redundant API calls. Returns ``None`` on failure.
        """
        # Check price cache first.
        cached = self._price_cache.get(symbol)
        if cached is not None:
            return cached

        try:
            price: float | None = None
            if market == "stock":
                from app.services.market_sync import get_local_quote

                data = get_local_quote(symbol)
                if data is None:
                    from app.tools.stock_data import get_stock_realtime
                    data = get_stock_realtime(symbol)
                    if isinstance(data, str):
                        data = json.loads(data)
                if isinstance(data, dict):
                    raw = data.get("price")
                    if raw is not None:
                        price = float(raw)

            elif market == "crypto":
                from app.tools.crypto_data import get_crypto_ticker

                data = get_crypto_ticker(symbol)
                if isinstance(data, dict):
                    raw = data.get("last_price") or data.get("price")
                    if raw is not None:
                        price = float(raw)
            else:
                logger.warning("unknown_market", market=market)
                return None

            if price is not None and price > 0:
                self._price_cache.set(symbol, price)
            return price

        except Exception as exc:
            logger.warning("fetch_price_failed", market=market, symbol=symbol, error=str(exc))
            return None

    def _fetch_kline_data(
        self,
        market: str,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> pd.DataFrame | None:
        """
        Fetch historical kline data and return a normalised DataFrame.

        The returned DataFrame always has columns:
        ``time``, ``open``, ``high``, ``low``, ``close``, ``volume``.
        Returns ``None`` on failure.
        """
        try:
            if market == "stock":
                return self._fetch_stock_klines(symbol, timeframe, limit)
            if market == "crypto":
                return self._fetch_crypto_klines(symbol, timeframe, limit)
            logger.warning("unknown_market_klines", market=market)
            return None
        except Exception as exc:
            logger.warning("fetch_klines_failed", market=market, symbol=symbol, error=str(exc))
            return None

    @staticmethod
    def _fetch_stock_klines(
        symbol: str, timeframe: str, limit: int
    ) -> pd.DataFrame | None:
        """Fetch A-share klines via AKShare and normalise."""
        from app.tools.stock_data import get_stock_history

        period = _timeframe_to_akshare_period(timeframe)
        raw = get_stock_history(symbol, period=period, limit=limit)
        parsed = json.loads(raw) if isinstance(raw, str) else raw

        data_list = parsed.get("data", []) if isinstance(parsed, dict) else []
        if not data_list:
            return None

        df = pd.DataFrame(data_list)
        if "date" in df.columns:
            df = df.rename(columns={"date": "time"})

        for col in ("open", "high", "low", "close", "volume"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if "time" not in df.columns:
            df["time"] = range(len(df))

        return df[["time", "open", "high", "low", "close", "volume"]].dropna()

    @staticmethod
    def _fetch_crypto_klines(
        symbol: str, timeframe: str, limit: int
    ) -> pd.DataFrame | None:
        """Fetch crypto klines via CCXT and normalise."""
        from app.tools.crypto_data import get_crypto_ohlcv

        ccxt_tf = _timeframe_to_ccxt(timeframe)
        result = get_crypto_ohlcv(symbol, timeframe=ccxt_tf, limit=limit)
        data_list = result.get("data", []) if isinstance(result, dict) else []
        if not data_list:
            return None

        df = pd.DataFrame(data_list)
        if "timestamp" in df.columns:
            df = df.rename(columns={"timestamp": "time"})

        for col in ("open", "high", "low", "close", "volume"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if "time" not in df.columns:
            df["time"] = range(len(df))

        return df[["time", "open", "high", "low", "close", "volume"]].dropna()

    # ── Time helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _candle_boundary_ts(ts: float, timeframe_sec: int) -> float:
        """
        Return the start-of-candle timestamp for *ts*.

        Used to detect when we have crossed into a new candle.
        """
        if timeframe_sec <= 0:
            return ts
        return float(int(ts // timeframe_sec) * timeframe_sec)


# ── Module-level singleton ─────────────────────────────────────────────────

_executor: TradingExecutor | None = None


def get_trading_executor() -> TradingExecutor:
    """Return the module-level :class:`TradingExecutor` singleton."""
    global _executor
    if _executor is None:
        _executor = TradingExecutor()
    return _executor
