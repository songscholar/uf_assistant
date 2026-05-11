"""
UF Stock Assistant — 模拟交易工具
支持模拟下单、持仓管理、订单查询、资金校验
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.constants import OrderSide, OrderStatus, OrderType
from app.core.exceptions import OrderError, TradingError
from app.core.logging import get_logger

logger = get_logger("app.tools.trading")

# 默认手续费率
COMMISSION_RATE = 0.0003  # 佣金 0.03%
STAMP_TAX_RATE = 0.001    # 印花税 0.1%（卖出时收取）


# =============================================================================
# 按用户隔离的模拟交易后端
# =============================================================================

class MockTradingBackend:
    """模拟交易后端（按用户隔离，内存存储）"""

    def __init__(self, user_id: int, initial_capital: float = 5_000_000.0) -> None:
        self.user_id = user_id
        self.initial_capital = initial_capital
        self.available_cash = initial_capital
        self._positions: dict[str, dict[str, Any]] = {}  # symbol -> position
        self._orders: dict[str, dict[str, Any]] = {}  # order_id -> order
        self._order_history: list[dict[str, Any]] = []

    # ── 订单 ──────────────────────────────────────────────────────────────────

    def submit_order(self, order: dict[str, Any]) -> dict[str, Any]:
        """提交订单（含资金/持仓校验）"""
        order_id = str(uuid.uuid4())
        order["id"] = order_id
        side = order["side"]
        qty = order["quantity"]
        price = order.get("price") or order.get("market_price", 0)

        # 资金/持仓校验
        if side == OrderSide.BUY.value:
            cost = qty * price * (1 + COMMISSION_RATE)
            if cost > self.available_cash:
                raise TradingError(
                    f"可用资金不足：需要 ¥{cost:,.2f}，当前可用 ¥{self.available_cash:,.2f}"
                )
        else:
            pos = self._positions.get(order["symbol"])
            if not pos or pos["quantity"] < qty:
                hold_qty = pos["quantity"] if pos else 0
                raise TradingError(
                    f"持仓不足：尝试卖出 {qty}，当前持仓 {hold_qty}"
                )

        # 模拟立即成交
        order["status"] = OrderStatus.FILLED.value
        order["filled_quantity"] = qty
        order["filled_price"] = price
        order["created_at"] = datetime.now(timezone.utc).isoformat()
        order["updated_at"] = order["created_at"]

        # 扣费/加钱
        if side == OrderSide.BUY.value:
            commission = qty * price * COMMISSION_RATE
            self.available_cash -= (qty * price + commission)
        else:
            commission = qty * price * COMMISSION_RATE
            stamp_tax = qty * price * STAMP_TAX_RATE
            self.available_cash += (qty * price - commission - stamp_tax)

        self._orders[order_id] = order
        self._order_history.append(order)

        # 更新持仓
        self._update_position(order)

        logger.info(
            "mock_order_filled",
            user_id=self.user_id,
            order_id=order_id,
            symbol=order["symbol"],
            side=side,
            quantity=qty,
            price=price,
            available_cash=self.available_cash,
        )
        return order

    def _update_position(self, order: dict[str, Any]) -> None:
        """更新持仓"""
        symbol = order["symbol"]
        side = order["side"]
        qty = order["quantity"]
        price = order.get("filled_price", 0)

        if symbol not in self._positions:
            self._positions[symbol] = {
                "symbol": symbol,
                "quantity": 0,
                "avg_cost": 0,
                "total_cost": 0,
                "market_value": 0,
                "unrealized_pnl": 0,
                "realized_pnl": 0,
            }

        pos = self._positions[symbol]

        if side == OrderSide.BUY.value:
            total_cost = pos["total_cost"] + qty * price
            total_qty = pos["quantity"] + qty
            pos["quantity"] = total_qty
            pos["avg_cost"] = total_cost / total_qty if total_qty > 0 else 0
            pos["total_cost"] = total_cost
        else:
            if pos["quantity"] >= qty:
                realized = (price - pos["avg_cost"]) * qty
                pos["realized_pnl"] += realized
                pos["quantity"] -= qty
                pos["total_cost"] = pos["quantity"] * pos["avg_cost"]
                if pos["quantity"] == 0:
                    pos["avg_cost"] = 0
                    pos["total_cost"] = 0

        pos["market_value"] = pos["quantity"] * price
        pos["unrealized_pnl"] = (price - pos["avg_cost"]) * pos["quantity"] if pos["quantity"] > 0 else 0

    def get_orders(self, status: str | None = None) -> list[dict[str, Any]]:
        """获取订单列表"""
        orders = list(self._orders.values())
        if status:
            orders = [o for o in orders if o["status"] == status]
        return sorted(orders, key=lambda x: x["created_at"], reverse=True)

    def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        order = self._orders.get(order_id)
        if not order:
            return False
        if order["status"] in (OrderStatus.FILLED.value, OrderStatus.CANCELLED.value, OrderStatus.REJECTED.value):
            return False

        order["status"] = OrderStatus.CANCELLED.value
        order["updated_at"] = datetime.now(timezone.utc).isoformat()
        return True

    # ── 持仓 ──────────────────────────────────────────────────────────────────

    def get_positions(self) -> list[dict[str, Any]]:
        """获取持仓"""
        return [pos for pos in self._positions.values() if pos["quantity"] > 0]

    def get_position(self, symbol: str) -> dict[str, Any] | None:
        """获取单个持仓"""
        pos = self._positions.get(symbol)
        if pos and pos["quantity"] > 0:
            return pos
        return None

    # ── 资产 ──────────────────────────────────────────────────────────────────

    def get_portfolio_summary(self) -> dict[str, Any]:
        """获取投资组合摘要（返回前端需要的字段格式）"""
        positions = self.get_positions()
        position_value = sum(p["market_value"] for p in positions)
        total_cost = sum(p["total_cost"] for p in positions)
        total_unrealized = sum(p["unrealized_pnl"] for p in positions)
        total_realized = sum(p["realized_pnl"] for p in positions)
        total_assets = self.available_cash + position_value
        total_pnl = total_unrealized + total_realized
        total_pnl_percent = round((total_pnl / total_cost * 100), 2) if total_cost > 0 else 0

        return {
            "total_assets": round(total_assets, 2),
            "available_cash": round(self.available_cash, 2),
            "position_value": round(position_value, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_percent": total_pnl_percent,
            "total_positions": len(positions),
            "total_market_value": round(position_value, 2),
            "total_cost": round(total_cost, 2),
            "total_unrealized_pnl": round(total_unrealized, 2),
            "total_realized_pnl": round(total_realized, 2),
            "return_pct": total_pnl_percent,
        }


# 全局模拟交易后端实例池（按 user_id 隔离）
_mock_backends: dict[int, MockTradingBackend] = {}


def _get_or_create_backend(user_id: int) -> MockTradingBackend:
    """获取或创建用户的模拟交易后端"""
    if user_id in _mock_backends:
        return _mock_backends[user_id]

    # 从 users 表加载初始资金
    initial = 5_000_000.0
    available = 5_000_000.0
    try:
        from sqlalchemy import text
        from app.core.config import get_settings
        from sqlalchemy import create_engine
        engine = create_engine(get_settings().database.url, echo=False)
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT mock_initial_capital, mock_available_cash FROM users WHERE id = :uid"),
                {"uid": user_id},
            ).fetchone()
            if row:
                initial = float(row[0]) if row[0] is not None else 5_000_000.0
                available = float(row[1]) if row[1] is not None else initial
    except Exception:
        pass

    backend = MockTradingBackend(user_id=user_id, initial_capital=initial)
    backend.available_cash = available
    _mock_backends[user_id] = backend
    logger.info("mock_backend_created", user_id=user_id, initial_capital=initial, available_cash=available)
    return backend


def _persist_cash(user_id: int, backend: MockTradingBackend) -> None:
    """将可用资金持久化到 users 表"""
    try:
        from sqlalchemy import text
        from app.core.config import get_settings
        from sqlalchemy import create_engine
        engine = create_engine(get_settings().database.url, echo=False)
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE users SET mock_available_cash = :cash WHERE id = :uid"),
                {"cash": round(backend.available_cash, 2), "uid": user_id},
            )
            conn.commit()
    except Exception as exc:
        logger.warning("persist_cash_failed", user_id=user_id, error=str(exc))


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
) -> dict[str, Any]:
    """
    提交交易订单（模拟）

    Args:
        user_id: 用户ID
        symbol: 股票代码
        side: buy 或 sell
        quantity: 数量
        price: 价格（限价单必填）
        order_type: market/limit/stop/stop_limit

    Returns:
        订单结果
    """
    try:
        if side not in (OrderSide.BUY.value, OrderSide.SELL.value):
            raise TradingError(f"无效的订单方向: {side}")

        if order_type not in (OrderType.MARKET.value, OrderType.LIMIT.value, OrderType.STOP.value, OrderType.STOP_LIMIT.value):
            raise TradingError(f"无效的订单类型: {order_type}")

        if order_type == OrderType.LIMIT.value and price is None:
            raise TradingError("限价单必须指定价格")

        if quantity <= 0:
            raise TradingError("数量必须大于 0")

        backend = _get_or_create_backend(user_id)

        order = {
            "symbol": symbol.upper(),
            "side": side.lower(),
            "quantity": quantity,
            "price": price,
            "order_type": order_type.lower(),
        }

        if order_type == OrderType.MARKET.value:
            order["market_price"] = price or 0

        result = backend.submit_order(order)

        # 持久化资金变动
        _persist_cash(user_id, backend)

        return {
            "success": True,
            "order": {
                "id": result["id"],
                "symbol": result["symbol"],
                "side": result["side"],
                "quantity": result["quantity"],
                "price": result.get("price"),
                "filled_price": result.get("filled_price"),
                "status": result["status"],
                "created_at": result["created_at"],
            }
        }

    except TradingError:
        raise
    except Exception as exc:
        logger.error("order_failed", user_id=user_id, symbol=symbol, side=side, error=str(exc))
        raise OrderError(f"提交订单失败: {exc}") from exc


def get_positions(user_id: int) -> dict[str, Any]:
    """
    获取当前持仓

    Args:
        user_id: 用户ID

    Returns:
        持仓列表和摘要
    """
    try:
        backend = _get_or_create_backend(user_id)
        return {
            "positions": backend.get_positions(),
            "summary": backend.get_portfolio_summary(),
        }
    except Exception as exc:
        logger.error("get_positions_failed", user_id=user_id, error=str(exc))
        raise TradingError(f"获取持仓失败: {exc}") from exc


def get_position(user_id: int, symbol: str) -> dict[str, Any]:
    """
    获取指定股票持仓

    Args:
        user_id: 用户ID
        symbol: 股票代码

    Returns:
        持仓数据
    """
    try:
        backend = _get_or_create_backend(user_id)
        pos = backend.get_position(symbol.upper())

        if not pos:
            return {"symbol": symbol, "has_position": False}

        return {"has_position": True, "position": pos}
    except Exception as exc:
        logger.error("get_position_failed", user_id=user_id, symbol=symbol, error=str(exc))
        raise TradingError(f"获取持仓失败: {exc}") from exc


def get_orders(user_id: int, status: str | None = None) -> dict[str, Any]:
    """
    获取订单列表

    Args:
        user_id: 用户ID
        status: 订单状态过滤

    Returns:
        订单列表
    """
    try:
        backend = _get_or_create_backend(user_id)
        orders = backend.get_orders(status)
        return {
            "count": len(orders),
            "orders": orders,
        }
    except Exception as exc:
        logger.error("get_orders_failed", user_id=user_id, error=str(exc))
        raise TradingError(f"获取订单失败: {exc}") from exc


def cancel_order(user_id: int, order_id: str) -> dict[str, Any]:
    """
    取消订单

    Args:
        user_id: 用户ID
        order_id: 订单 ID

    Returns:
        取消结果
    """
    try:
        backend = _get_or_create_backend(user_id)
        success = backend.cancel_order(order_id)

        if success:
            logger.info("order_cancelled", user_id=user_id, order_id=order_id)
            return {"success": True, "message": "订单已取消"}
        else:
            return {"success": False, "message": "订单无法取消（可能已成交或不存在）"}
    except Exception as exc:
        logger.error("cancel_order_failed", user_id=user_id, order_id=order_id, error=str(exc))
        raise TradingError(f"取消订单失败: {exc}") from exc


def get_portfolio(user_id: int) -> dict[str, Any]:
    """
    获取投资组合摘要

    Args:
        user_id: 用户ID

    Returns:
        投资组合数据
    """
    try:
        backend = _get_or_create_backend(user_id)
        return {
            "summary": backend.get_portfolio_summary(),
            "positions": backend.get_positions(),
        }
    except Exception as exc:
        logger.error("get_portfolio_failed", user_id=user_id, error=str(exc))
        raise TradingError(f"获取投资组合失败: {exc}") from exc
