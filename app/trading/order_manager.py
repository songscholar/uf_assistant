"""
UF Stock Assistant — 订单管理器
统一的订单提交、取消、查询接口
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import MarketType, OrderSide, OrderStatus, OrderType, TradingMode
from app.core.exceptions import OrderError
from app.core.logging import get_logger

from .backends import ExchangeBackend, OrderResult
from .models import Order, TradeLog, _uuid, _utcnow

logger = get_logger("app.trading.order_manager")


class OrderManager:
    """订单管理器 — 协调订单生命周期"""

    def __init__(self, db: Session, backend: ExchangeBackend, mode: str) -> None:
        self.db = db
        self.backend = backend
        self.mode = mode

    async def submit_order(
        self,
        market: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        strategy_id: str | None = None,
    ) -> Order:
        """提交订单：创建 DB 记录 → 提交到交易所 → 更新状态"""

        # 参数校验
        if quantity <= 0:
            raise OrderError("订单数量必须大于 0")
        if order_type == OrderType.LIMIT and price is None:
            raise OrderError("限价单必须指定价格")
        if side not in (OrderSide.BUY, OrderSide.SELL):
            raise OrderError(f"无效的订单方向: {side}")

        # 1. 创建 DB 订单记录（PENDING）
        order = Order(
            id=_uuid(),
            market=market,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            status=OrderStatus.PENDING,
            strategy_id=strategy_id,
            mode=self.mode,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)

        logger.info(
            "order_created",
            order_id=order.id,
            market=market,
            symbol=symbol,
            side=side,
            quantity=quantity,
            mode=self.mode,
        )

        # 2. 提交到交易所
        try:
            result: OrderResult = await self.backend.place_order(
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
            )

            # 3. 更新订单状态
            order.exchange_order_id = result.exchange_order_id
            order.status = result.status
            order.filled_quantity = result.filled_quantity
            order.filled_price = result.filled_price
            order.fee = result.fee
            order.fee_currency = result.fee_currency
            order.updated_at = _utcnow()
            self.db.commit()

            # 4. 如果成交，记录交易日志
            if result.status == OrderStatus.FILLED and result.filled_price:
                log = TradeLog(
                    id=_uuid(),
                    order_id=order.id,
                    market=market,
                    symbol=symbol,
                    side=side,
                    quantity=result.filled_quantity,
                    price=result.filled_price,
                    fee=result.fee or 0,
                    timestamp=_utcnow(),
                )
                self.db.add(log)
                self.db.commit()

            logger.info(
                "order_submitted",
                order_id=order.id,
                exchange_order_id=result.exchange_order_id,
                status=result.status,
            )

        except Exception as exc:
            order.status = OrderStatus.REJECTED
            order.updated_at = _utcnow()
            self.db.commit()
            logger.error("order_submit_failed", order_id=order.id, error=str(exc))
            raise OrderError(f"订单提交失败: {exc}") from exc

        return order

    async def cancel_order(self, order_id: str) -> Order:
        """取消订单"""
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise OrderError(f"订单不存在: {order_id}")

        if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
            raise OrderError(f"订单 {order_id} 状态为 {order.status}，无法取消")

        if order.exchange_order_id:
            success = await self.backend.cancel_order(order.exchange_order_id, order.symbol)
            if success:
                order.status = OrderStatus.CANCELLED
            else:
                raise OrderError("交易所取消订单失败")
        else:
            order.status = OrderStatus.CANCELLED

        order.updated_at = _utcnow()
        self.db.commit()
        logger.info("order_cancelled", order_id=order_id)
        return order

    async def sync_order_status(self, order_id: str) -> Order:
        """从交易所同步订单最新状态"""
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise OrderError(f"订单不存在: {order_id}")

        if not order.exchange_order_id:
            return order

        if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
            return order

        try:
            result = await self.backend.get_order_status(order.exchange_order_id, order.symbol)
            order.status = result.status
            order.filled_quantity = result.filled_quantity
            order.filled_price = result.filled_price
            order.fee = result.fee
            order.fee_currency = result.fee_currency
            order.updated_at = _utcnow()
            self.db.commit()

            # 如果刚成交，记录交易日志
            if result.status == OrderStatus.FILLED and result.filled_price:
                existing = self.db.query(TradeLog).filter(TradeLog.order_id == order_id).first()
                if not existing:
                    log = TradeLog(
                        id=_uuid(),
                        order_id=order.id,
                        market=order.market,
                        symbol=order.symbol,
                        side=order.side,
                        quantity=result.filled_quantity,
                        price=result.filled_price,
                        fee=result.fee or 0,
                        timestamp=_utcnow(),
                    )
                    self.db.add(log)
                    self.db.commit()

        except Exception as exc:
            logger.error("order_sync_failed", order_id=order_id, error=str(exc))

        return order

    def get_order(self, order_id: str) -> Order | None:
        return self.db.query(Order).filter(Order.id == order_id).first()

    def list_orders(
        self,
        status: str | None = None,
        market: str | None = None,
        limit: int = 50,
    ) -> list[Order]:
        query = self.db.query(Order)
        if status:
            query = query.filter(Order.status == status)
        if market:
            query = query.filter(Order.market == market)
        return query.order_by(Order.created_at.desc()).limit(limit).all()
