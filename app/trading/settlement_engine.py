"""
UF Stock Assistant — 交收引擎
支持多业务类型、多交收周期的资金和持仓交收处理
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.core.constants import SettlementMode, SettlementStatus, TradeType
from app.core.logging import get_logger
from app.trading.models import (
    MockPortfolio,
    Order,
    Position,
    SettlementTask,
    get_db_session,
)

logger = get_logger("app.trading.settlement")


# ── 交收引擎 ──────────────────────────────────────────────────────────────────

class SettlementEngine:
    """交收引擎：处理所有待交收任务"""

    def __init__(self) -> None:
        pass

    def create_settlement_tasks(
        self,
        user_id: int,
        order_id: str,
        trade_type: TradeType,
        settlement_mode: SettlementMode,
        side: str,
        symbol: str,
        quantity: float,
        price: float,
        total_fee: float,
    ) -> list[str]:
        """
        根据成交结果创建待交收任务

        返回：任务ID列表
        """
        now = datetime.now(timezone.utc)
        tasks = []

        # 计算交收日期
        if settlement_mode == SettlementMode.T0:
            settlement_date = now
        elif settlement_mode == SettlementMode.T1:
            settlement_date = self._next_trading_day(now, 1)
        elif settlement_mode == SettlementMode.T2:
            settlement_date = self._next_trading_day(now, 2)
        else:
            settlement_date = self._next_trading_day(now, 1)

        if side == "buy":
            # 买入：
            # 1. 成交时冻结资金（已在前端处理）
            # 2. 交收日：扣减实际资金 + 增加实际持仓
            tasks.append(self._create_task(
                user_id=user_id,
                order_id=order_id,
                trade_type=trade_type,
                task_type="cash_release",
                amount=quantity * price + total_fee,
                symbol=None,
                settlement_date=settlement_date,
            ))
            tasks.append(self._create_task(
                user_id=user_id,
                order_id=order_id,
                trade_type=trade_type,
                task_type="position_add",
                amount=quantity,
                symbol=symbol,
                settlement_date=settlement_date,
            ))
        else:
            # 卖出：
            # 1. 成交时冻结持仓（已在前端处理）
            # 2. 交收日：扣减实际持仓 + 增加实际资金
            tasks.append(self._create_task(
                user_id=user_id,
                order_id=order_id,
                trade_type=trade_type,
                task_type="position_release",
                amount=quantity,
                symbol=symbol,
                settlement_date=settlement_date,
            ))
            tasks.append(self._create_task(
                user_id=user_id,
                order_id=order_id,
                trade_type=trade_type,
                task_type="cash_deduct",
                amount=quantity * price - total_fee,
                symbol=None,
                settlement_date=settlement_date,
            ))

        logger.info(
            "settlement_tasks_created",
            user_id=user_id,
            order_id=order_id,
            trade_type=trade_type,
            settlement_mode=settlement_mode,
            task_count=len(tasks),
        )
        return tasks

    def _create_task(
        self,
        user_id: int,
        order_id: str,
        trade_type: TradeType,
        task_type: str,
        amount: float,
        symbol: str | None,
        settlement_date: datetime,
    ) -> str:
        """创建单个待交收任务"""
        db = get_db_session()
        try:
            task = SettlementTask(
                user_id=user_id,
                order_id=order_id,
                trade_type=trade_type,
                task_type=task_type,
                symbol=symbol,
                amount=round(amount, 2),
                settlement_date=settlement_date,
                status=SettlementStatus.PENDING,
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            return task.id
        finally:
            db.close()

    def run_daily_settlement(self, target_date: datetime | None = None) -> dict[str, Any]:
        """
        执行日终交收（定时任务入口）

        Args:
            target_date: 指定交收日期，None 表示今天

        Returns:
            {"processed": int, "success": int, "failed": int, "details": list}
        """
        if target_date is None:
            target_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        # 获取所有待交收任务（settlement_date <= target_date）
        db = get_db_session()
        try:
            tasks = (
                db.query(SettlementTask)
                .filter(
                    SettlementTask.settlement_date <= target_date,
                    SettlementTask.status == SettlementStatus.PENDING,
                )
                .order_by(SettlementTask.created_at)
                .all()
            )

            result = {"processed": 0, "success": 0, "failed": 0, "details": []}

            for task in tasks:
                result["processed"] += 1
                try:
                    self._execute_task(db, task)
                    result["success"] += 1
                    result["details"].append({
                        "task_id": task.id,
                        "order_id": task.order_id,
                        "task_type": task.task_type,
                        "symbol": task.symbol,
                        "amount": task.amount,
                        "status": "success",
                    })
                except Exception as exc:
                    result["failed"] += 1
                    task.status = SettlementStatus.FAILED
                    task.error_message = str(exc)
                    db.commit()
                    result["details"].append({
                        "task_id": task.id,
                        "order_id": task.order_id,
                        "task_type": task.task_type,
                        "symbol": task.symbol,
                        "amount": task.amount,
                        "status": "failed",
                        "error": str(exc),
                    })
                    logger.error("settlement_task_failed", task_id=task.id, error=str(exc))

            logger.info(
                "daily_settlement_completed",
                target_date=target_date.isoformat(),
                processed=result["processed"],
                success=result["success"],
                failed=result["failed"],
            )
            return result
        finally:
            db.close()

    def _execute_task(self, db, task: SettlementTask) -> None:
        """执行单个交收任务"""
        if task.task_type == "cash_release":
            # 买入交收：冻结资金 → 实际扣减
            self._release_frozen_cash(db, task.user_id, task.amount)
        elif task.task_type == "position_add":
            # 买入交收：增加实际持仓
            self._add_position(db, task.user_id, task.symbol, task.amount)
        elif task.task_type == "position_release":
            # 卖出交收：冻结持仓 → 实际扣减
            self._release_frozen_position(db, task.user_id, task.symbol, task.amount)
        elif task.task_type == "cash_deduct":
            # 卖出交收：增加可用资金
            self._add_available_cash(db, task.user_id, task.amount)

        task.status = SettlementStatus.SETTLED
        task.executed_at = datetime.now(timezone.utc)
        db.commit()

    def _release_frozen_cash(self, db, user_id: int, amount: float) -> None:
        """释放冻结资金（买入交收）"""
        portfolio = db.query(MockPortfolio).filter(MockPortfolio.user_id == user_id).first()
        if portfolio:
            portfolio.frozen_cash = max(0, portfolio.frozen_cash - amount)
            # available_cash 不动（成交时已扣减），frozen_cash 释放后变成 position_value
            db.commit()

    def _add_position(self, db, user_id: int, symbol: str, quantity: float) -> None:
        """增加实际持仓（买入交收）"""
        position = (
            db.query(Position)
            .filter(Position.user_id == user_id, Position.symbol == symbol)
            .first()
        )
        if position:
            total_cost = position.avg_cost * position.total_quantity + position.avg_cost * quantity
            position.total_quantity += quantity
            position.available_quantity += quantity
            db.commit()
        else:
            # 持仓不存在时创建（T+1/T+2 买入交收）
            # 从订单中查找成交价作为 avg_cost
            from app.trading.models import Order as OrderModel, Position as PositionModel
            order = db.query(OrderModel).filter(
                OrderModel.user_id == user_id,
                OrderModel.symbol == symbol,
                OrderModel.side == "buy",
            ).order_by(OrderModel.created_at.desc()).first()
            avg_cost = order.filled_price if order else 0

            pos = PositionModel(
                user_id=user_id,
                market="A",
                symbol=symbol,
                total_quantity=quantity,
                available_quantity=quantity,
                frozen_quantity=0,
                avg_cost=avg_cost,
                trade_type=order.trade_type if order else "normal",
            )
            db.add(pos)
            db.commit()

    def _release_frozen_position(self, db, user_id: int, symbol: str, quantity: float) -> None:
        """释放冻结持仓（卖出交收）"""
        position = (
            db.query(Position)
            .filter(Position.user_id == user_id, Position.symbol == symbol)
            .first()
        )
        if position:
            position.frozen_quantity = max(0, position.frozen_quantity - quantity)
            position.total_quantity = max(0, position.total_quantity - quantity)
            db.commit()

    def _add_available_cash(self, db, user_id: int, amount: float) -> None:
        """增加可用资金（卖出交收）"""
        portfolio = db.query(MockPortfolio).filter(MockPortfolio.user_id == user_id).first()
        if portfolio:
            portfolio.available_cash += amount
            # 总资产增加（卖出获利）
            portfolio.total_assets += amount
            db.commit()

    def _next_trading_day(self, base_date: datetime, days: int) -> datetime:
        """计算下一个交易日（简化：直接加天数，忽略节假日）"""
        return base_date + timedelta(days=days)


# 全局交收引擎实例
settlement_engine = SettlementEngine()


def run_daily_settlement(target_date: datetime | None = None) -> dict[str, Any]:
    """日终交收入口"""
    return settlement_engine.run_daily_settlement(target_date)
