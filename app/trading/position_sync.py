"""
UF Stock Assistant — 持仓同步器
从交易所拉取真实持仓，更新数据库
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import MarketType, TradingMode
from app.core.logging import get_logger

from .backends import ExchangeBackend, PositionResult
from .models import Position, _uuid, _utcnow

logger = get_logger("app.trading.position_sync")


class PositionSyncer:
    """持仓同步器 — 从交易所同步持仓到本地 DB"""

    def __init__(self, db: Session, backend: ExchangeBackend, mode: str) -> None:
        self.db = db
        self.backend = backend
        self.mode = mode

    async def sync_positions(self, market: str) -> list[Position]:
        """从交易所拉取真实持仓，更新 DB"""
        try:
            remote_positions = await self.backend.get_positions()
        except Exception as exc:
            logger.error("position_sync_fetch_failed", market=market, error=str(exc))
            return []

        synced = []
        for rp in remote_positions:
            pos = (
                self.db.query(Position)
                .filter(Position.symbol == rp.symbol, Position.market == market, Position.mode == self.mode)
                .first()
            )

            if pos:
                pos.quantity = rp.quantity
                pos.avg_cost = rp.avg_cost or pos.avg_cost
                pos.current_price = rp.current_price
                pos.unrealized_pnl = rp.unrealized_pnl
                pos.updated_at = _utcnow()
            else:
                pos = Position(
                    id=_uuid(),
                    market=market,
                    symbol=rp.symbol,
                    quantity=rp.quantity,
                    avg_cost=rp.avg_cost or 0,
                    current_price=rp.current_price,
                    unrealized_pnl=rp.unrealized_pnl,
                    mode=self.mode,
                    updated_at=_utcnow(),
                )
                self.db.add(pos)

            synced.append(pos)

        # 将本地有但远程没有的持仓标记为 0
        local_positions = (
            self.db.query(Position)
            .filter(Position.market == market, Position.mode == self.mode, Position.quantity > 0)
            .all()
        )
        remote_symbols = {rp.symbol for rp in remote_positions}
        for lp in local_positions:
            if lp.symbol not in remote_symbols:
                lp.quantity = 0
                lp.updated_at = _utcnow()

        self.db.commit()
        logger.info("positions_synced", market=market, count=len(synced))
        return synced

    async def update_current_prices(self) -> None:
        """更新所有持仓的当前价格和未实现盈亏"""
        positions = (
            self.db.query(Position)
            .filter(Position.mode == self.mode, Position.quantity > 0)
            .all()
        )

        for pos in positions:
            try:
                ticker = await self.backend.get_ticker(pos.symbol)
                current_price = ticker.get("last", 0)
                if current_price:
                    pos.current_price = current_price
                    pos.unrealized_pnl = round((current_price - pos.avg_cost) * pos.quantity, 4)
                    pos.updated_at = _utcnow()
            except Exception as exc:
                logger.warning("price_update_failed", symbol=pos.symbol, error=str(exc))

        self.db.commit()

    def get_positions(self, market: str | None = None) -> list[Position]:
        query = self.db.query(Position).filter(Position.mode == self.mode, Position.quantity > 0)
        if market:
            query = query.filter(Position.market == market)
        return query.all()

    def get_position(self, symbol: str) -> Position | None:
        return (
            self.db.query(Position)
            .filter(Position.symbol == symbol, Position.mode == self.mode)
            .first()
        )
