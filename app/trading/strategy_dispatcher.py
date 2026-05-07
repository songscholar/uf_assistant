"""
UF Stock Assistant — 策略信号 → 交易订单 调度器
将策略分析结果转换为交易订单（支持手动确认和自动执行）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import MarketType, OrderSide, OrderType, TradingMode, TrendDirection
from app.core.logging import get_logger
from app.strategies.base import Signal

from .backend_router import BackendRouter
from .models import Order, _uuid, _utcnow

logger = get_logger("app.trading.strategy_dispatcher")


@dataclass
class PendingSignal:
    """待处理的策略信号"""
    id: str
    strategy_id: str
    symbol: str
    direction: str  # "up" → buy, "down" → sell
    confidence: float
    reason: str
    suggested_quantity: float = 0
    suggested_price: float | None = None
    market: str = MarketType.CRYPTO
    status: str = "pending"  # pending, confirmed, rejected, executed
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class StrategyDispatcher:
    """将策略信号转换为交易订单

    工作流：
    1. 策略执行 → 产生 Signal
    2. Dispatcher 接收信号 → 创建 PendingSignal
    3. 手动模式：用户在 UI 确认后执行
    4. 自动模式：直接提交到交易所
    """

    def __init__(self, db: Session, backend_router: BackendRouter, auto_execute: bool = False) -> None:
        self.db = db
        self.backend_router = backend_router
        self.auto_execute = auto_execute
        self._pending_signals: dict[str, PendingSignal] = {}

    async def process_signal(
        self,
        signal: Signal,
        strategy_id: str,
        market: str = MarketType.CRYPTO,
        suggested_quantity: float = 0,
        suggested_price: float | None = None,
    ) -> PendingSignal:
        """处理策略信号

        Args:
            signal: 策略产生的交易信号
            strategy_id: 策略标识
            market: 交易市场
            suggested_quantity: 建议数量（0 表示需要用户指定）
            suggested_price: 建议价格

        Returns:
            PendingSignal 对象
        """
        # 信号方向 → 交易方向
        if signal.direction == TrendDirection.UP:
            side = OrderSide.BUY
        elif signal.direction == TrendDirection.DOWN:
            side = OrderSide.SELL
        else:
            # direction == flat，不交易
            logger.info("signal_ignored_flat", symbol=signal.symbol, strategy=strategy_id)
            pending = PendingSignal(
                id=_uuid(),
                strategy_id=strategy_id,
                symbol=signal.symbol,
                direction="flat",
                confidence=signal.confidence,
                reason=signal.reason,
                market=market,
                status="ignored",
            )
            return pending

        # 置信度检查
        min_confidence = 0.6
        if signal.confidence < min_confidence:
            logger.info(
                "signal_low_confidence",
                symbol=signal.symbol,
                confidence=signal.confidence,
                min_confidence=min_confidence,
            )
            pending = PendingSignal(
                id=_uuid(),
                strategy_id=strategy_id,
                symbol=signal.symbol,
                direction=signal.direction.value,
                confidence=signal.confidence,
                reason=signal.reason,
                market=market,
                status="rejected",
            )
            return pending

        pending = PendingSignal(
            id=_uuid(),
            strategy_id=strategy_id,
            symbol=signal.symbol,
            direction=signal.direction.value,
            confidence=signal.confidence,
            reason=signal.reason,
            suggested_quantity=suggested_quantity,
            suggested_price=suggested_price,
            market=market,
        )

        self._pending_signals[pending.id] = pending

        logger.info(
            "signal_pending",
            signal_id=pending.id,
            symbol=signal.symbol,
            side=side,
            confidence=signal.confidence,
            strategy=strategy_id,
            auto_execute=self.auto_execute,
        )

        # 自动执行模式
        if self.auto_execute and suggested_quantity > 0:
            await self.execute_signal(pending.id, suggested_quantity, suggested_price)

        return pending

    async def execute_signal(
        self,
        signal_id: str,
        quantity: float,
        price: float | None = None,
    ) -> Order | None:
        """执行待确认的信号（手动确认后调用）"""
        pending = self._pending_signals.get(signal_id)
        if not pending:
            logger.warning("signal_not_found", signal_id=signal_id)
            return None

        if pending.status not in ("pending", "confirmed"):
            logger.warning("signal_already_processed", signal_id=signal_id, status=pending.status)
            return None

        side = OrderSide.BUY if pending.direction == "up" else OrderSide.SELL
        order_type = OrderType.LIMIT if price else OrderType.MARKET

        # 获取后端并下单
        from .order_manager import OrderManager

        backend = await self.backend_router.get_backend(pending.market)
        manager = OrderManager(self.db, backend, self.backend_router.get_mode())

        try:
            order = await manager.submit_order(
                market=pending.market,
                symbol=pending.symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                strategy_id=pending.strategy_id,
            )
            pending.status = "executed"
            logger.info(
                "signal_executed",
                signal_id=signal_id,
                order_id=order.id,
                symbol=pending.symbol,
                side=side,
            )
            return order
        except Exception as exc:
            logger.error("signal_execution_failed", signal_id=signal_id, error=str(exc))
            pending.status = "rejected"
            return None

    def reject_signal(self, signal_id: str) -> bool:
        """拒绝信号"""
        pending = self._pending_signals.get(signal_id)
        if not pending:
            return False
        pending.status = "rejected"
        logger.info("signal_rejected", signal_id=signal_id)
        return True

    def list_pending_signals(self) -> list[dict]:
        """列出所有待处理信号"""
        return [
            {
                "id": s.id,
                "strategy_id": s.strategy_id,
                "symbol": s.symbol,
                "direction": s.direction,
                "confidence": s.confidence,
                "reason": s.reason,
                "suggested_quantity": s.suggested_quantity,
                "suggested_price": s.suggested_price,
                "market": s.market,
                "status": s.status,
                "created_at": s.created_at,
            }
            for s in self._pending_signals.values()
            if s.status == "pending"
        ]

    def get_signal_history(self, limit: int = 50) -> list[dict]:
        """获取信号历史"""
        all_signals = sorted(
            self._pending_signals.values(),
            key=lambda s: s.created_at,
            reverse=True,
        )
        return [
            {
                "id": s.id,
                "strategy_id": s.strategy_id,
                "symbol": s.symbol,
                "direction": s.direction,
                "confidence": s.confidence,
                "reason": s.reason,
                "market": s.market,
                "status": s.status,
                "created_at": s.created_at,
            }
            for s in all_signals[:limit]
        ]
