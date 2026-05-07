"""
Local DB snapshot for trades and positions (best-effort, not source of truth).

These functions mirror QuantDinger's record_trade / upsert_position design,
adapted to UF's SQLAlchemy ORM models (StrategyTrade, StrategyPosition).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger
from app.strategies.models import StrategyPosition, StrategyTrade
from app.strategies.trading_executor import get_strategy_db_session

logger = get_logger("app.strategies.live_trading.records")


def normalize_strategy_symbol(symbol: str) -> str:
    """Canonical form like BTC/USDT to fix mixed format lookups."""
    if not symbol:
        return ""
    s = str(symbol).strip().upper()
    # Strip :USDT suffix
    if ":" in s:
        s = s.split(":")[0]
    # Ensure separator is /
    if "_" in s and "/" not in s:
        s = s.replace("_", "/")
    if "-" in s and "/" not in s:
        # Only convert if it looks like a pair (e.g. BTC-USDT)
        parts = s.split("-")
        if len(parts) == 2 and len(parts[0]) >= 2 and len(parts[1]) >= 2:
            s = f"{parts[0]}/{parts[1]}"
    return s


def record_trade(
    strategy_id: str,
    symbol: str,
    trade_type: str,
    price: float,
    amount: float,
    value: float = 0.0,
    commission: float = 0.0,
    profit: float = 0.0,
    balance: float = 0.0,
    exchange_order_id: str = "",
) -> None:
    """Insert a trade record into strategy_trades."""
    session = get_strategy_db_session()
    try:
        trade = StrategyTrade(
            strategy_id=str(strategy_id),
            symbol=normalize_strategy_symbol(symbol),
            trade_type=str(trade_type),
            price=float(price),
            amount=float(amount),
            value=float(value),
            commission=float(commission),
            profit=float(profit),
            balance=float(balance),
            exchange_order_id=str(exchange_order_id) if exchange_order_id else None,
        )
        session.add(trade)
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("record_trade_failed", strategy_id=strategy_id, error=str(exc))
    finally:
        session.close()


def upsert_position(
    strategy_id: str,
    symbol: str,
    side: str,
    size: float,
    entry_price: float,
    current_price: float = 0.0,
    highest_price: float = 0.0,
    lowest_price: float = 0.0,
    unrealized_pnl: float = 0.0,
) -> None:
    """Insert or update a position record."""
    session = get_strategy_db_session()
    try:
        sym = normalize_strategy_symbol(symbol)
        pos = (
            session.query(StrategyPosition)
            .filter_by(strategy_id=str(strategy_id), symbol=sym, side=str(side))
            .first()
        )
        if pos is None:
            pos = StrategyPosition(
                strategy_id=str(strategy_id),
                symbol=sym,
                side=str(side),
                size=float(size),
                entry_price=float(entry_price),
                current_price=float(current_price) if current_price else float(entry_price),
                highest_price=float(highest_price),
                lowest_price=float(lowest_price),
                unrealized_pnl=float(unrealized_pnl),
            )
            session.add(pos)
        else:
            pos.size = float(size)
            pos.entry_price = float(entry_price)
            if current_price:
                pos.current_price = float(current_price)
            if highest_price:
                pos.highest_price = float(highest_price)
            if lowest_price:
                pos.lowest_price = float(lowest_price)
            pos.unrealized_pnl = float(unrealized_pnl)
            pos.updated_at = datetime.now(timezone.utc)
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("upsert_position_failed", strategy_id=strategy_id, error=str(exc))
    finally:
        session.close()


def apply_fill_to_local_position(
    strategy_id: str,
    symbol: str,
    side: str,
    fill_size: float,
    fill_price: float,
    trade_type: str = "",
) -> dict[str, Any]:
    """
    Update local position on fill.

    - Open/Add: weighted average entry price, track highest/lowest price
    - Close/Reduce: calculates PnL using local entry price, deletes position if size <= 0

    Returns {"realized_pnl": float, "position_size": float, "entry_price": float}
    """
    session = get_strategy_db_session()
    try:
        sym = normalize_strategy_symbol(symbol)
        pos = (
            session.query(StrategyPosition)
            .filter_by(strategy_id=str(strategy_id), symbol=sym, side=str(side))
            .first()
        )

        realized_pnl = 0.0
        is_opening = trade_type in ("open_long", "open_short", "add_long", "add_short")
        is_closing = trade_type in ("close_long", "close_short", "reduce_long", "reduce_short")

        if pos is None:
            if is_closing:
                # Closing a non-existent position → nothing to do
                return {"realized_pnl": 0.0, "position_size": 0.0, "entry_price": 0.0}
            # New position
            pos = StrategyPosition(
                strategy_id=str(strategy_id),
                symbol=sym,
                side=str(side),
                size=float(fill_size),
                entry_price=float(fill_price),
                current_price=float(fill_price),
                highest_price=float(fill_price),
                lowest_price=float(fill_price),
                unrealized_pnl=0.0,
            )
            session.add(pos)
            session.commit()
            return {"realized_pnl": 0.0, "position_size": fill_size, "entry_price": fill_price}

        old_size = float(pos.size or 0.0)
        old_entry = float(pos.entry_price or 0.0)

        if is_opening:
            # Weighted average entry price
            total_value = old_size * old_entry + fill_size * fill_price
            new_size = old_size + fill_size
            new_entry = total_value / new_size if new_size > 0 else 0.0
            pos.size = new_size
            pos.entry_price = new_entry
            pos.current_price = fill_price
            pos.highest_price = max(pos.highest_price or 0.0, fill_price)
            pos.lowest_price = min(pos.lowest_price or fill_price, fill_price) if pos.lowest_price else fill_price
            pos.updated_at = datetime.now(timezone.utc)
            session.commit()
            return {"realized_pnl": 0.0, "position_size": new_size, "entry_price": new_entry}

        if is_closing:
            # Calculate realized PnL
            if side == "long":
                realized_pnl = (fill_price - old_entry) * min(fill_size, old_size)
            else:
                realized_pnl = (old_entry - fill_price) * min(fill_size, old_size)

            new_size = old_size - fill_size
            if new_size <= 0:
                session.delete(pos)
            else:
                pos.size = new_size
                pos.current_price = fill_price
                pos.updated_at = datetime.now(timezone.utc)
            session.commit()
            return {"realized_pnl": realized_pnl, "position_size": max(0.0, new_size), "entry_price": old_entry}

        # Unknown trade_type → treat as add
        pos.size = old_size + fill_size
        pos.current_price = fill_price
        pos.updated_at = datetime.now(timezone.utc)
        session.commit()
        return {"realized_pnl": 0.0, "position_size": pos.size, "entry_price": old_entry}

    except Exception as exc:
        session.rollback()
        logger.error("apply_fill_failed", strategy_id=strategy_id, error=str(exc))
        return {"realized_pnl": 0.0, "position_size": 0.0, "entry_price": 0.0}
    finally:
        session.close()
