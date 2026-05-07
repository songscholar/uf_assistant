"""
UF Stock Assistant — 盈亏追踪器
统计已实现/未实现盈亏、每日盈亏、交易历史
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.logging import get_logger

from .models import Order, Position, TradeLog

logger = get_logger("app.trading.pnl_tracker")


class PnLTracker:
    """盈亏追踪器"""

    def __init__(self, db: Session, mode: str) -> None:
        self.db = db
        self.mode = mode

    def get_total_pnl(self, market: str | None = None) -> dict:
        """统计总盈亏"""
        # 已实现盈亏（从成交日志计算）
        query = self.db.query(func.sum(TradeLog.fee)).select_from(TradeLog)
        if market:
            query = query.filter(TradeLog.market == market)

        # 未实现盈亏（从持仓计算）
        pos_query = self.db.query(
            func.sum(Position.unrealized_pnl),
            func.sum(Position.realized_pnl),
        ).filter(Position.mode == self.mode, Position.quantity > 0)
        if market:
            pos_query = pos_query.filter(Position.market == market)

        row = pos_query.first()
        total_unrealized = float(row[0] or 0) if row else 0
        total_realized = float(row[1] or 0) if row else 0

        # 总手续费
        fee_query = self.db.query(func.sum(TradeLog.fee))
        if market:
            fee_query = fee_query.filter(TradeLog.market == market)
        total_fee = float(fee_query.scalar() or 0)

        return {
            "total_realized": round(total_realized, 4),
            "total_unrealized": round(total_unrealized, 4),
            "total_pnl": round(total_realized + total_unrealized, 4),
            "total_fee": round(total_fee, 4),
        }

    def get_trade_history(
        self,
        symbol: str | None = None,
        market: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """获取交易历史"""
        query = self.db.query(TradeLog)
        if symbol:
            query = query.filter(TradeLog.symbol == symbol)
        if market:
            query = query.filter(TradeLog.market == market)

        logs = query.order_by(TradeLog.timestamp.desc()).limit(limit).all()
        return [
            {
                "id": log.id,
                "order_id": log.order_id,
                "market": log.market,
                "symbol": log.symbol,
                "side": log.side,
                "quantity": log.quantity,
                "price": log.price,
                "fee": log.fee,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            }
            for log in logs
        ]

    def get_daily_pnl(self, days: int = 30) -> list[dict]:
        """每日盈亏统计"""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        logs = (
            self.db.query(TradeLog)
            .filter(TradeLog.timestamp >= since)
            .order_by(TradeLog.timestamp)
            .all()
        )

        daily: dict[str, dict] = {}
        for log in logs:
            date_key = log.timestamp.strftime("%Y-%m-%d") if log.timestamp else "unknown"
            if date_key not in daily:
                daily[date_key] = {"date": date_key, "pnl": 0, "trades": 0, "fee": 0}
            # 简化：buy 为负，sell 为正
            sign = -1 if log.side == "buy" else 1
            daily[date_key]["pnl"] += sign * log.quantity * log.price
            daily[date_key]["fee"] += log.fee
            daily[date_key]["trades"] += 1

        return sorted(daily.values(), key=lambda x: x["date"])

    def get_order_count(self, status: str | None = None) -> int:
        query = self.db.query(func.count(Order.id)).filter(Order.mode == self.mode)
        if status:
            query = query.filter(Order.status == status)
        return query.scalar() or 0
