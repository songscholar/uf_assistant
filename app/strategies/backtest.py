"""
UF Stock Assistant — Backtest Engine
Ported from QuantDinger's pattern to UF Stock Assistant's stack.

Supports:
- Indicator strategy backtest (df['buy']/df['sell'] pattern)
- Script strategy backtest (on_bar event-driven)
- Multi-timeframe backtest (signal TF + execution TF)
- Risk controls: stop loss, take profit, trailing stop
- Position scaling: trendAdd, dcaAdd, trendReduce, adverseReduce
- Performance metrics: Sharpe, max drawdown, profit factor, etc.
"""

from __future__ import annotations

import json
import math
import time
import traceback
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.core.logging import get_logger
from app.core.safe_exec import safe_exec_code, validate_code_safety
from app.strategies.code_quality import analyze_indicator_code_quality
from app.strategies.indicator_params import IndicatorParamsParser, StrategyConfigParser
from app.strategies.models import BacktestEquityPoint, BacktestRun, BacktestTrade
from app.strategies.script_runtime import (
    ScriptBar,
    ScriptPosition,
    StrategyScriptContext,
    compile_strategy_script_handlers,
)

logger = get_logger("app.strategies.backtest")

# =============================================================================
# Constants
# =============================================================================

_KLINE_CACHE_MAX = 64
_KLINE_TTL_SECONDS = 300       # 5 min for klines
_OTHER_TTL_SECONDS = 1800      # 30 min for other data
_MAX_CALL_DEPTH = 5
_MIN_BARS_FOR_BACKTEST = 30
_EQUITY_CURVE_MAX_POINTS = 500
_RISK_FREE_RATE = 0.03         # annualized

_ANNUALIZE_FACTORS: dict[str, float] = {
    "1D": 252.0,
    "1W": 52.0,
    "1H": 6048.0,
    "4H": 1512.0,
    "5m": 252.0 * 78,   # approx trading minutes per year / 5
    "15m": 252.0 * 26,
    "30m": 252.0 * 13,
    "1m": 252.0 * 240,
}

_MTF_CONFIG: dict[str, int] = {
    "max_1m_days": 15,
    "max_5m_days": 365,
}

# =============================================================================
# In-memory TTL Cache with LRU Eviction
# =============================================================================


class _KlineCache:
    """In-memory TTL cache with LRU eviction for kline and auxiliary data."""

    def __init__(self, max_entries: int = _KLINE_CACHE_MAX) -> None:
        self._max = max_entries
        self._store: OrderedDict[str, Tuple[float, Any, float]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        """Return cached value if present and not expired; None otherwise."""
        entry = self._store.get(key)
        if entry is None:
            return None
        expires, value, _ts = entry
        if time.time() > expires:
            # expired
            del self._store[key]
            return None
        # move to end (most recently used)
        self._store.move_to_end(key)
        return value

    def set(self, key: str, data: Any, ttl: float = _KLINE_TTL_SECONDS) -> None:
        """Insert or update a cache entry with the given TTL in seconds."""
        if key in self._store:
            del self._store[key]
        elif len(self._store) >= self._max:
            # evict least recently used
            self._store.popitem(last=False)
        self._store[key] = (time.time() + ttl, data, time.time())

    def clear(self) -> None:
        """Remove all entries from the cache."""
        self._store.clear()


# =============================================================================
# Built-in Technical Indicator Helpers
# =============================================================================


def _sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=period, min_periods=period).mean()


def _ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_val = 100.0 - (100.0 / (1.0 + rs))
    return rsi_val


