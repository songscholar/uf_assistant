"""
UF Stock Assistant — Pending Order Worker (QuantDinger parity)

Background polling thread that processes pending_orders table.
Enhanced with:
  - Stale order reclaim (90s timeout for stuck "processing" orders)
  - Priority-based ordering (priority DESC, id ASC)
  - Signal mode: notification dispatch
  - Live mode: maker-then-market execution via CCXT
  - Position reconciliation (sync_positions_best_effort)
  - apply_fill_to_local_position with weighted-average entry
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, select, update, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.logging import get_logger
from app.strategies.models import (
    PendingOrder,
    StrategyModel,
    StrategyPosition,
    StrategyTrade,
)

logger = get_logger("app.strategies.pending_order_worker")

# ── Helper functions (module-level, usable by other modules) ──────────────


def apply_fill_to_local_position(
    *,
    strategy_id: str,
    symbol: str,
    signal_type: str,
    filled: float,
    avg_price: float,
    session: Session | None = None,
) -> tuple[float | None, dict[str, Any] | None]:
    """
    Apply a fill to the local position snapshot.
    Returns (profit, updated_position_dict_or_None).
    Profit is only calculated on close/reduce fills.
    """
    sig = (signal_type or "").strip().lower()
    filled_qty = float(filled or 0.0)
    px = float(avg_price or 0.0)
    if filled_qty <= 0 or px <= 0:
        return None, None

    if "long" in sig:
        side = "long"
    elif "short" in sig:
        side = "short"
    else:
        return None, None

    is_open = sig.startswith("open_") or sig.startswith("add_")
    is_close = sig.startswith("close_") or sig.startswith("reduce_")

    close_session = False
    if session is None:
        from app.strategies.trading_executor import get_strategy_db_session
        session = get_strategy_db_session()
        close_session = True

    try:
        pos = (
            session.query(StrategyPosition)
            .filter_by(strategy_id=str(strategy_id), symbol=symbol, side=side)
            .first()
        )

        cur_size = float(pos.size or 0) if pos else 0.0
        cur_entry = float(pos.entry_price or 0) if pos else 0.0
        cur_high = float(pos.highest_price or 0) if pos else 0.0
        cur_low = float(pos.lowest_price or 0) if pos else 0.0

        profit: float | None = None
        now = datetime.now(timezone.utc)

        if is_open:
            new_size = cur_size + filled_qty
            if new_size <= 0:
                return None, None
            # Weighted average entry.
            if cur_size > 0 and cur_entry > 0:
                new_entry = (cur_size * cur_entry + filled_qty * px) / new_size
            else:
                new_entry = px
            new_high = max(cur_high or px, px)
            new_low = min(cur_low if cur_low > 0 else px, px)

            if pos is None:
                pos = StrategyPosition(
                    strategy_id=str(strategy_id),
                    symbol=symbol,
                    side=side,
                    size=new_size,
                    entry_price=new_entry,
                    amount=new_size * new_entry,
                    current_price=px,
                    highest_price=new_high,
                    lowest_price=new_low,
                    updated_at=now,
                )
                session.add(pos)
            else:
                pos.size = new_size
                pos.entry_price = new_entry
                pos.amount = new_size * new_entry
                pos.current_price = px
                pos.highest_price = new_high
                pos.lowest_price = new_low
                pos.updated_at = now
            session.commit()

            return None, {
                "side": side, "size": new_size, "entry_price": new_entry,
                "current_price": px, "highest_price": new_high, "lowest_price": new_low,
            }

        if is_close:
            # Calculate PnL.
            if cur_size > 0 and cur_entry > 0:
                close_qty = min(cur_size, filled_qty)
                if side == "long":
                    profit = (px - cur_entry) * close_qty
                else:
                    profit = (cur_entry - px) * close_qty

            new_size = cur_size - filled_qty
            if new_size <= 0.0001:
                # Fully closed.
                if pos is not None:
                    session.delete(pos)
                    session.commit()
                return profit, None

            new_high = max(cur_high or px, px)
            new_low = min(cur_low if cur_low > 0 else px, px)
            if pos is not None:
                pos.size = new_size
                pos.amount = new_size * cur_entry
                pos.current_price = px
                pos.highest_price = new_high
                pos.lowest_price = new_low
                pos.updated_at = now
                session.commit()

            return profit, {
                "side": side, "size": new_size, "entry_price": cur_entry,
                "current_price": px,
            }

        return None, None
    except Exception as exc:
        session.rollback()
        logger.warning("apply_fill_failed", error=str(exc))
        return None, None
    finally:
        if close_session:
            session.close()


def record_trade(
    *,
    strategy_id: str,
    symbol: str,
    trade_type: str,
    price: float,
    amount: float,
    commission: float = 0.0,
    profit: float = 0.0,
    value: float = 0.0,
    session: Session | None = None,
) -> None:
    """Insert a StrategyTrade row."""
    close_session = False
    if session is None:
        from app.strategies.trading_executor import get_strategy_db_session
        session = get_strategy_db_session()
        close_session = True

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
        if close_session:
            session.close()


# ── PendingOrderWorker ─────────────────────────────────────────────────────


class PendingOrderWorker:
    """
    Background thread: polls pending_orders table, processes orders.

    Signal mode: dispatch notifications via NotifierManager.
    Live mode: execute on exchange via CCXT with maker-then-market flow.
    """

    def __init__(
        self,
        db_url: str,
        poll_interval: float = 5.0,
        stale_processing_sec: int = 90,
        exchange_client: Any | None = None,
    ) -> None:
        self._poll_interval = poll_interval
        self._stale_processing_sec = stale_processing_sec
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._exchange_client = exchange_client

        # Independent DB connection pool.
        self._engine = create_engine(db_url, pool_size=2, max_overflow=2)
        self._session_factory = sessionmaker(bind=self._engine)

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background worker thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("pending_order_worker_already_running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="pending-order-worker",
            daemon=True,
        )
        self._thread.start()
        logger.info("pending_order_worker_started", poll_interval=self._poll_interval)

    def stop(self, timeout: float = 10.0) -> None:
        """Stop the background worker thread."""
        if self._thread is None or not self._thread.is_alive():
            logger.info("pending_order_worker_not_running")
            return

        self._stop_event.set()
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            logger.warning("pending_order_worker_stop_timeout", timeout=timeout)
        else:
            logger.info("pending_order_worker_stopped")

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Main loop ──────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """Main loop: continuously poll and process pending orders."""
        logger.info("pending_order_loop_started")
        while not self._stop_event.is_set():
            try:
                processed = self._poll_once()
                if processed > 0:
                    logger.info("pending_orders_processed", count=processed)
            except Exception:
                logger.error("pending_order_poll_error", exc_info=True)

            self._stop_event.wait(timeout=self._poll_interval)

        logger.info("pending_order_loop_exited")

    def _poll_once(self) -> int:
        """Execute one poll cycle. Returns count of processed orders."""
        processed = 0
        orders = self._fetch_pending_orders(limit=50)

        for order_dict in orders:
            try:
                order_id = order_dict.get("id")
                if order_id is None:
                    continue

                # Mark as processing to prevent double-processing.
                with self._session_factory() as session:
                    order = session.get(PendingOrder, int(order_id))
                    if order is None or order.status != "pending":
                        continue
                    order.status = "processing"
                    order.processed_at = datetime.now(timezone.utc)
                    order.attempts = (order.attempts or 0) + 1
                    order.updated_at = datetime.now(timezone.utc)
                    session.commit()

                # Dispatch outside the session lock.
                try:
                    self._dispatch_one(order_dict)
                    processed += 1
                except Exception as exc:
                    logger.error("dispatch_error", order_id=order_id, error=str(exc))
                    self._mark_failed(int(order_id), str(exc))

            except Exception:
                logger.error("pending_order_process_error", order_id=order_dict.get("id"), exc_info=True)

        return processed

    # ── Fetch with stale reclaim ───────────────────────────────────────────

    def _fetch_pending_orders(self, limit: int = 50) -> list[dict[str, Any]]:
        """
        Fetch pending orders with stale reclaim.

        Before fetching, reclaims orders stuck in 'processing' for longer
        than stale_processing_sec back to 'pending'.
        """
        try:
            # Stale reclaim: reset stuck processing orders.
            if self._stale_processing_sec > 0:
                with self._session_factory() as session:
                    cutoff = datetime.now(timezone.utc) - \
                        __import__("datetime").timedelta(seconds=self._stale_processing_sec)
                    session.execute(
                        text("""
                            UPDATE pending_orders
                            SET status = 'pending',
                                updated_at = :now,
                                dispatch_note = CASE
                                    WHEN dispatch_note IS NULL OR dispatch_note = ''
                                    THEN 'requeued_stale_processing'
                                    ELSE dispatch_note
                                END
                            WHERE status = 'processing'
                              AND (updated_at IS NULL OR updated_at < :cutoff)
                              AND (attempts < max_attempts)
                        """),
                        {"now": datetime.now(timezone.utc), "cutoff": cutoff},
                    )
                    session.commit()

            # Fetch pending orders ordered by priority DESC, id ASC.
            with self._session_factory() as session:
                orders = (
                    session.query(PendingOrder)
                    .filter(
                        PendingOrder.status == "pending",
                        PendingOrder.attempts < PendingOrder.max_attempts,
                    )
                    .order_by(PendingOrder.priority.desc(), PendingOrder.id.asc())
                    .limit(limit)
                    .all()
                )

                result: list[dict[str, Any]] = []
                for o in orders:
                    result.append({
                        "id": o.id,
                        "strategy_id": o.strategy_id,
                        "symbol": o.symbol,
                        "signal_type": o.signal_type,
                        "signal_ts": o.signal_ts,
                        "trigger_price": o.trigger_price,
                        "position_size": o.position_size,
                        "payload_json": o.payload_json,
                        "execution_mode": o.execution_mode,
                        "status": o.status,
                        "priority": o.priority,
                        "attempts": o.attempts,
                        "max_attempts": o.max_attempts,
                    })
                return result

        except Exception as exc:
            logger.warning("fetch_pending_orders_failed", error=str(exc))
            return []

    # ── Dispatch ───────────────────────────────────────────────────────────

    def _dispatch_one(self, order_dict: dict[str, Any]) -> None:
        """
        Dispatch a single order based on execution_mode.

        Signal mode: send notifications.
        Live mode: execute on exchange with maker-then-market.
        """
        order_id = int(order_dict["id"])
        mode = (order_dict.get("execution_mode") or "signal").strip().lower()
        payload_json = order_dict.get("payload_json") or ""

        payload: dict[str, Any] = {}
        if payload_json and isinstance(payload_json, str):
            try:
                payload = json.loads(payload_json) or {}
            except Exception:
                payload = {}

        signal_type = payload.get("signal_type") or order_dict.get("signal_type")
        symbol = payload.get("symbol") or order_dict.get("symbol")
        strategy_id = payload.get("strategy_id") or order_dict.get("strategy_id")
        price = float(payload.get("price") or order_dict.get("trigger_price") or 0.0)
        amount = float(payload.get("amount") or order_dict.get("position_size") or 0.0)

        # Auto-upgrade: if strategy DB says "live", upgrade mode.
        try:
            if mode != "live" and strategy_id:
                with self._session_factory() as session:
                    strategy = session.query(StrategyModel).filter_by(id=str(strategy_id)).first()
                    if strategy is not None:
                        em = getattr(strategy, "execution_mode", None) or ""
                        if em.strip().lower() == "live":
                            mode = "live"
        except Exception:
            pass

        if mode == "signal":
            self._dispatch_signal_notification(order_id, order_dict, payload)
            return

        if mode == "live":
            self._execute_live_order(order_id, order_dict, payload)
            return

        self._mark_failed(order_id, f"unsupported_execution_mode:{mode}")

    def _dispatch_signal_notification(
        self,
        order_id: int,
        order_dict: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        """Signal mode: dispatch notifications via notifier."""
        strategy_id = payload.get("strategy_id") or order_dict.get("strategy_id")
        signal_type = payload.get("signal_type") or order_dict.get("signal_type")
        symbol = payload.get("symbol") or order_dict.get("symbol")
        price = float(payload.get("price") or order_dict.get("trigger_price") or 0.0)
        amount = float(payload.get("amount") or order_dict.get("position_size") or 0.0)
        notification_config = payload.get("notification_config") or {}

        # Try to load notification_config from strategy if not in payload.
        if not notification_config and strategy_id:
            try:
                with self._session_factory() as session:
                    strategy = session.query(StrategyModel).filter_by(id=str(strategy_id)).first()
                    if strategy is not None:
                        notification_config = getattr(strategy, "notification_config", None) or {}
            except Exception:
                pass

        # Try to dispatch via notifier (best-effort).
        try:
            from app.strategies.notifier import get_notifier_manager
            notifier = get_notifier_manager()
            direction = "short" if "short" in str(signal_type) else "long"
            strategy_name = payload.get("strategy_name", f"Strategy_{strategy_id}")

            results = notifier.notify_signal(
                strategy_id=str(strategy_id or ""),
                strategy_name=str(strategy_name),
                symbol=str(symbol or ""),
                signal_type=str(signal_type or ""),
                price=price,
                stake_amount=amount,
                direction=direction,
                notification_config=notification_config if isinstance(notification_config, dict) else {},
                extra={"pending_order_id": order_id, "mode": "signal"},
            )

            ok_channels = [c for c, r in results.items() if (r or {}).get("ok")]
            fail_channels = [c for c, r in results.items() if not (r or {}).get("ok")]

            if ok_channels:
                note = f"notified_ok={','.join(ok_channels)}"
                if fail_channels:
                    note += f";fail={','.join(fail_channels)}"
                self._mark_sent(order_id, note=note[:200])
            else:
                first_err = ""
                for c, r in results.items():
                    err = (r or {}).get("error") or ""
                    if err:
                        first_err = f"{c}:{err}"
                        break
                self._mark_failed(order_id, first_err or "notify_failed")

        except ImportError:
            # No notifier available — mark as sent (signal-only, no notification).
            self._mark_sent(order_id, note="no_notifier_available")
        except Exception as exc:
            logger.warning("signal_notify_failed", order_id=order_id, error=str(exc))
            self._mark_sent(order_id, note=f"notify_error:{str(exc)[:100]}")

    # ── Live order execution ───────────────────────────────────────────────

    def _execute_live_order(
        self,
        order_id: int,
        order_dict: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        """
        Execute a live order on the exchange.

        Flow: validate → pre-sync positions → maker-then-market → post-fill.
        """
        strategy_id = payload.get("strategy_id") or order_dict.get("strategy_id")
        symbol = payload.get("symbol") or order_dict.get("symbol")
        signal_type = payload.get("signal_type") or order_dict.get("signal_type")
        price = float(payload.get("price") or order_dict.get("trigger_price") or 0.0)
        amount = float(payload.get("amount") or order_dict.get("position_size") or 0.0)
        ref_price = float(payload.get("ref_price") or price or 0.0)
        leverage = float(payload.get("leverage", 1) or 1)

        if not symbol or not signal_type:
            self._mark_failed(order_id, "missing_symbol_or_signal_type")
            return

        # Get exchange client.
        exchange = self._exchange_client
        if exchange is None:
            self._mark_failed(order_id, "no_exchange_client_configured")
            return

        # Determine side and reduce_only.
        side, reduce_only = self._signal_to_side_reduce(signal_type)

        # Pre-execution position sync.
        try:
            self._sync_positions_for_strategy(str(strategy_id))
        except Exception as exc:
            logger.warning("pre_sync_failed", error=str(exc))

        # For close/reduce signals, cap amount to actual exchange position.
        if reduce_only:
            try:
                actual_qty = self._get_exchange_position_size(exchange, symbol, side)
                if actual_qty is not None and actual_qty > 0:
                    amount = min(amount, actual_qty)
                elif actual_qty is not None and actual_qty <= 0:
                    self._mark_sent(order_id, note="no_exchange_position_to_close")
                    return
            except Exception as exc:
                logger.warning("query_exchange_position_failed", error=str(exc))

        if amount <= 0:
            self._mark_failed(order_id, "zero_amount")
            return

        # Set leverage for futures.
        try:
            exchange.set_leverage(int(leverage), symbol)
        except Exception as exc:
            logger.warning("set_leverage_failed", symbol=symbol, error=str(exc))

        # ── Maker-then-market flow ─────────────────────────────────────
        total_filled = 0.0
        total_cost = 0.0
        total_fee = 0.0
        maker_offset_bps = 2  # 2 basis points
        maker_wait_sec = 10.0

        # Phase 1: Try limit order first.
        if ref_price > 0:
            try:
                offset = ref_price * maker_offset_bps / 10000
                if side == "buy":
                    limit_price = ref_price - offset
                else:
                    limit_price = ref_price + offset

                limit_price = round(limit_price, 6)
                limit_order = exchange.place_limit_order(
                    symbol=symbol,
                    side=side,
                    amount=amount,
                    price=limit_price,
                    reduce_only=reduce_only,
                )

                order_id_exch = limit_order.get("id")
                if order_id_exch:
                    # Wait for fill.
                    filled = exchange.wait_for_fill(symbol, order_id_exch, max_wait_sec=maker_wait_sec)
                    if filled:
                        filled_qty = float(filled.get("filled") or 0)
                        avg_px = float(filled.get("average") or limit_price)
                        fee_info = filled.get("fee") or {}
                        fee_cost = float(fee_info.get("cost") or 0)

                        if filled_qty > 0:
                            total_filled += filled_qty
                            total_cost += filled_qty * avg_px
                            total_fee += fee_cost

                    remaining = amount - total_filled
                    if remaining > amount * 0.001:
                        # Cancel unfilled portion.
                        try:
                            exchange.cancel_order(order_id_exch, symbol)
                        except Exception:
                            pass
                    else:
                        remaining = 0

                    if remaining > 0:
                        # Phase 2: Market order for remaining.
                        try:
                            market_order = exchange.create_market_order(
                                symbol=symbol,
                                side=side,
                                amount=remaining,
                                reduce_only=reduce_only,
                            )
                            if market_order:
                                m_filled = float(market_order.get("filled") or remaining)
                                m_avg = float(market_order.get("average") or ref_price)
                                m_fee = float((market_order.get("fee") or {}).get("cost") or 0)
                                total_filled += m_filled
                                total_cost += m_filled * m_avg
                                total_fee += m_fee
                        except Exception as exc:
                            logger.error("market_order_failed", error=str(exc))
                            if total_filled <= 0:
                                self._mark_failed(order_id, f"market_order_failed: {exc}")
                                return
                else:
                    # Limit order failed, fall back to market.
                    raise Exception("limit_order_no_id")

            except Exception as exc:
                logger.warning("limit_order_failed_fallback_market", error=str(exc))
                # Full market order fallback.
                try:
                    market_order = exchange.create_market_order(
                        symbol=symbol,
                        side=side,
                        amount=amount,
                        reduce_only=reduce_only,
                    )
                    if market_order:
                        m_filled = float(market_order.get("filled") or amount)
                        m_avg = float(market_order.get("average") or ref_price)
                        m_fee = float((market_order.get("fee") or {}).get("cost") or 0)
                        total_filled += m_filled
                        total_cost += m_filled * m_avg
                        total_fee += m_fee
                except Exception as exc2:
                    logger.error("market_order_fallback_failed", error=str(exc2))
                    self._mark_failed(order_id, f"all_orders_failed: {exc2}")
                    return
        else:
            # No ref_price, direct market order.
            try:
                market_order = exchange.create_market_order(
                    symbol=symbol,
                    side=side,
                    amount=amount,
                    reduce_only=reduce_only,
                )
                if market_order:
                    m_filled = float(market_order.get("filled") or amount)
                    m_avg = float(market_order.get("average") or 0)
                    m_fee = float((market_order.get("fee") or {}).get("cost") or 0)
                    total_filled += m_filled
                    total_cost += m_filled * m_avg if m_avg > 0 else 0
                    total_fee += m_fee
            except Exception as exc:
                self._mark_failed(order_id, f"market_order_failed: {exc}")
                return

        # ── Post-execution ─────────────────────────────────────────────
        filled_final = total_filled if total_filled > 0 else amount
        avg_final = (total_cost / total_filled) if total_filled > 0 else ref_price

        # Mark order as sent.
        self._mark_sent(
            order_id,
            note=f"filled={filled_final:.6f}@{avg_final:.6f},fee={total_fee:.6f}",
            filled=filled_final,
            avg_price=avg_final,
        )

        # Apply fill to local position.
        profit, _ = apply_fill_to_local_position(
            strategy_id=str(strategy_id),
            symbol=symbol,
            signal_type=signal_type,
            filled=filled_final,
            avg_price=avg_final,
        )

        # Record trade.
        record_trade(
            strategy_id=str(strategy_id),
            symbol=symbol,
            trade_type=signal_type,
            price=avg_final,
            amount=filled_final,
            commission=total_fee,
            profit=profit or 0.0,
            value=filled_final * avg_final,
        )

        logger.info(
            "live_order_executed", order_id=order_id,
            signal_type=signal_type, symbol=symbol,
            filled=filled_final, avg_price=avg_final, profit=profit,
        )

    @staticmethod
    def _signal_to_side_reduce(signal_type: str) -> tuple[str, bool]:
        """Map signal_type to (ccxt_side, reduce_only)."""
        sig = (signal_type or "").lower()
        if sig in ("open_long", "add_long"):
            return "buy", False
        if sig in ("open_short", "add_short"):
            return "sell", False
        if sig in ("close_long", "reduce_long"):
            return "sell", True
        if sig in ("close_short", "reduce_short"):
            return "buy", True
        return "buy", False

    # ── Position sync ──────────────────────────────────────────────────────

    def _sync_positions_for_strategy(self, strategy_id: str) -> None:
        """
        Best-effort position sync between exchange and local DB for a strategy.
        Removes ghost positions (exchange closed, local still open).
        """
        if self._exchange_client is None:
            return

        try:
            # Get local positions.
            with self._session_factory() as session:
                local_positions = (
                    session.query(StrategyPosition)
                    .filter_by(strategy_id=str(strategy_id))
                    .all()
                )

                if not local_positions:
                    return

                # Get exchange positions.
                try:
                    exchange_positions = self._exchange_client.get_positions()
                except Exception as exc:
                    logger.warning("get_positions_failed", error=str(exc))
                    return

                # Build exchange position map: symbol -> {side: size}.
                exch_map: dict[str, dict[str, float]] = {}
                if isinstance(exchange_positions, list):
                    for ep in exchange_positions:
                        sym = ep.get("symbol", "")
                        ep_side = (ep.get("side") or "").lower()
                        ep_size = abs(float(ep.get("contracts") or ep.get("size") or 0))
                        if sym and ep_side:
                            exch_map.setdefault(sym, {})[ep_side] = ep_size

                # Reconcile.
                for pos in local_positions:
                    local_sym = pos.symbol
                    local_side = (pos.side or "").lower()
                    local_size = float(pos.size or 0)

                    exch_qty = exch_map.get(local_sym, {}).get(local_side, 0)

                    if exch_qty <= 0.0001 and local_size > 0.0001:
                        # Ghost position: exchange closed but local still open.
                        logger.info(
                            "removing_ghost_position",
                            strategy_id=strategy_id, symbol=local_sym, side=local_side,
                        )
                        pos.size = 0.0
                        pos.amount = 0.0
                        pos.unrealized_pnl = 0.0
                        pos.updated_at = datetime.now(timezone.utc)

                    elif exch_qty > 0.0001 and abs(local_size - exch_qty) / max(exch_qty, 0.0001) > 0.01:
                        # Size divergence > 1%: update local to match exchange.
                        logger.info(
                            "syncing_position_size",
                            strategy_id=strategy_id, symbol=local_sym,
                            local=local_size, exchange=exch_qty,
                        )
                        pos.size = exch_qty
                        pos.amount = exch_qty * float(pos.entry_price or 0)
                        pos.updated_at = datetime.now(timezone.utc)

                session.commit()

        except Exception as exc:
            logger.warning("sync_positions_failed", strategy_id=strategy_id, error=str(exc))

    def _get_exchange_position_size(
        self,
        exchange: Any,
        symbol: str,
        side: str,
    ) -> float | None:
        """Get the actual position size from exchange for a symbol+side."""
        try:
            positions = exchange.get_positions()
            if not isinstance(positions, list):
                return None
            for p in positions:
                p_sym = p.get("symbol", "")
                p_side = (p.get("side") or "").lower()
                if p_sym == symbol and p_side == side:
                    return abs(float(p.get("contracts") or p.get("size") or 0))
            return 0.0
        except Exception:
            return None

    # ── Status updates ─────────────────────────────────────────────────────

    def _mark_sent(
        self,
        order_id: int,
        note: str = "",
        filled: float = 0.0,
        avg_price: float = 0.0,
    ) -> None:
        """Mark an order as successfully sent/executed."""
        with self._session_factory() as session:
            try:
                order = session.get(PendingOrder, order_id)
                if order is not None:
                    order.status = "sent"
                    order.dispatch_note = str(note or "")[:500]
                    order.sent_at = datetime.now(timezone.utc)
                    order.executed_at = datetime.now(timezone.utc)
                    order.updated_at = datetime.now(timezone.utc)
                    session.commit()
            except Exception as exc:
                session.rollback()
                logger.error("mark_sent_failed", order_id=order_id, error=str(exc))

    def _mark_failed(self, order_id: int, error: str) -> None:
        """Mark an order as failed."""
        with self._session_factory() as session:
            try:
                order = session.get(PendingOrder, order_id)
                if order is not None:
                    order.status = "failed"
                    order.last_error = str(error or "failed")[:1000]
                    order.updated_at = datetime.now(timezone.utc)
                    session.commit()
            except Exception as exc:
                session.rollback()
                logger.error("mark_failed_failed", order_id=order_id, error=str(exc))
