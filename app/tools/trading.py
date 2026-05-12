"""
UF Stock Assistant — 模拟交易工具（多业务类型支持）
支持普通委托、大宗交易、港股通、ETF 等业务的模拟下单、持仓管理、订单查询
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.core.constants import (
    OrderSide,
    OrderStatus,
    OrderType,
    SettlementMode,
    SettlementStatus,
    TradeType,
)
from app.core.exceptions import OrderError, TradingError
from app.core.logging import get_logger
from app.trading.fees import calculate_fees, check_block_trade_limits, get_settlement_mode
from app.trading.models import (
    MockPortfolio,
    Order,
    Position,
    Security,
    SettlementTask,
    get_db_session,
)
from app.trading.settlement_engine import settlement_engine
from app.tools.stock_data import get_stock_realtime

logger = get_logger("app.tools.trading")


# =============================================================================
# 按用户隔离的模拟交易后端
# =============================================================================

class MockTradingBackend:
    """模拟交易后端（按用户隔离，支持多业务类型）"""

    def __init__(self, user_id: int, initial_capital: float = 5_000_000.0) -> None:
        self.user_id = user_id
        self.initial_capital = initial_capital

    # ── 资产账户 ──────────────────────────────────────────────────────────────

    def _get_or_create_portfolio(self, db) -> MockPortfolio:
        """获取或创建用户的资产账户"""
        portfolio = db.query(MockPortfolio).filter(MockPortfolio.user_id == self.user_id).first()
        if not portfolio:
            portfolio = MockPortfolio(
                user_id=self.user_id,
                initial_capital=self.initial_capital,
                total_assets=self.initial_capital,
                available_cash=self.initial_capital,
                frozen_cash=0,
                position_value=0,
                total_pnl=0,
            )
            db.add(portfolio)
            db.commit()
            db.refresh(portfolio)
            logger.info("portfolio_created", user_id=self.user_id, initial_capital=self.initial_capital)
        return portfolio

    def _get_position(self, db, symbol: str, trade_type: TradeType) -> Position | None:
        """获取指定证券的持仓"""
        return (
            db.query(Position)
            .filter(
                Position.user_id == self.user_id,
                Position.symbol == symbol,
                Position.trade_type == trade_type,
            )
            .first()
        )

    def _get_or_create_position(self, db, symbol: str, trade_type: TradeType) -> Position:
        """获取或创建持仓"""
        pos = self._get_position(db, symbol, trade_type)
        if not pos:
            pos = Position(
                user_id=self.user_id,
                market="A" if trade_type in (TradeType.NORMAL, TradeType.BLOCK_TRADE) else "HK",
                symbol=symbol,
                total_quantity=0,
                available_quantity=0,
                frozen_quantity=0,
                avg_cost=0,
                trade_type=trade_type,
            )
            db.add(pos)
            db.commit()
            db.refresh(pos)
        # 补充名称（优先本地 securities 表）
        if not pos.name:
            try:
                sec = db.query(Security).filter(Security.symbol == symbol).first()
                if sec and sec.name:
                    pos.name = sec.name
                    db.commit()
            except Exception:
                pass
        return pos

    # ── 订单提交 ──────────────────────────────────────────────────────────────

    def submit_order(
        self,
        db,
        symbol: str,
        side: str,
        quantity: float,
        price: float | None,
        order_type: str,
        trade_type: TradeType,
        exchange_code: str = "SH",
    ) -> dict[str, Any]:
        """提交订单（即时成交，取消交收冻结机制）"""
        portfolio = self._get_or_create_portfolio(db)

        # 参数校验
        if side not in (OrderSide.BUY.value, OrderSide.SELL.value):
            raise TradingError(f"无效的订单方向: {side}")

        if quantity <= 0:
            raise TradingError("数量必须大于 0")

        # 确定成交价（市价单查询本地 securities 表最新价）
        if price is None or price <= 0:
            try:
                sec = db.query(Security).filter(Security.symbol == symbol).first()
                if sec and sec.price:
                    filled_price = sec.price
                else:
                    filled_price = 0
            except Exception:
                filled_price = 0
        else:
            filled_price = price

        if filled_price <= 0:
            raise TradingError(f"无法获取 {symbol} 的当前价格，请填写委托价格")

        # 计算费用
        fee_result = calculate_fees(trade_type, side, quantity, filled_price, exchange_code=exchange_code)
        total_cost = quantity * filled_price + float(fee_result.total)

        # 大宗交易限额检查
        if trade_type == TradeType.BLOCK_TRADE:
            ok, msg = check_block_trade_limits(trade_type, symbol, quantity, filled_price, exchange_code)
            if not ok:
                raise TradingError(msg)

        # 限价单涨跌停校验（从本地 securities 表获取）
        if price is not None and price > 0:
            try:
                sec = db.query(Security).filter(Security.symbol == symbol).first()
                if sec:
                    if sec.limit_up is not None and price > sec.limit_up:
                        raise TradingError(f"委托价 {price:.2f} 超过涨停价 {sec.limit_up:.2f}")
                    if sec.limit_down is not None and price < sec.limit_down:
                        raise TradingError(f"委托价 {price:.2f} 低于跌停价 {sec.limit_down:.2f}")
            except TradingError:
                raise
            except Exception:
                pass

        # 资金/持仓校验
        if side == OrderSide.BUY.value:
            if total_cost > portfolio.available_cash:
                raise TradingError(
                    f"可用资金不足：需要 ¥{total_cost:,.2f}（含费用），"
                    f"当前可用 ¥{portfolio.available_cash:,.2f}"
                )
        else:
            pos = self._get_position(db, symbol, trade_type)
            if not pos or pos.total_quantity < quantity:
                available = pos.total_quantity if pos else 0
                raise TradingError(
                    f"持仓不足：尝试卖出 {quantity}，当前持有 {available}"
                )

        # 创建订单记录
        order = Order(
            user_id=self.user_id,
            market=exchange_code,
            symbol=symbol.upper(),
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            status=OrderStatus.FILLED,
            filled_quantity=quantity,
            filled_price=filled_price,
            trade_type=trade_type,
            settlement_mode="T+0",
            settlement_status=SettlementStatus.SETTLED,
            commission=float(fee_result.commission),
            stamp_tax=float(fee_result.stamp_tax),
            exchange_fee=float(fee_result.exchange_fee),
            transfer_fee=float(fee_result.transfer_fee),
            system_fee=float(fee_result.system_fee),
            portfolio_fee=float(fee_result.portfolio_fee),
            other_fees=float(fee_result.other_fees),
            total_fee=float(fee_result.total),
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        # 即时更新资金和持仓
        self._update_assets_on_fill(db, portfolio, side, symbol, trade_type, quantity, filled_price, float(fee_result.total))

        logger.info(
            "order_submitted",
            user_id=self.user_id,
            order_id=order.id,
            symbol=symbol,
            side=side,
            trade_type=trade_type,
            quantity=quantity,
            price=filled_price,
            fees=fee_result.to_dict(),
        )

        return {
            "order_id": order.id,
            "symbol": order.symbol,
            "side": order.side,
            "quantity": order.quantity,
            "price": order.price,
            "filled_price": order.filled_price,
            "status": order.status,
            "trade_type": order.trade_type,
            "settlement_mode": "T+0",
            "fees": fee_result.to_dict(),
            "created_at": order.created_at.isoformat() if order.created_at else None,
        }

    def _update_assets_on_fill(
        self,
        db,
        portfolio: MockPortfolio,
        side: str,
        symbol: str,
        trade_type: TradeType,
        quantity: float,
        price: float,
        total_fee: float,
    ) -> None:
        """成交时即时更新资产（买入即持仓，卖出即到账）"""
        if side == OrderSide.BUY.value:
            total_cost = quantity * price + total_fee
            portfolio.available_cash -= total_cost
            self._add_position(db, symbol, trade_type, quantity, price)
        else:
            total_income = quantity * price - total_fee
            self._deduct_position(db, symbol, trade_type, quantity, price, total_fee)
            portfolio.available_cash += total_income

        # 持仓市值 = 所有持仓 total_quantity * avg_cost（简化，无实时行情时用成本价）
        positions = db.query(Position).filter(Position.user_id == self.user_id).all()
        portfolio.position_value = sum(p.total_quantity * (p.current_price or p.avg_cost) for p in positions)
        portfolio.total_assets = portfolio.available_cash + portfolio.position_value
        portfolio.frozen_cash = 0
        db.commit()

    def _add_position(self, db, symbol: str, trade_type: TradeType, quantity: float, price: float) -> None:
        """增加持仓（买入）"""
        pos = self._get_or_create_position(db, symbol, trade_type)
        total_cost = pos.avg_cost * pos.total_quantity + price * quantity
        pos.total_quantity += quantity
        pos.available_quantity += quantity
        pos.avg_cost = total_cost / pos.total_quantity if pos.total_quantity > 0 else 0
        db.commit()

    def _deduct_position(self, db, symbol: str, trade_type: TradeType, quantity: float, price: float, fee: float) -> None:
        """扣减持仓（卖出），计算已实现收益"""
        pos = self._get_position(db, symbol, trade_type)
        if not pos:
            return
        # 已实现收益 = (卖出价 - 成本价) * 数量 - 费用
        realized = (price - pos.avg_cost) * quantity - fee
        pos.realized_pnl += realized
        pos.total_quantity = max(0, pos.total_quantity - quantity)
        pos.available_quantity = max(0, pos.available_quantity - quantity)
        if pos.total_quantity == 0:
            pos.avg_cost = 0
            pos.unrealized_pnl = 0
        db.commit()

    # ── 查询 ────────────────────────────────────────────────────────────────────

    def get_positions(self, db, trade_type: TradeType | None = None) -> list[dict[str, Any]]:
        """获取持仓列表（字段对齐前端）"""
        query = db.query(Position).filter(Position.user_id == self.user_id)
        if trade_type:
            query = query.filter(Position.trade_type == trade_type)
        positions = query.all()
        result = []
        for p in positions:
            if p.total_quantity <= 0:
                continue
            # 补充名称（优先本地 securities 表）
            name = p.name
            if not name:
                try:
                    sec = db.query(Security).filter(Security.symbol == p.symbol).first()
                    if sec and sec.name:
                        name = sec.name
                        p.name = name
                        db.commit()
                except Exception:
                    pass
            price = p.current_price or p.avg_cost or 0
            market_value = round(price * p.total_quantity, 2)
            cost_basis = p.avg_cost * p.total_quantity
            pnl = round(market_value - cost_basis, 2) if p.avg_cost else 0
            pnl_percent = round(pnl / cost_basis * 100, 2) if cost_basis else 0

            # 累计买入费用
            total_fee = 0.0
            try:
                from sqlalchemy import func as sa_func
                fee_sum = db.query(sa_func.sum(Order.total_fee)).filter(
                    Order.user_id == self.user_id,
                    Order.symbol == p.symbol,
                    Order.side == OrderSide.BUY.value,
                ).scalar()
                if fee_sum:
                    total_fee = round(float(fee_sum), 2)
            except Exception:
                pass

            result.append({
                "id": p.id,
                "symbol": p.symbol,
                "name": name or p.symbol,
                "market": p.market,
                "quantity": p.total_quantity,
                "available_quantity": p.available_quantity,
                "frozen_quantity": p.frozen_quantity,
                "avg_cost": round(p.avg_cost, 4) if p.avg_cost else 0,
                "current_price": round(price, 4) if price else 0,
                "market_value": market_value,
                "pnl": pnl,
                "pnl_percent": pnl_percent,
                "unrealized_pnl": round(p.unrealized_pnl, 2) if p.unrealized_pnl else 0,
                "realized_pnl": round(p.realized_pnl, 2) if p.realized_pnl else 0,
                "total_fee": total_fee,
                "trade_type": p.trade_type,
            })
        return result

    def get_orders(self, db, trade_type: TradeType | None = None, status: str | None = None) -> list[dict[str, Any]]:
        """获取订单列表（字段对齐前端）"""
        query = db.query(Order).filter(Order.user_id == self.user_id)
        if trade_type:
            query = query.filter(Order.trade_type == trade_type)
        if status:
            query = query.filter(Order.status == status)
        orders = query.order_by(Order.created_at.desc()).all()
        return [
            {
                "id": o.id,
                "order_id": o.id,
                "market": o.market,
                "symbol": o.symbol,
                "side": o.side,
                "order_type": o.order_type,
                "quantity": o.quantity,
                "price": o.price,
                "filled_price": o.filled_price,
                "status": o.status,
                "trade_type": o.trade_type,
                "settlement_mode": o.settlement_mode,
                "settlement_status": o.settlement_status,
                "total_fee": round(o.total_fee, 2) if o.total_fee else 0,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in orders
        ]

    def get_portfolio_summary(self, db) -> dict[str, Any]:
        """获取投资组合摘要（即时生效模型）"""
        portfolio = self._get_or_create_portfolio(db)

        positions = db.query(Position).filter(Position.user_id == self.user_id).all()

        # 持仓市值 = 各持仓数量 * (当前价 or 成本价)
        position_value = sum(
            (p.current_price or p.avg_cost) * p.total_quantity for p in positions
        )

        # 计算各持仓浮盈
        for p in positions:
            if p.total_quantity > 0 and p.avg_cost > 0:
                market_price = p.current_price or p.avg_cost
                p.unrealized_pnl = (market_price - p.avg_cost) * p.total_quantity
            else:
                p.unrealized_pnl = 0

        # 总资产 = 可用资金 + 持仓市值（冻结资金始终为 0）
        total_assets = portfolio.available_cash + position_value
        total_pnl = sum(p.realized_pnl + (p.unrealized_pnl or 0) for p in positions)
        total_pnl_percent = round((total_pnl / portfolio.initial_capital * 100), 2) if portfolio.initial_capital > 0 else 0

        portfolio.position_value = position_value
        portfolio.total_assets = total_assets
        portfolio.total_pnl = total_pnl
        portfolio.frozen_cash = 0
        db.commit()

        return {
            "total_assets": round(total_assets, 2),
            "available_cash": round(portfolio.available_cash, 2),
            "frozen_cash": 0,
            "position_value": round(position_value, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_percent": total_pnl_percent,
            "initial_capital": round(portfolio.initial_capital, 2),
            "total_positions": len(positions),
        }


# 全局模拟交易后端实例池（按 user_id 隔离）
_backends: dict[int, MockTradingBackend] = {}


def _get_or_create_backend(user_id: int, initial_capital: float = 5_000_000.0) -> MockTradingBackend:
    """获取或创建用户的模拟交易后端"""
    if user_id in _backends:
        return _backends[user_id]
    backend = MockTradingBackend(user_id=user_id, initial_capital=initial_capital)
    _backends[user_id] = backend
    logger.info("mock_backend_created", user_id=user_id, initial_capital=initial_capital)
    return backend


# =============================================================================
# 交易工具函数（按用户隔离）
# =============================================================================

def submit_order(
    user_id: int,
    symbol: str,
    side: str,
    quantity: float,
    price: float | None = None,
    order_type: str = "market",
    trade_type: str = TradeType.NORMAL,
    exchange_code: str = "SH",
) -> dict[str, Any]:
    """提交交易订单（支持多业务类型）"""
    db = get_db_session()
    try:
        backend = _get_or_create_backend(user_id)
        return backend.submit_order(
            db=db,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
            trade_type=trade_type,
            exchange_code=exchange_code,
        )
    except TradingError:
        raise
    except Exception as exc:
        logger.error("order_failed", user_id=user_id, symbol=symbol, side=side, error=str(exc))
        raise OrderError(f"提交订单失败: {exc}") from exc
    finally:
        db.close()


def get_positions(user_id: int, trade_type: str | None = None) -> dict[str, Any]:
    """获取持仓列表"""
    db = get_db_session()
    try:
        backend = _get_or_create_backend(user_id)
        positions = backend.get_positions(db, trade_type)
        summary = backend.get_portfolio_summary(db)
        return {"positions": positions, "summary": summary}
    except Exception as exc:
        logger.error("get_positions_failed", user_id=user_id, error=str(exc))
        raise TradingError(f"获取持仓失败: {exc}") from exc
    finally:
        db.close()


def get_orders(user_id: int, trade_type: str | None = None, status: str | None = None) -> dict[str, Any]:
    """获取订单列表"""
    db = get_db_session()
    try:
        backend = _get_or_create_backend(user_id)
        orders = backend.get_orders(db, trade_type, status)
        return {"count": len(orders), "orders": orders}
    except Exception as exc:
        logger.error("get_orders_failed", user_id=user_id, error=str(exc))
        raise TradingError(f"获取订单失败: {exc}") from exc
    finally:
        db.close()


def get_portfolio(user_id: int) -> dict[str, Any]:
    """获取投资组合摘要"""
    db = get_db_session()
    try:
        backend = _get_or_create_backend(user_id)
        summary = backend.get_portfolio_summary(db)
        positions = backend.get_positions(db)
        return {"summary": summary, "positions": positions}
    except Exception as exc:
        logger.error("get_portfolio_failed", user_id=user_id, error=str(exc))
        raise TradingError(f"获取投资组合失败: {exc}") from exc
    finally:
        db.close()


def cancel_order(user_id: int, order_id: str) -> dict[str, Any]:
    """取消订单（简化：仅支持未成交订单）"""
    db = get_db_session()
    try:
        order = db.query(Order).filter(Order.id == order_id, Order.user_id == user_id).first()
        if not order:
            return {"success": False, "message": "订单不存在"}
        if order.status in (OrderStatus.FILLED.value, OrderStatus.CANCELLED.value, OrderStatus.REJECTED.value):
            return {"success": False, "message": "订单已成交或已取消"}

        order.status = OrderStatus.CANCELLED
        order.updated_at = datetime.now(timezone.utc)
        db.commit()

        # 解冻资金和持仓
        backend = _get_or_create_backend(user_id)
        portfolio = backend._get_or_create_portfolio(db)
        if order.side == OrderSide.BUY.value and order.frozen_cash > 0:
            portfolio.frozen_cash = max(0, portfolio.frozen_cash - order.frozen_cash)
            portfolio.available_cash += order.frozen_cash
        elif order.side == OrderSide.SELL.value and order.frozen_position > 0:
            pos = backend._get_position(db, order.symbol, order.trade_type)
            if pos:
                pos.frozen_quantity = max(0, pos.frozen_quantity - order.frozen_position)
                pos.available_quantity += order.frozen_position

        db.commit()
        logger.info("order_cancelled", user_id=user_id, order_id=order_id)
        return {"success": True, "message": "订单已取消"}
    except Exception as exc:
        logger.error("cancel_order_failed", user_id=user_id, order_id=order_id, error=str(exc))
        raise TradingError(f"取消订单失败: {exc}") from exc
    finally:
        db.close()