def _macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """MACD (line, signal, histogram)."""
    ema_fast = _ema(series, fast)
    ema_slow = _ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _boll(
    series: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands (upper, middle, lower)."""
    middle = _sma(series, period)
    rolling_std = series.rolling(window=period, min_periods=period).std()
    upper = middle + std_dev * rolling_std
    lower = middle - std_dev * rolling_std
    return upper, middle, lower


def _atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Average True Range."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return true_range.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


def _crossover(series_a: pd.Series, series_b: pd.Series) -> pd.Series:
    """True when series_a crosses above series_b (current > b, previous <= b)."""
    return (series_a > series_b) & (series_a.shift(1) <= series_b.shift(1))


def _crossunder(series_a: pd.Series, series_b: pd.Series) -> pd.Series:
    """True when series_a crosses below series_b (current < b, previous >= b)."""
    return (series_a < series_b) & (series_a.shift(1) >= series_b.shift(1))


# =============================================================================
# Indicator Code Execution (Sandbox)
# =============================================================================


def _build_indicator_builtins(
    call_indicator: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Build the namespace of helper functions available to indicator code."""
    ns: dict[str, Any] = {
        "SMA": _sma,
        "EMA": _ema,
        "RSI": _rsi,
        "MACD": _macd,
        "BOLL": _boll,
        "ATR": _atr,
        "CROSSOVER": _crossover,
        "CROSSUNDER": _crossunder,
    }
    if call_indicator is not None:
        ns["call_indicator"] = call_indicator
    return ns


def _execute_indicator(
    code: str,
    kline_df: pd.DataFrame,
    params: dict[str, Any] | None = None,
    depth: int = 0,
    indicator_caller=None,
) -> dict[str, Any]:
    """
    Execute indicator code in a sandbox.

    The code should populate ``df['buy']`` and ``df['sell']`` boolean columns,
    or an ``output`` dict with those keys.

    Args:
        code: Python indicator source code.
        kline_df: DataFrame with OHLCV columns.
        params: Optional indicator parameters.
        depth: Current recursive call depth (for ``call_indicator``).
        indicator_caller: Optional IndicatorCaller instance for DB-aware recursion.

    Returns:
        dict with 'buy' and 'sell' boolean Series, or 'error' key on failure.
    """
    if depth >= _MAX_CALL_DEPTH:
        return {"error": f"Maximum indicator call depth ({_MAX_CALL_DEPTH}) exceeded"}

    is_safe, err = validate_code_safety(code)
    if not is_safe:
        return {"error": f"Unsafe indicator code: {err}"}

    df = kline_df.copy()

    # Recursive call_indicator support
    def call_indicator(name_or_code: str, **kwargs: Any) -> dict[str, Any]:
        """Call another indicator from within indicator code."""
        # 如果提供了 IndicatorCaller，优先使用它（支持 DB 查询 + 环形检测）
        if indicator_caller is not None:
            return indicator_caller.call_indicator(
                indicator_ref=name_or_code,
                df=kline_df,
                params=kwargs,
                _depth=depth + 1,
            )
        # 降级到简单的递归执行（内联代码字符串）
        return _execute_indicator(
            code=name_or_code,
            kline_df=kline_df,
            params=kwargs,
            depth=depth + 1,
        )

    builtins_ns = _build_indicator_builtins(call_indicator=call_indicator)
    exec_globals: dict[str, Any] = {
        "__builtins__": {},
        "np": np,
        "pd": pd,
        "df": df,
        "params": params or {},
        **builtins_ns,
    }

    # Validate and add safe builtins
    is_safe_builtins, err2 = validate_code_safety(code)
    if not is_safe_builtins:
        return {"error": f"Code safety check failed: {err2}"}

    from app.core.safe_exec import build_safe_builtins

    exec_globals["__builtins__"] = build_safe_builtins()
    exec_globals["__builtins__"].update(builtins_ns)

    try:
        result = safe_exec_code(
            code=code,
            exec_globals=exec_globals,
            exec_locals=exec_globals,
            timeout=30,
        )
        if not result["success"]:
            return {"error": result.get("error", "Indicator execution failed")}

        # Extract output from the execution environment
        output = exec_globals.get("output", {})
        buy_series = None
        sell_series = None

        if isinstance(output, dict):
            buy_series = output.get("buy")
            sell_series = output.get("sell")

        # Fallback: check df columns
        if buy_series is None and "buy" in df.columns:
            buy_series = df["buy"]
        if sell_series is None and "sell" in df.columns:
            sell_series = df["sell"]

        if buy_series is None or sell_series is None:
            return {"error": "Indicator code did not produce buy/sell signals"}

        # Ensure boolean type and proper index
        buy_arr = pd.Series(buy_series, index=kline_df.index).fillna(False).astype(bool)
        sell_arr = pd.Series(sell_series, index=kline_df.index).fillna(False).astype(bool)

        return {"buy": buy_arr, "sell": sell_arr}

    except Exception as exc:
        logger.error("indicator_execution_error", error=str(exc))
        return {"error": f"Indicator execution error: {exc}"}


# =============================================================================
# Script Strategy Backtest
# =============================================================================


def _execute_script_strategy(
    code: str,
    kline_df: pd.DataFrame,
    initial_capital: float,
    commission: float,
    slippage: float,
    leverage: int,
    trade_direction: str,
    strategy_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Run a backtest for a script-style strategy (on_bar event-driven).

    Args:
        code: Python script defining on_bar(ctx, bar).
        kline_df: DataFrame with OHLCV columns.
        initial_capital: Starting capital.
        commission: Commission rate (e.g., 0.001 = 0.1%).
        slippage: Slippage rate.
        leverage: Leverage multiplier.
        trade_direction: 'long', 'short', or 'both'.
        strategy_config: Optional strategy configuration from @strategy annotations.

    Returns:
        dict with 'trades', 'equity_curve', 'buy_count', 'sell_count', or 'error'.
    """
    try:
        on_init, on_bar = compile_strategy_script_handlers(code)
    except (ValueError, RuntimeError) as exc:
        return {"error": f"Script compilation failed: {exc}"}

    if kline_df.empty:
        return {"error": "No kline data available"}

    # Build context
    ctx = StrategyScriptContext(bars_df=kline_df, initial_balance=initial_capital)

    # Apply strategy config
    cfg = strategy_config or {}
    entry_pct = cfg.get("entryPct", 1.0)
    stop_loss_pct = cfg.get("stopLossPct", 0.0)
    take_profit_pct = cfg.get("takeProfitPct", 0.0)
    trailing_enabled = cfg.get("trailingEnabled", False)
    trailing_stop_pct = cfg.get("trailingStopPct", 0.02)
    trailing_activation_pct = cfg.get("trailingActivationPct", 0.03)

    # Parse params from code
    declared_params = IndicatorParamsParser.parse_params(code)
    merged_params = IndicatorParamsParser.merge_params(declared_params, cfg.get("params", {}))

    # Initialize params in context
    for p_name, p_val in merged_params.items():
        ctx._params[p_name] = p_val

    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    buy_count = 0
    sell_count = 0
    position = ScriptPosition()
    capital = initial_capital
    highest_price = 0.0
    lowest_price = float("inf")

    # Run on_init if present
    if on_init is not None:
        try:
            on_init(ctx)
        except Exception as exc:
            logger.warning("script_on_init_error", error=str(exc))

    total_bars = len(kline_df)
    for i in range(total_bars):
        ctx.current_index = i
        row = kline_df.iloc[i]

        bar = ScriptBar(
            open=float(row.get("open", 0)),
            high=float(row.get("high", 0)),
            low=float(row.get("low", 0)),
            close=float(row.get("close", 0)),
            volume=float(row.get("volume", 0)),
            timestamp=str(row.get("time", row.name)),
        )

        bar_time = str(row.get("time", row.name))

        # Track high/low for trailing stop
        if position:
            if position["side"] == "long":
                highest_price = max(highest_price, bar["high"])
                current_pnl_pct = (bar["close"] - position["entry_price"]) / max(position["entry_price"], 1e-10)
            elif position["side"] == "short":
                lowest_price = min(lowest_price, bar["low"])
                current_pnl_pct = (position["entry_price"] - bar["close"]) / max(position["entry_price"], 1e-10)

            # Risk controls
            if position:
                closed_by_risk = False
                entry_p = position["entry_price"]
                pos_size = position["size"]

                # Stop loss check
                if stop_loss_pct > 0:
                    if position["side"] == "long":
                        sl_price = entry_p * (1 - stop_loss_pct / max(leverage, 1))
                        if bar["low"] <= sl_price:
                            exit_price = sl_price
                            pnl = (exit_price - entry_p) * pos_size * leverage
                            commission_cost = exit_price * pos_size * commission
                            capital += pnl - commission_cost
                            trades.append({
                                "time": bar_time,
                                "type": "close_long",
                                "price": exit_price,
                                "amount": pos_size,
                                "profit": pnl - commission_cost,
                                "balance": capital,
                                "reason": "stop_loss",
                            })
                            sell_count += 1
                            position.clear_position()
                            closed_by_risk = True
                    elif position["side"] == "short":
                        sl_price = entry_p * (1 + stop_loss_pct / max(leverage, 1))
                        if bar["high"] >= sl_price:
                            exit_price = sl_price
                            pnl = (entry_p - exit_price) * pos_size * leverage
                            commission_cost = exit_price * pos_size * commission
                            capital += pnl - commission_cost
                            trades.append({
                                "time": bar_time,
                                "type": "close_short",
                                "price": exit_price,
                                "amount": pos_size,
                                "profit": pnl - commission_cost,
                                "balance": capital,
                                "reason": "stop_loss",
                            })
                            buy_count += 1
                            position.clear_position()
                            closed_by_risk = True

                # Take profit check
                if not closed_by_risk and take_profit_pct > 0:
                    if position["side"] == "long":
                        tp_price = entry_p * (1 + take_profit_pct / max(leverage, 1))
                        if bar["high"] >= tp_price:
                            exit_price = tp_price
                            pnl = (exit_price - entry_p) * pos_size * leverage
                            commission_cost = exit_price * pos_size * commission
                            capital += pnl - commission_cost
                            trades.append({
                                "time": bar_time,
                                "type": "close_long",
                                "price": exit_price,
                                "amount": pos_size,
                                "profit": pnl - commission_cost,
                                "balance": capital,
                                "reason": "take_profit",
                            })
                            sell_count += 1
                            position.clear_position()
                            closed_by_risk = True
                    elif position["side"] == "short":
                        tp_price = entry_p * (1 - take_profit_pct / max(leverage, 1))
                        if bar["low"] <= tp_price:
                            exit_price = tp_price
                            pnl = (entry_p - exit_price) * pos_size * leverage
                            commission_cost = exit_price * pos_size * commission
                            capital += pnl - commission_cost
                            trades.append({
                                "time": bar_time,
                                "type": "close_short",
                                "price": exit_price,
                                "amount": pos_size,
                                "profit": pnl - commission_cost,
                                "balance": capital,
                                "reason": "take_profit",
                            })
                            buy_count += 1
                            position.clear_position()
                            closed_by_risk = True

                # Trailing stop check
                if not closed_by_risk and trailing_enabled and position:
                    if position["side"] == "long" and current_pnl_pct >= trailing_activation_pct:
                        trail_price = highest_price * (1 - trailing_stop_pct)
                        if bar["low"] <= trail_price and trail_price > entry_p:
                            exit_price = trail_price
                            pnl = (exit_price - entry_p) * pos_size * leverage
                            commission_cost = exit_price * pos_size * commission
                            capital += pnl - commission_cost
                            trades.append({
                                "time": bar_time,
                                "type": "close_long",
                                "price": exit_price,
                                "amount": pos_size,
                                "profit": pnl - commission_cost,
                                "balance": capital,
                                "reason": "trailing_stop",
                            })
                            sell_count += 1
                            position.clear_position()
                    elif position["side"] == "short" and current_pnl_pct >= trailing_activation_pct:
                        trail_price = lowest_price * (1 + trailing_stop_pct)
                        if bar["high"] >= trail_price and trail_price < entry_p:
                            exit_price = trail_price
                            pnl = (entry_p - exit_price) * pos_size * leverage
                            commission_cost = exit_price * pos_size * commission
                            capital += pnl - commission_cost
                            trades.append({
                                "time": bar_time,
                                "type": "close_short",
                                "price": exit_price,
                                "amount": pos_size,
                                "profit": pnl - commission_cost,
                                "balance": capital,
                                "reason": "trailing_stop",
                            })
                            buy_count += 1
                            position.clear_position()

        # Clear orders before calling on_bar
        ctx._orders.clear()

        # Call on_bar
        try:
            on_bar(ctx, bar)
        except Exception as exc:
            logger.warning("script_on_bar_error", bar_index=i, error=str(exc))
            continue

        # Process orders
        for order in ctx._orders:
            action = order.get("action")

            if action == "buy" and not position:
                if trade_direction in ("long", "both"):
                    price = float(order["price"]) if order.get("price") is not None else bar["close"]
                    price *= (1 + slippage)
                    amount_pct = float(order["amount"]) if order.get("amount") is not None else entry_pct
                    amount = (capital * amount_pct) / max(price, 1e-10)

                    if amount > 0 and capital >= price * amount * commission:
                        entry_cost = price * amount * commission
                        capital -= entry_cost
                        position.open_position("long", price, amount)
                        highest_price = price
                        buy_count += 1
                        trades.append({
                            "time": bar_time,
                            "type": "open_long",
                            "price": price,
                            "amount": amount,
                            "profit": 0,
                            "balance": capital,
                        })

            elif action == "sell" and not position:
                if trade_direction in ("short", "both"):
                    price = float(order["price"]) if order.get("price") is not None else bar["close"]
                    price *= (1 - slippage)
                    amount_pct = float(order["amount"]) if order.get("amount") is not None else entry_pct
                    amount = (capital * amount_pct) / max(price, 1e-10)

                    if amount > 0:
                        entry_cost = price * amount * commission
                        capital -= entry_cost
                        position.open_position("short", price, amount)
                        lowest_price = price
                        sell_count += 1
                        trades.append({
                            "time": bar_time,
                            "type": "open_short",
                            "price": price,
                            "amount": amount,
                            "profit": 0,
                            "balance": capital,
                        })

            elif action == "close" and position:
                price = bar["close"]
                entry_p = position["entry_price"]
                pos_size = position["size"]

                if position["side"] == "long":
                    pnl = (price - entry_p) * pos_size * leverage
                else:
                    pnl = (entry_p - price) * pos_size * leverage

                commission_cost = price * pos_size * commission
                capital += pnl - commission_cost

                close_type = "close_long" if position["side"] == "long" else "close_short"
                if position["side"] == "long":
                    sell_count += 1
                else:
                    buy_count += 1

                trades.append({
                    "time": bar_time,
                    "type": close_type,
                    "price": price,
                    "amount": pos_size,
                    "profit": pnl - commission_cost,
                    "balance": capital,
                })
                position.clear_position()

        # Calculate equity for this bar
        unrealized = 0.0
        if position:
            if position["side"] == "long":
                unrealized = (bar["close"] - position["entry_price"]) * position["size"] * leverage
            elif position["side"] == "short":
                unrealized = (position["entry_price"] - bar["close"]) * position["size"] * leverage

        current_equity = capital + unrealized
        equity_curve.append({"timestamp": bar_time, "equity": current_equity})

        # Liquidation check
        if current_equity < 1.0:
            logger.warning("liquidation_detected", bar_index=i, equity=current_equity)
            if position:
                position.clear_position()
            capital = 0.0
            break

    # Force close at backtest end
    if position:
        last_row = kline_df.iloc[-1]
        price = float(last_row["close"])
        entry_p = position["entry_price"]
        pos_size = position["size"]
        bar_time = str(last_row.get("time", last_row.name))

        if position["side"] == "long":
            pnl = (price - entry_p) * pos_size * leverage
        else:
            pnl = (entry_p - price) * pos_size * leverage

        commission_cost = price * pos_size * commission
        capital += pnl - commission_cost

        close_type = "close_long" if position["side"] == "long" else "close_short"
        if position["side"] == "long":
            sell_count += 1
        else:
            buy_count += 1

        trades.append({
            "time": bar_time,
            "type": close_type,
            "price": price,
            "amount": pos_size,
            "profit": pnl - commission_cost,
            "balance": capital,
            "reason": "force_close",
        })
        position.clear_position()

        # Update final equity
        equity_curve.append({"timestamp": bar_time, "equity": capital})

    return {
        "trades": trades,
        "equity_curve": equity_curve,
        "buy_count": buy_count,
        "sell_count": sell_count,
    }


# =============================================================================
# Signal Normalization
# =============================================================================


def _normalize_signals(
    buy: pd.Series,
    sell: pd.Series,
    close: pd.Series,
    trade_direction: str,
    anti_repaint_mode: str = "confirmed",
) -> dict[str, pd.Series]:
    """
    Convert buy/sell boolean Series into 4-way signals.

    Produces: open_long, close_long, open_short, close_short.

    Anti-repainting modes:
    - confirmed: use second-to-last bar signal (safer, no repaint)
    - aggressive: use last bar signal (may repaint)

    Args:
        buy: Boolean Series for buy signals.
        sell: Boolean Series for sell signals.
        close: Close price Series.
        trade_direction: 'long', 'short', or 'both'.
        anti_repaint_mode: 'confirmed' or 'aggressive'.

    Returns:
        dict with 'open_long', 'close_long', 'open_short', 'close_short' boolean Series.
    """
    n = len(buy)
    open_long = pd.Series(False, index=buy.index)
    close_long = pd.Series(False, index=buy.index)
    open_short = pd.Series(False, index=buy.index)
    close_short = pd.Series(False, index=buy.index)

    in_long = False
    in_short = False

    # Determine effective length for anti-repaint
    effective_len = n - 1 if anti_repaint_mode == "confirmed" and n > 1 else n

    for i in range(effective_len):
        b = bool(buy.iloc[i]) if not pd.isna(buy.iloc[i]) else False
        s = bool(sell.iloc[i]) if not pd.isna(sell.iloc[i]) else False

        if b and not in_long:
            if trade_direction in ("long", "both"):
                if in_short:
                    close_short.iloc[i] = True
                    in_short = False
                open_long.iloc[i] = True
                in_long = True
        elif s and in_long:
            close_long.iloc[i] = True
            in_long = False

        if s and not in_short:
            if trade_direction in ("short", "both"):
                if in_long:
                    close_long.iloc[i] = True
                    in_long = False
                open_short.iloc[i] = True
                in_short = True
        elif b and in_short:
            close_short.iloc[i] = True
            in_short = False

    return {
        "open_long": open_long,
        "close_long": close_long,
        "open_short": open_short,
        "close_short": close_short,
    }


# =============================================================================
# Trading Simulation (New Format)
# =============================================================================


def _simulate_trading_new_format(
    kline_df: pd.DataFrame,
    signals: dict[str, pd.Series],
    initial_capital: float,
    commission: float,
    leverage: int,
    strategy_config: dict[str, Any] | None = None,
    execution_timing: str = "next_bar_open",
) -> dict[str, Any]:
    """
    Simulate trading from 4-way signals with risk controls and position scaling.

    Args:
        kline_df: DataFrame with OHLCV columns.
        signals: dict with open_long/close_long/open_short/close_short boolean Series.
        initial_capital: Starting capital.
        commission: Commission rate.
        leverage: Leverage multiplier.
        strategy_config: Strategy configuration (stop loss, take profit, etc.).
        execution_timing: 'next_bar_open' or 'same_bar_close'.

    Returns:
        dict with 'trades', 'equity_curve', 'buy_count', 'sell_count'.
    """
    cfg = strategy_config or {}
    stop_loss_pct = cfg.get("stopLossPct", 0.0)
    take_profit_pct = cfg.get("takeProfitPct", 0.0)
    trailing_enabled = cfg.get("trailingEnabled", False)
    trailing_stop_pct = cfg.get("trailingStopPct", 0.02)
    trailing_activation_pct = cfg.get("trailingActivationPct", 0.03)
    entry_pct = cfg.get("entryPct", 1.0)

    # Position scaling config
    trend_add = cfg.get("trendAdd", {})
    dca_add = cfg.get("dcaAdd", {})
    trend_reduce = cfg.get("trendReduce", {})
    adverse_reduce = cfg.get("adverseReduce", {})

    total_bars = len(kline_df)
    if total_bars < 2:
        return {"trades": [], "equity_curve": [], "buy_count": 0, "sell_count": 0}

    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    buy_count = 0
    sell_count = 0

    capital = initial_capital
    position_side: str = ""  # 'long' or 'short' or ''
    position_size: float = 0.0
    entry_price: float = 0.0
    highest_since_entry: float = 0.0
    lowest_since_entry: float = float("inf")
    add_count: int = 0  # how many times we added to position

    open_long = signals["open_long"]
    close_long = signals["close_long"]
    open_short = signals["open_short"]
    close_short = signals["close_short"]

    def _get_exec_price(bar: pd.Series, side: str) -> float:
        """Get execution price based on timing mode."""
        if execution_timing == "same_bar_close":
            return float(bar["close"])
        else:  # next_bar_open — we're called from the next bar
            return float(bar["open"])

    def _close_position(price: float, bar_time: str, reason: str = "signal") -> None:
        nonlocal capital, position_side, position_size, entry_price, add_count
        nonlocal buy_count, sell_count

        if position_side == "long":
            pnl = (price - entry_price) * position_size * leverage
        else:
            pnl = (entry_price - price) * position_size * leverage

        comm_cost = price * position_size * commission
        capital += pnl - comm_cost

        close_type = "close_long" if position_side == "long" else "close_short"
        if position_side == "long":
            sell_count += 1
        else:
            buy_count += 1

        trades.append({
            "time": bar_time,
            "type": close_type,
            "price": round(price, 6),
            "amount": round(position_size, 6),
            "profit": round(pnl - comm_cost, 6),
            "balance": round(capital, 6),
            "reason": reason,
        })
        position_side = ""
        position_size = 0.0
        entry_price = 0.0
        add_count = 0

    def _open_position(side: str, price: float, bar_time: str) -> None:
        nonlocal capital, position_side, position_size, entry_price
        nonlocal highest_since_entry, lowest_since_entry, buy_count, sell_count, add_count

        adj_price = price * (1 + commission) if side == "long" else price * (1 - commission)
        amount = (capital * entry_pct) / max(adj_price, 1e-10)

        if amount <= 0:
            return

        comm_cost = adj_price * amount * commission
        if capital < comm_cost:
            return

        capital -= comm_cost
        position_side = side
        position_size = amount
        entry_price = adj_price
        highest_since_entry = adj_price
        lowest_since_entry = adj_price
        add_count = 0

        open_type = "open_long" if side == "long" else "open_short"
        if side == "long":
            buy_count += 1
        else:
            sell_count += 1

        trades.append({
            "time": bar_time,
            "type": open_type,
            "price": round(adj_price, 6),
            "amount": round(amount, 6),
            "profit": 0,
            "balance": round(capital, 6),
        })

    def _add_to_position(price: float, pct: float, bar_time: str, reason: str) -> None:
        nonlocal capital, position_size, entry_price, add_count

        adj_price = price * (1 + commission) if position_side == "long" else price * (1 - commission)
        add_amount = (capital * pct) / max(adj_price, 1e-10)

        if add_amount <= 0:
            return

        comm_cost = adj_price * add_amount * commission
        if capital < comm_cost:
            return

        capital -= comm_cost
        # Weighted average entry price
        total_cost = entry_price * position_size + adj_price * add_amount
        position_size += add_amount
        entry_price = total_cost / max(position_size, 1e-10)
        add_count += 1

        add_type = "add_long" if position_side == "long" else "add_short"
        trades.append({
            "time": bar_time,
            "type": add_type,
            "price": round(adj_price, 6),
            "amount": round(add_amount, 6),
            "profit": 0,
            "balance": round(capital, 6),
            "reason": reason,
        })

    def _reduce_position(price: float, pct: float, bar_time: str, reason: str) -> None:
        nonlocal capital, position_size, entry_price

        reduce_amount = position_size * pct
        if reduce_amount <= 0:
            return

        if position_side == "long":
            pnl = (price - entry_price) * reduce_amount * leverage
        else:
            pnl = (entry_price - price) * reduce_amount * leverage

        comm_cost = price * reduce_amount * commission
        capital += pnl - comm_cost

        reduce_type = "reduce_long" if position_side == "long" else "reduce_short"
        trades.append({
            "time": bar_time,
            "type": reduce_type,
            "price": round(price, 6),
            "amount": round(reduce_amount, 6),
            "profit": round(pnl - comm_cost, 6),
            "balance": round(capital, 6),
            "reason": reason,
        })

        position_size -= reduce_amount
        if position_size < 1e-12:
            position_side = ""
            position_size = 0.0
            entry_price = 0.0

    # Main simulation loop
    for i in range(1, total_bars):
        bar = kline_df.iloc[i]
        prev_bar = kline_df.iloc[i - 1]
        bar_time = str(bar.get("time", bar.name))

        # Determine execution price
        if execution_timing == "next_bar_open":
            exec_price = float(bar["open"])
        else:
            exec_price = float(prev_bar["close"])

        bar_high = float(bar["high"])
        bar_low = float(bar["low"])
        bar_close = float(bar["close"])

        # Update tracking for position
        if position_side:
            highest_since_entry = max(highest_since_entry, bar_high)
            lowest_since_entry = min(lowest_since_entry, bar_low)

            # Calculate current PnL percentage on margin basis
            if position_side == "long":
                current_pnl_pct = (bar_close - entry_price) / max(entry_price, 1e-10) * leverage
                margin_pnl_pct = (bar_close - entry_price) / max(entry_price, 1e-10)
            else:
                current_pnl_pct = (entry_price - bar_close) / max(entry_price, 1e-10) * leverage
                margin_pnl_pct = (entry_price - bar_close) / max(entry_price, 1e-10)

        # === Risk Controls (priority: stop_loss > trailing_stop > take_profit) ===
        risk_closed = False

        if position_side and stop_loss_pct > 0:
            # Stop loss on margin PnL basis, convert to price by dividing by leverage
            if position_side == "long":
                sl_price = entry_price * (1 - stop_loss_pct / max(leverage, 1))
                if bar_low <= sl_price:
                    _close_position(sl_price, bar_time, reason="stop_loss")
                    risk_closed = True
            else:
                sl_price = entry_price * (1 + stop_loss_pct / max(leverage, 1))
                if bar_high >= sl_price:
                    _close_position(sl_price, bar_time, reason="stop_loss")
                    risk_closed = True

        if not risk_closed and position_side and trailing_enabled:
            if position_side == "long":
                gain_pct = (highest_since_entry - entry_price) / max(entry_price, 1e-10)
                if gain_pct >= trailing_activation_pct:
                    trail_price = highest_since_entry * (1 - trailing_stop_pct)
                    if bar_low <= trail_price and trail_price > entry_price:
                        _close_position(trail_price, bar_time, reason="trailing_stop")
                        risk_closed = True
            else:
                gain_pct = (entry_price - lowest_since_entry) / max(entry_price, 1e-10)
                if gain_pct >= trailing_activation_pct:
                    trail_price = lowest_since_entry * (1 + trailing_stop_pct)
                    if bar_high >= trail_price and trail_price < entry_price:
                        _close_position(trail_price, bar_time, reason="trailing_stop")
                        risk_closed = True

        if not risk_closed and position_side and take_profit_pct > 0:
            if position_side == "long":
                tp_price = entry_price * (1 + take_profit_pct / max(leverage, 1))
                if bar_high >= tp_price:
                    _close_position(tp_price, bar_time, reason="take_profit")
                    risk_closed = True
            else:
                tp_price = entry_price * (1 - take_profit_pct / max(leverage, 1))
                if bar_low <= tp_price:
                    _close_position(tp_price, bar_time, reason="take_profit")
                    risk_closed = True

        # === Position Scaling ===
        if not risk_closed and position_side:
            # Trend Add
            if trend_add and not risk_closed:
                ta_pct = trend_add.get("pct", 0.1)
                ta_trigger = trend_add.get("triggerPct", 0.02)
                ta_max = trend_add.get("maxAdds", 3)
                if position_side == "long":
                    gain = (bar_close - entry_price) / max(entry_price, 1e-10)
                else:
                    gain = (entry_price - bar_close) / max(entry_price, 1e-10)
                if gain >= ta_trigger and add_count < ta_max:
                    _add_to_position(exec_price, ta_pct, bar_time, reason="trend_add")

            # DCA Add
            if dca_add and not risk_closed:
                da_pct = dca_add.get("pct", 0.1)
                da_trigger = dca_add.get("dropPct", 0.05)
                da_max = dca_add.get("maxAdds", 3)
                if position_side == "long":
                    loss = (entry_price - bar_close) / max(entry_price, 1e-10)
                else:
                    loss = (bar_close - entry_price) / max(entry_price, 1e-10)
                if loss >= da_trigger and add_count < da_max:
                    _add_to_position(exec_price, da_pct, bar_time, reason="dca_add")

            # Trend Reduce
            if trend_reduce and not risk_closed:
                tr_pct = trend_reduce.get("pct", 0.25)
                tr_trigger = trend_reduce.get("triggerPct", 0.05)
                if position_side == "long":
                    gain = (bar_close - entry_price) / max(entry_price, 1e-10)
                else:
                    gain = (entry_price - bar_close) / max(entry_price, 1e-10)
                if gain >= tr_trigger:
                    _reduce_position(exec_price, tr_pct, bar_time, reason="trend_reduce")

            # Adverse Reduce
            if adverse_reduce and not risk_closed:
                ar_pct = adverse_reduce.get("pct", 0.25)
                ar_trigger = adverse_reduce.get("triggerPct", 0.03)
                if position_side == "long":
                    loss = (entry_price - bar_close) / max(entry_price, 1e-10)
                else:
                    loss = (bar_close - entry_price) / max(entry_price, 1e-10)
                if loss >= ar_trigger:
                    _reduce_position(exec_price, ar_pct, bar_time, reason="adverse_reduce")

        # === Signal-based actions (at execution price) ===
        ol = bool(open_long.iloc[i]) if not pd.isna(open_long.iloc[i]) else False
        cl = bool(close_long.iloc[i]) if not pd.isna(close_long.iloc[i]) else False
        os_ = bool(open_short.iloc[i]) if not pd.isna(open_short.iloc[i]) else False
        cs = bool(close_short.iloc[i]) if not pd.isna(close_short.iloc[i]) else False

        if cl and position_side == "long":
            _close_position(exec_price, bar_time, reason="signal")
        elif cs and position_side == "short":
            _close_position(exec_price, bar_time, reason="signal")

        if ol and not position_side:
            _open_position("long", exec_price, bar_time)
        elif os_ and not position_side:
            _open_position("short", exec_price, bar_time)

        # === Calculate equity ===
        unrealized = 0.0
        if position_side == "long":
            unrealized = (bar_close - entry_price) * position_size * leverage
        elif position_side == "short":
            unrealized = (entry_price - bar_close) * position_size * leverage

        current_equity = capital + unrealized
        equity_curve.append({"timestamp": bar_time, "equity": round(current_equity, 6)})

        # Liquidation check
        if current_equity < 1.0:
            logger.warning("liquidation_detected", bar_index=i, equity=current_equity)
            position_side = ""
            position_size = 0.0
            capital = 0.0
            break

    # Force close at end
    if position_side:
        last_row = kline_df.iloc[-1]
        close_price = float(last_row["close"])
        bar_time = str(last_row.get("time", last_row.name))
        _close_position(close_price, bar_time, reason="force_close")
        equity_curve.append({"timestamp": bar_time, "equity": round(capital, 6)})

    return {
        "trades": trades,
        "equity_curve": equity_curve,
        "buy_count": buy_count,
        "sell_count": sell_count,
    }


# =============================================================================
# Metrics Calculation
# =============================================================================


def _calculate_max_drawdown(values: list[float]) -> float:
    """
    Calculate maximum drawdown (peak-to-trough) as a fraction.

    Args:
        values: List of equity values.

    Returns:
        Maximum drawdown as a decimal (e.g., 0.15 = 15%).
    """
    if len(values) < 2:
        return 0.0

    peak = values[0]
    max_dd = 0.0

    for v in values:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd

    return round(max_dd, 6)


def _calculate_sharpe(
    values: list[float],
    timeframe: str = "1D",
    risk_free_rate: float = _RISK_FREE_RATE,
) -> float:
    """
    Calculate annualized Sharpe ratio.

    Args:
        values: List of equity values.
        timeframe: Data timeframe (e.g., '1D', '1W', '1H').
        risk_free_rate: Annualized risk-free rate.

    Returns:
        Annualized Sharpe ratio.
    """
    if len(values) < 10:
        return 0.0

    returns = []
    for i in range(1, len(values)):
        if values[i - 1] > 0:
            returns.append((values[i] - values[i - 1]) / values[i - 1])

    if not returns:
        return 0.0

    arr = np.array(returns)
    mean_r = float(np.mean(arr))
    std_r = float(np.std(arr, ddof=1))

    if std_r < 1e-12:
        return 0.0

    annualize = _ANNUALIZE_FACTORS.get(timeframe, 252.0)
    periods_per_year = annualize

    # Annualized Sharpe
    excess_return = mean_r * periods_per_year - risk_free_rate
    annualized_std = std_r * math.sqrt(periods_per_year)

    sharpe = excess_return / annualized_std if annualized_std > 0 else 0.0
    return round(sharpe, 4)


def _calculate_metrics(
    equity_curve: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    initial_capital: float,
    commission: float,
    timeframe: str = "1D",
) -> dict[str, Any]:
    """
    Calculate comprehensive backtest performance metrics.

    Args:
        equity_curve: List of {timestamp, equity} dicts.
        trades: List of trade dicts.
        initial_capital: Starting capital.
        commission: Commission rate.
        timeframe: Data timeframe.

    Returns:
        dict with all performance metrics.
    """
    values = [pt["equity"] for pt in equity_curve]

    if not values:
        return {
            "totalReturn": 0.0,
            "annualReturn": 0.0,
            "maxDrawdown": 0.0,
            "sharpeRatio": 0.0,
            "winRate": 0.0,
            "profitFactor": 0.0,
            "totalTrades": 0,
            "totalProfit": 0.0,
            "totalCommission": 0.0,
        }

    final_equity = values[-1]
    total_return = (final_equity - initial_capital) / max(initial_capital, 1e-10)

    # Annualized return
    n_bars = len(values)
    annualize = _ANNUALIZE_FACTORS.get(timeframe, 252.0)
    n_years = n_bars / max(annualize, 1.0)
    if n_years > 0 and total_return > -1:
        annual_return = (1 + total_return) ** (1 / n_years) - 1
    else:
        annual_return = total_return

    max_dd = _calculate_max_drawdown(values)
    sharpe = _calculate_sharpe(values, timeframe)

    # Trade analysis
    close_trades = [t for t in trades if t["type"] in ("close_long", "close_short")]
    total_trades = len(close_trades)
    winning = [t for t in close_trades if t.get("profit", 0) > 0]
    losing = [t for t in close_trades if t.get("profit", 0) < 0]

    win_rate = len(winning) / max(total_trades, 1)

    gross_profit = sum(t.get("profit", 0) for t in winning)
    gross_loss = abs(sum(t.get("profit", 0) for t in losing))
    profit_factor = gross_profit / max(gross_loss, 1e-10) if gross_loss > 0 else (
        float("inf") if gross_profit > 0 else 0.0
    )

    total_profit = final_equity - initial_capital
    total_commission = sum(
        t.get("price", 0) * t.get("amount", 0) * commission for t in trades
    )

    return {
        "totalReturn": round(total_return, 6),
        "annualReturn": round(annual_return, 6),
        "maxDrawdown": round(max_dd, 6),
        "sharpeRatio": round(sharpe, 4),
        "winRate": round(win_rate, 4),
        "profitFactor": round(min(profit_factor, 9999.0), 4),
        "totalTrades": total_trades,
        "totalProfit": round(total_profit, 2),
        "totalCommission": round(total_commission, 2),
    }


# =============================================================================
# Equity Curve Downsampling
# =============================================================================


def _downsample_equity(
    equity_curve: list[dict[str, Any]],
    max_points: int = _EQUITY_CURVE_MAX_POINTS,
) -> list[dict[str, Any]]:
    """
    Downsample equity curve to at most max_points using LTTB algorithm approximation.

    Args:
        equity_curve: List of {timestamp, equity} dicts.
        max_points: Maximum number of points in output.

    Returns:
        Downsampled list of {timestamp, equity} dicts.
    """
    if len(equity_curve) <= max_points:
        return equity_curve

    # Simple uniform sampling (LTTB approximation)
    n = len(equity_curve)
    step = (n - 2) / (max_points - 2)
    result: list[dict[str, Any]] = [equity_curve[0]]

    for i in range(1, max_points - 1):
        idx = int(1 + i * step)
        idx = min(idx, n - 1)
        result.append(equity_curve[idx])

    result.append(equity_curve[-1])
    return result


# =============================================================================
# NaN/Inf Cleaning
# =============================================================================


def _clean_nan_inf(obj: Any) -> Any:
    """Recursively replace NaN/Inf values with 0 or None in dicts/lists."""
    if isinstance(obj, dict):
        return {k: _clean_nan_inf(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean_nan_inf(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return 0.0
        return obj
    elif isinstance(obj, (np.floating, np.integer)):
        val = float(obj)
        if math.isnan(val) or math.isinf(val):
            return 0.0
        return val
    elif isinstance(obj, np.bool_):
        return bool(obj)
    return obj


# =============================================================================
# Data Fetching
# =============================================================================


def _fetch_kline_data(
    market: str,
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    cache: _KlineCache | None = None,
) -> pd.DataFrame:
    """
    Fetch kline data from UF's data sources.

    For stock: uses AKShare via app.tools.stock_data.
    For crypto: uses CCXT via app.tools.crypto_data.

    Args:
        market: 'stock' or 'crypto'.
        symbol: Stock code or crypto pair (e.g., '600519', 'BTC/USDT').
        timeframe: Kline period (e.g., '1D', '1W', '1h', '5m').
        start_date: Start date string (YYYY-MM-DD or YYYYMMDD).
        end_date: End date string (YYYY-MM-DD or YYYYMMDD).
        cache: Optional cache instance.

    Returns:
        DataFrame with columns: time, open, high, low, close, volume.
    """
    cache_key = f"{market}:{symbol}:{timeframe}:{start_date}:{end_date}"

    if cache is not None:
        cached = cache.get(cache_key)
        if cached is not None:
            logger.info("kline_cache_hit", key=cache_key)
            return cached

    df = pd.DataFrame()

    try:
        if market == "stock":
            from app.tools.stock_data import get_stock_history

            # Map timeframe to AKShare period
            period_map = {
                "1D": "daily",
                "daily": "daily",
                "1W": "weekly",
                "weekly": "weekly",
                "1M": "monthly",
                "monthly": "monthly",
            }
            ak_period = period_map.get(timeframe, "daily")

            raw = get_stock_history(
                symbol=symbol,
                period=ak_period,
                start=start_date.replace("-", ""),
                end=end_date.replace("-", ""),
                limit=10000,
            )
            data = json.loads(raw)
            records = data.get("data", [])

            if records:
                df = pd.DataFrame(records)
                # Normalize column names
                col_map = {
                    "date": "time",
                    "open": "open",
                    "high": "high",
                    "low": "low",
                    "close": "close",
                    "volume": "volume",
                }
                df = df.rename(columns=col_map)
                for col in ["open", "high", "low", "close", "volume"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                df["time"] = pd.to_datetime(df["time"], errors="coerce")
                df = df.dropna(subset=["time", "open", "high", "low", "close"])
                df = df.sort_values("time").reset_index(drop=True)

        elif market == "crypto":
            from app.tools.crypto_data import get_crypto_ohlcv

            # Map timeframe to CCXT format
            tf_map = {
                "1D": "1d",
                "1d": "1d",
                "1W": "1w",
                "1w": "1w",
                "1H": "1h",
                "1h": "1h",
                "4H": "4h",
                "4h": "4h",
                "5m": "5m",
                "15m": "15m",
                "30m": "30m",
                "1m": "1m",
            }
            ccxt_tf = tf_map.get(timeframe, "1d")

            # Calculate limit from date range
            start_dt = datetime.strptime(start_date.replace("-", ""), "%Y%m%d")
            end_dt = datetime.strptime(end_date.replace("-", ""), "%Y%m%d")
            days = (end_dt - start_dt).days
            tf_minutes = {"1d": 1440, "1w": 10080, "1h": 60, "4h": 240, "5m": 5, "15m": 15, "30m": 30, "1m": 1}
            minutes_per_bar = tf_minutes.get(ccxt_tf, 1440)
            estimated_bars = max(int(days * 1440 / max(minutes_per_bar, 1)), 100)
            fetch_limit = min(estimated_bars + 100, 5000)

            raw = get_crypto_ohlcv(
                symbol=symbol,
                timeframe=ccxt_tf,
                limit=fetch_limit,
            )
            records = raw.get("data", [])

            if records:
                df = pd.DataFrame(records)
                if "timestamp" in df.columns:
                    df["time"] = pd.to_datetime(df["timestamp"], unit="ms", errors="coerce")
                for col in ["open", "high", "low", "close", "volume"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna(subset=["time", "open", "high", "low", "close"])

                # Filter by date range
                start_dt_filter = pd.Timestamp(start_date)
                end_dt_filter = pd.Timestamp(end_date)
                df = df[(df["time"] >= start_dt_filter) & (df["time"] <= end_dt_filter)]
                df = df.sort_values("time").reset_index(drop=True)

    except Exception as exc:
        logger.error("kline_fetch_failed", market=market, symbol=symbol, error=str(exc))
        return pd.DataFrame()

    if cache is not None and not df.empty:
        cache.set(cache_key, df, _KLINE_TTL_SECONDS)

    return df


# =============================================================================
# Persistence
# =============================================================================


def _persist_backtest_run(
    db_session: Any,
    strategy_id: str | None,
    result: dict[str, Any],
    symbol: str,
    timeframe: str,
    strategy_type: str,
    code: str | None,
    initial_capital: float,
    commission: float,
    leverage: int,
    trade_direction: str,
    start_date: str | None,
    end_date: str | None,
    config_snapshot: dict[str, Any] | None,
) -> str:
    """
    Persist backtest run results to database.

    Args:
        db_session: SQLAlchemy Session.
        strategy_id: Optional strategy ID.
        result: Backtest result dict.
        symbol: Stock/crypto symbol.
        timeframe: Data timeframe.
        strategy_type: 'indicator' or 'script'.
        code: Strategy code.
        initial_capital: Starting capital.
        commission: Commission rate.
        leverage: Leverage.
        trade_direction: Trade direction.
        start_date: Backtest start date.
        end_date: Backtest end date.
        config_snapshot: Optional config snapshot.

    Returns:
        The run ID string.
    """
    metrics = result.get("metrics", {})

    run = BacktestRun(
        strategy_id=strategy_id,
        symbol=symbol,
        timeframe=timeframe,
        strategy_type=strategy_type,
        code=code,
        initial_capital=initial_capital,
        commission=commission,
        leverage=leverage,
        trade_direction=trade_direction,
        start_date=start_date,
        end_date=end_date,
        total_return=metrics.get("totalReturn", 0.0),
        annual_return=metrics.get("annualReturn", 0.0),
        max_drawdown=metrics.get("maxDrawdown", 0.0),
        sharpe_ratio=metrics.get("sharpeRatio", 0.0),
        win_rate=metrics.get("winRate", 0.0),
        profit_factor=metrics.get("profitFactor", 0.0),
        total_trades=metrics.get("totalTrades", 0),
        total_profit=metrics.get("totalProfit", 0.0),
        total_commission=metrics.get("totalCommission", 0.0),
        config_snapshot=config_snapshot,
    )
    db_session.add(run)
    db_session.flush()  # get run.id

    run_id: str = run.id

    # Persist trades
    for t in result.get("trades", []):
        trade = BacktestTrade(
            run_id=run_id,
            trade_time=str(t.get("time", "")),
            trade_type=str(t.get("type", "")),
            price=float(t.get("price", 0)),
            amount=float(t.get("amount", 0)),
            profit=float(t.get("profit", 0)),
            balance=float(t.get("balance", 0)),
        )
        db_session.add(trade)

    # Persist equity curve (downsampled)
    for pt in result.get("equityCurve", []):
        ep = BacktestEquityPoint(
            run_id=run_id,
            point_time=str(pt.get("timestamp", "")),
            value=float(pt.get("equity", 0)),
        )
        db_session.add(ep)

    db_session.commit()
    logger.info("backtest_persisted", run_id=run_id, trades=len(result.get("trades", [])))
    return run_id


# =============================================================================
# BacktestService — Main Entry Point
# =============================================================================


class BacktestService:
    """
    Unified backtest service for UF Stock Assistant.

    Supports:
    - Indicator strategy backtest (QuantDinger-style df['buy']/df['sell'])
    - Script strategy backtest (on_bar event-driven)
    - Multi-timeframe backtest
    - Full risk controls and position scaling
    """

    def __init__(self) -> None:
        self._kline_cache = _KlineCache()

    def run(
        self,
        indicator_code: str,
        market: str,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        initial_capital: float = 100000.0,
        commission: float = 0.001,
        leverage: int = 1,
        trade_direction: str = "long",
        strategy_config: dict[str, Any] | None = None,
        indicator_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Run an indicator strategy backtest.

        Args:
            indicator_code: Python indicator code (should produce df['buy']/df['sell']).
            market: 'stock' or 'crypto'.
            symbol: Stock code or crypto pair.
            timeframe: Data timeframe.
            start_date: Backtest start date.
            end_date: Backtest end date.
            initial_capital: Starting capital.
            commission: Commission rate.
            leverage: Leverage multiplier.
            trade_direction: 'long', 'short', or 'both'.
            strategy_config: Optional strategy config from @strategy annotations.
            indicator_params: Optional user-provided indicator parameters.

        Returns:
            dict with metrics, equityCurve, trades, buy_count, sell_count.
        """
        start_time = time.time()
        logger.info(
            "backtest_start",
            market=market,
            symbol=symbol,
            timeframe=timeframe,
            start=start_date,
            end=end_date,
            capital=initial_capital,
            leverage=leverage,
            direction=trade_direction,
        )

        # 1. Parse strategy config from code annotations
        if strategy_config is None:
            strategy_config = StrategyConfigParser.parse(indicator_code)
        # Merge trade_direction from parameter if not in config
        if "tradeDirection" not in strategy_config:
            strategy_config["tradeDirection"] = trade_direction

        # 2. Parse and merge indicator params
        declared_params = IndicatorParamsParser.parse_params(indicator_code)
        merged_params = IndicatorParamsParser.merge_params(
            declared_params, indicator_params or {}
        )

        # 3. Fetch kline data
        kline_df = self._fetch_kline_data(
            market=market,
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
        )

        if kline_df.empty:
            return _clean_nan_inf(self._empty_result("No kline data available"))

        if len(kline_df) < _MIN_BARS_FOR_BACKTEST:
            return _clean_nan_inf(self._empty_result(
                f"Insufficient data: {len(kline_df)} bars (minimum {_MIN_BARS_FOR_BACKTEST})"
            ))

        # 4. Execute indicator code
        indicator_result = _execute_indicator(
            code=indicator_code,
            kline_df=kline_df,
            params=merged_params,
        )

        if "error" in indicator_result:
            return _clean_nan_inf(self._empty_result(indicator_result["error"]))

        buy_series = indicator_result["buy"]
        sell_series = indicator_result["sell"]

        # 5. Normalize signals to 4-way
        effective_direction = strategy_config.get("tradeDirection", trade_direction)
        signals = _normalize_signals(
            buy=buy_series,
            sell=sell_series,
            close=kline_df["close"],
            trade_direction=effective_direction,
            anti_repaint_mode="confirmed",
        )

        # 6. Simulate trading
        sim_result = _simulate_trading_new_format(
            kline_df=kline_df,
            signals=signals,
            initial_capital=initial_capital,
            commission=commission,
            leverage=leverage,
            strategy_config=strategy_config,
            execution_timing="next_bar_open",
        )

        if "error" in sim_result:
            return _clean_nan_inf(self._empty_result(sim_result["error"]))

        # 7. Calculate metrics
        equity_curve = sim_result["equity_curve"]
        metrics = _calculate_metrics(
            equity_curve=equity_curve,
            trades=sim_result["trades"],
            initial_capital=initial_capital,
            commission=commission,
            timeframe=timeframe,
        )

        # 8. Downsample equity curve
        downsampled = _downsample_equity(equity_curve)

        elapsed = round(time.time() - start_time, 2)
        logger.info(
            "backtest_complete",
            symbol=symbol,
            total_return=metrics["totalReturn"],
            trades=metrics["totalTrades"],
            elapsed=elapsed,
        )

        result = {
            **metrics,
            "equityCurve": downsampled,
            "trades": sim_result["trades"],
            "buy_count": sim_result["buy_count"],
            "sell_count": sim_result["sell_count"],
            "elapsed_seconds": elapsed,
        }

        return _clean_nan_inf(result)

    def _run_script_strategy(
        self,
        code: str,
        market: str,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        initial_capital: float = 100000.0,
        commission: float = 0.001,
        slippage: float = 0.0,
        leverage: int = 1,
        trade_direction: str = "long",
        strategy_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Run a script strategy backtest (on_bar event-driven).

        Args:
            code: Python script defining on_bar(ctx, bar).
            market: 'stock' or 'crypto'.
            symbol: Stock code or crypto pair.
            timeframe: Data timeframe.
            start_date: Backtest start date.
            end_date: Backtest end date.
            initial_capital: Starting capital.
            commission: Commission rate.
            slippage: Slippage rate.
            leverage: Leverage multiplier.
            trade_direction: 'long', 'short', or 'both'.
            strategy_config: Optional strategy config.

        Returns:
            dict with metrics, equityCurve, trades, buy_count, sell_count.
        """
        start_time = time.time()
        logger.info(
            "script_backtest_start",
            market=market,
            symbol=symbol,
            timeframe=timeframe,
            start=start_date,
            end=end_date,
        )

        # Fetch kline data
        kline_df = self._fetch_kline_data(
            market=market,
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
        )

        if kline_df.empty:
            return _clean_nan_inf(self._empty_result("No kline data available"))

        if len(kline_df) < _MIN_BARS_FOR_BACKTEST:
            return _clean_nan_inf(self._empty_result(
                f"Insufficient data: {len(kline_df)} bars (minimum {_MIN_BARS_FOR_BACKTEST})"
            ))

        # Parse strategy config from code
        if strategy_config is None:
            strategy_config = StrategyConfigParser.parse(code)

        # Execute script strategy
        sim_result = _execute_script_strategy(
            code=code,
            kline_df=kline_df,
            initial_capital=initial_capital,
            commission=commission,
            slippage=slippage,
            leverage=leverage,
            trade_direction=trade_direction,
            strategy_config=strategy_config,
        )

        if "error" in sim_result:
            return _clean_nan_inf(self._empty_result(sim_result["error"]))

        # Calculate metrics
        equity_curve = sim_result["equity_curve"]
        metrics = _calculate_metrics(
            equity_curve=equity_curve,
            trades=sim_result["trades"],
            initial_capital=initial_capital,
            commission=commission,
            timeframe=timeframe,
        )

        # Downsample equity curve
        downsampled = _downsample_equity(equity_curve)

        elapsed = round(time.time() - start_time, 2)
        logger.info(
            "script_backtest_complete",
            symbol=symbol,
            total_return=metrics["totalReturn"],
            trades=metrics["totalTrades"],
            elapsed=elapsed,
        )

        result = {
            **metrics,
            "equityCurve": downsampled,
            "trades": sim_result["trades"],
            "buy_count": sim_result["buy_count"],
            "sell_count": sim_result["sell_count"],
            "elapsed_seconds": elapsed,
        }

        return _clean_nan_inf(result)

    def run_multi_timeframe(
        self,
        indicator_code: str,
        market: str,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        initial_capital: float = 100000.0,
        commission: float = 0.001,
        leverage: int = 1,
        trade_direction: str = "long",
        strategy_config: dict[str, Any] | None = None,
        indicator_params: dict[str, Any] | None = None,
        enable_mtf: bool = False,
    ) -> dict[str, Any]:
        """
        Run a multi-timeframe backtest.

        Signal timeframe generates signals, execution timeframe (1m/5m) provides
        precise simulation with intra-bar price path inference.

        MTF_CONFIG:
            max_1m_days: Maximum days of 1m data to fetch (default 15).
            max_5m_days: Maximum days of 5m data to fetch (default 365).

        Args:
            indicator_code: Indicator code for signal generation.
            market: 'stock' or 'crypto'.
            symbol: Symbol.
            timeframe: Signal timeframe (e.g., '1D', '1H').
            start_date: Backtest start date.
            end_date: Backtest end date.
            initial_capital: Starting capital.
            commission: Commission rate.
            leverage: Leverage.
            trade_direction: Trade direction.
            strategy_config: Strategy config.
            indicator_params: Indicator parameters.
            enable_mtf: Whether to enable multi-timeframe mode.

        Returns:
            dict with full backtest results.
        """
        if not enable_mtf:
            return self.run(
                indicator_code=indicator_code,
                market=market,
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                commission=commission,
                leverage=leverage,
                trade_direction=trade_direction,
                strategy_config=strategy_config,
                indicator_params=indicator_params,
            )

        start_time = time.time()
        logger.info(
            "mtf_backtest_start",
            market=market,
            symbol=symbol,
            signal_tf=timeframe,
            start=start_date,
            end=end_date,
        )

        # Determine execution timeframe
        exec_tf = "5m" if timeframe not in ("1m", "5m") else timeframe

        # Parse config
        if strategy_config is None:
            strategy_config = StrategyConfigParser.parse(indicator_code)
        if "tradeDirection" not in strategy_config:
            strategy_config["tradeDirection"] = trade_direction

        declared_params = IndicatorParamsParser.parse_params(indicator_code)
        merged_params = IndicatorParamsParser.merge_params(
            declared_params, indicator_params or {}
        )

        # Fetch signal timeframe data
        signal_df = self._fetch_kline_data(
            market=market,
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
        )

        if signal_df.empty:
            return _clean_nan_inf(self._empty_result("No signal kline data available"))

        if len(signal_df) < _MIN_BARS_FOR_BACKTEST:
            return _clean_nan_inf(self._empty_result(
                f"Insufficient signal data: {len(signal_df)} bars"
            ))

        # Generate signals on signal timeframe
        indicator_result = _execute_indicator(
            code=indicator_code,
            kline_df=signal_df,
            params=merged_params,
        )

        if "error" in indicator_result:
            return _clean_nan_inf(self._empty_result(indicator_result["error"]))

        buy_series = indicator_result["buy"]
        sell_series = indicator_result["sell"]

        effective_direction = strategy_config.get("tradeDirection", trade_direction)
        signals = _normalize_signals(
            buy=buy_series,
            sell=sell_series,
            close=signal_df["close"],
            trade_direction=effective_direction,
        )

        # Fetch execution timeframe data (with date limits based on MTF_CONFIG)
        start_dt = datetime.strptime(start_date.replace("-", ""), "%Y%m%d")
        end_dt = datetime.strptime(end_date.replace("-", ""), "%Y%m%d")
        total_days = (end_dt - start_dt).days

        if exec_tf == "1m":
            max_days = _MTF_CONFIG["max_1m_days"]
        elif exec_tf == "5m":
            max_days = _MTF_CONFIG["max_5m_days"]
        else:
            max_days = total_days

        if total_days > max_days:
            adjusted_start = end_dt - timedelta(days=max_days)
            exec_start = adjusted_start.strftime("%Y-%m-%d")
        else:
            exec_start = start_date

        exec_df = self._fetch_kline_data(
            market=market,
            symbol=symbol,
            timeframe=exec_tf,
            start_date=exec_start,
            end_date=end_date,
        )

        if exec_df.empty:
            logger.warning("mtf_exec_data_empty_fallback", exec_tf=exec_tf)
            # Fallback to signal timeframe simulation
            return self.run(
                indicator_code=indicator_code,
                market=market,
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                commission=commission,
                leverage=leverage,
                trade_direction=trade_direction,
                strategy_config=strategy_config,
                indicator_params=indicator_params,
            )

        # Map signal TF signals to execution TF bars
        # For each signal bar, find the corresponding execution bar range
        exec_signals = {
            "open_long": pd.Series(False, index=exec_df.index),
            "close_long": pd.Series(False, index=exec_df.index),
            "open_short": pd.Series(False, index=exec_df.index),
            "close_short": pd.Series(False, index=exec_df.index),
        }

        signal_times = pd.to_datetime(signal_df["time"])
        exec_times = pd.to_datetime(exec_df["time"])

        for sig_idx in range(len(signal_df)):
            sig_time = signal_times.iloc[sig_idx]

            # Find the first exec bar at or after signal time
            exec_mask = exec_times >= sig_time
            if not exec_mask.any():
                continue
            exec_idx = exec_mask.idxmax()

            for signal_key in ("open_long", "close_long", "open_short", "close_short"):
                if bool(signals[signal_key].iloc[sig_idx]):
                    # Apply signal to the next exec bar (for next_bar_open execution)
                    next_idx = exec_idx + 1
                    if next_idx < len(exec_df):
                        exec_signals[signal_key].iloc[next_idx] = True

        # Infer intra-bar price path for execution
        # Bullish bar: O -> L -> H -> C (if close > open)
        # Bearish bar: O -> H -> L -> C (if close <= open)
        # This is handled implicitly by the simulation using bar high/low

        # Simulate on execution timeframe
        sim_result = _simulate_trading_new_format(
            kline_df=exec_df,
            signals=exec_signals,
            initial_capital=initial_capital,
            commission=commission,
            leverage=leverage,
            strategy_config=strategy_config,
            execution_timing="next_bar_open",
        )

        if "error" in sim_result:
            return _clean_nan_inf(self._empty_result(sim_result["error"]))

        # Calculate metrics using exec timeframe
        equity_curve = sim_result["equity_curve"]
        metrics = _calculate_metrics(
            equity_curve=equity_curve,
            trades=sim_result["trades"],
            initial_capital=initial_capital,
            commission=commission,
            timeframe=exec_tf,
        )

        downsampled = _downsample_equity(equity_curve)

        elapsed = round(time.time() - start_time, 2)
        logger.info(
            "mtf_backtest_complete",
            symbol=symbol,
            signal_tf=timeframe,
            exec_tf=exec_tf,
            total_return=metrics["totalReturn"],
            trades=metrics["totalTrades"],
            elapsed=elapsed,
        )

        result = {
            **metrics,
            "equityCurve": downsampled,
            "trades": sim_result["trades"],
            "buy_count": sim_result["buy_count"],
            "sell_count": sim_result["sell_count"],
            "signal_timeframe": timeframe,
            "execution_timeframe": exec_tf,
            "elapsed_seconds": elapsed,
        }

        return _clean_nan_inf(result)

    def _fetch_kline_data(
        self,
        market: str,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """
        Fetch kline data from UF's data sources (delegates to module-level function).

        Args:
            market: 'stock' or 'crypto'.
            symbol: Symbol.
            timeframe: Kline period.
            start_date: Start date.
            end_date: End date.

        Returns:
            DataFrame with OHLCV columns.
        """
        return _fetch_kline_data(
            market=market,
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            cache=self._kline_cache,
        )

    def persist_run(
        self,
        db_session: Any,
        strategy_id: str | None,
        result: dict[str, Any],
    ) -> int:
        """
        Persist backtest results to database.

        Args:
            db_session: SQLAlchemy Session.
            strategy_id: Optional strategy ID.
            result: Backtest result dict (as returned by run() or _run_script_strategy()).

        Returns:
            The backtest run ID (as int for compatibility).
        """
        try:
            run_id = _persist_backtest_run(
                db_session=db_session,
                strategy_id=strategy_id,
                result=result,
                symbol=result.get("symbol", ""),
                timeframe=result.get("timeframe", "1D"),
                strategy_type=result.get("strategy_type", "indicator"),
                code=result.get("code"),
                initial_capital=result.get("initial_capital", 100000.0),
                commission=result.get("commission", 0.001),
                leverage=result.get("leverage", 1),
                trade_direction=result.get("trade_direction", "long"),
                start_date=result.get("start_date"),
                end_date=result.get("end_date"),
                config_snapshot=result.get("config_snapshot"),
            )
            return hash(run_id) % (2**31)  # return a stable int-ish id
        except Exception as exc:
            logger.error("persist_run_failed", error=str(exc))
            db_session.rollback()
            raise

    @staticmethod
    def _empty_result(error_msg: str) -> dict[str, Any]:
        """Build an empty result dict with an error message."""
        return {
            "totalReturn": 0.0,
            "annualReturn": 0.0,
            "maxDrawdown": 0.0,
            "sharpeRatio": 0.0,
            "winRate": 0.0,
            "profitFactor": 0.0,
            "totalTrades": 0,
            "totalProfit": 0.0,
            "totalCommission": 0.0,
            "equityCurve": [],
            "trades": [],
            "buy_count": 0,
            "sell_count": 0,
            "error": error_msg,
        }

    def analyze_code_quality(self, code: str) -> list[dict[str, Any]]:
        """
        Analyze indicator code quality and return hints.

        Args:
            code: Indicator Python code.

        Returns:
            List of hint dicts with severity, code, and params.
        """
        return analyze_indicator_code_quality(code)

    def clear_cache(self) -> None:
        """Clear the kline cache."""
        self._kline_cache.clear()
        logger.info("kline_cache_cleared")
