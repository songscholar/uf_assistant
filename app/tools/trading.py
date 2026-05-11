"""
UF Stock Assistant — 模拟交易工具
支持模拟下单、持仓管理、订单查询
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.constants import OrderSide, OrderStatus, OrderType
from app.core.exceptions import OrderError, TradingError
from app.core.logging import get_logger

logger = get_logger("app.tools.trading")


# =============================================================================
# 内存中的模拟交易数据（实际项目中应使用数据库）
# =============================================================================

class MockTradingBackend:
    """模拟交易后端（内存存储）"""
    
    def __init__(self) -> None:
        self._positions: dict[str, dict[str, Any]] = {}  # symbol -> position
        self._orders: dict[str, dict[str, Any]] = {}  # order_id -> order
        self._order_history: list[dict[str, Any]] = []
    
    def submit_order(self, order: dict[str, Any]) -> dict[str, Any]:
        """提交订单"""
        order_id = str(uuid.uuid4())
        order["id"] = order_id
        order["status"] = OrderStatus.FILLED.value  # 模拟立即成交
        order["filled_quantity"] = order["quantity"]
        order["filled_price"] = order.get("price") or order.get("market_price", 0)
        order["created_at"] = datetime.now(timezone.utc).isoformat()
        order["updated_at"] = order["created_at"]
        
        self._orders[order_id] = order
        self._order_history.append(order)
        
        # 更新持仓
        self._update_position(order)
        
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
            # 买入：更新平均成本
            total_cost = pos["total_cost"] + qty * price
            total_qty = pos["quantity"] + qty
            pos["quantity"] = total_qty
            pos["avg_cost"] = total_cost / total_qty if total_qty > 0 else 0
            pos["total_cost"] = total_cost
        else:
            # 卖出：计算实现盈亏
            if pos["quantity"] >= qty:
                realized = (price - pos["avg_cost"]) * qty
                pos["realized_pnl"] += realized
                pos["quantity"] -= qty
                pos["total_cost"] = pos["quantity"] * pos["avg_cost"]
                if pos["quantity"] == 0:
                    pos["avg_cost"] = 0
                    pos["total_cost"] = 0
        
        # 更新市值（使用成交价格作为当前价格）
        pos["market_value"] = pos["quantity"] * price
        pos["unrealized_pnl"] = (price - pos["avg_cost"]) * pos["quantity"] if pos["quantity"] > 0 else 0
    
    def get_positions(self) -> list[dict[str, Any]]:
        """获取持仓"""
        return [pos for pos in self._positions.values() if pos["quantity"] > 0]
    
    def get_position(self, symbol: str) -> dict[str, Any] | None:
        """获取单个持仓"""
        pos = self._positions.get(symbol)
        if pos and pos["quantity"] > 0:
            return pos
        return None
    
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
    
    def get_portfolio_summary(self) -> dict[str, Any]:
        """获取投资组合摘要"""
        positions = self.get_positions()
        total_market_value = sum(p["market_value"] for p in positions)
        total_cost = sum(p["total_cost"] for p in positions)
        total_unrealized = sum(p["unrealized_pnl"] for p in positions)
        total_realized = sum(p["realized_pnl"] for p in positions)
        
        return {
            "total_positions": len(positions),
            "total_market_value": round(total_market_value, 2),
            "total_cost": round(total_cost, 2),
            "total_unrealized_pnl": round(total_unrealized, 2),
            "total_realized_pnl": round(total_realized, 2),
            "return_pct": round((total_unrealized / total_cost * 100), 2) if total_cost > 0 else 0,
        }


# 全局模拟交易后端实例
_mock_backend = MockTradingBackend()


# =============================================================================
# 交易工具函数
# =============================================================================

def submit_order(
    symbol: str,
    side: str,
    quantity: float,
    price: float | None = None,
    order_type: str = "market",
) -> dict[str, Any]:
    """
    提交交易订单（模拟）
    
    Args:
        symbol: 股票代码
        side: buy 或 sell
        quantity: 数量
        price: 价格（限价单必填）
        order_type: market/limit/stop/stop_limit
        
    Returns:
        JSON 格式的订单结果
    """
    try:
        # 参数校验
        if side not in (OrderSide.BUY.value, OrderSide.SELL.value):
            raise TradingError(f"无效的订单方向: {side}")
        
        if order_type not in (OrderType.MARKET.value, OrderType.LIMIT.value, OrderType.STOP.value, OrderType.STOP_LIMIT.value):
            raise TradingError(f"无效的订单类型: {order_type}")
        
        if order_type == OrderType.LIMIT.value and price is None:
            raise TradingError("限价单必须指定价格")
        
        if quantity <= 0:
            raise TradingError("数量必须大于 0")
        
        # 构建订单
        order = {
            "symbol": symbol.upper(),
            "side": side.lower(),
            "quantity": quantity,
            "price": price,
            "order_type": order_type.lower(),
        }
        
        # 模拟获取市场价格（实际应从行情工具获取）
        if order_type == OrderType.MARKET.value:
            order["market_price"] = price or 0  # 简化处理
        
        result = _mock_backend.submit_order(order)
        
        logger.info(
            "order_submitted",
            order_id=result["id"],
            symbol=symbol,
            side=side,
            quantity=quantity,
        )
        
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
        logger.error("order_failed", symbol=symbol, side=side, error=str(exc))
        raise OrderError(f"提交订单失败: {exc}") from exc


def get_positions() -> dict[str, Any]:
    """
    获取当前持仓
    
    Returns:
        持仓列表和摘要
    """
    try:
        positions = _mock_backend.get_positions()
        summary = _mock_backend.get_portfolio_summary()
        
        return {
            "positions": positions,
            "summary": summary,
        }
        
    except Exception as exc:
        logger.error("get_positions_failed", error=str(exc))
        raise TradingError(f"获取持仓失败: {exc}") from exc


def get_position(symbol: str) -> dict[str, Any]:
    """
    获取指定股票持仓
    
    Args:
        symbol: 股票代码
        
    Returns:
        持仓数据
    """
    try:
        pos = _mock_backend.get_position(symbol.upper())
        
        if not pos:
            return {"symbol": symbol, "has_position": False}
        
        return {"has_position": True, "position": pos}
        
    except Exception as exc:
        logger.error("get_position_failed", symbol=symbol, error=str(exc))
        raise TradingError(f"获取持仓失败: {exc}") from exc


def get_orders(status: str | None = None) -> dict[str, Any]:
    """
    获取订单列表
    
    Args:
        status: 订单状态过滤（pending/submitted/filled/cancelled/rejected）
        
    Returns:
        订单列表
    """
    try:
        orders = _mock_backend.get_orders(status)
        
        return {
            "count": len(orders),
            "orders": orders,
        }
        
    except Exception as exc:
        logger.error("get_orders_failed", error=str(exc))
        raise TradingError(f"获取订单失败: {exc}") from exc


def cancel_order(order_id: str) -> dict[str, Any]:
    """
    取消订单
    
    Args:
        order_id: 订单 ID
        
    Returns:
        取消结果
    """
    try:
        success = _mock_backend.cancel_order(order_id)
        
        if success:
            logger.info("order_cancelled", order_id=order_id)
            return {"success": True, "message": "订单已取消"}
        else:
            return {"success": False, "message": "订单无法取消（可能已成交或不存在）"}
        
    except Exception as exc:
        logger.error("cancel_order_failed", order_id=order_id, error=str(exc))
        raise TradingError(f"取消订单失败: {exc}") from exc


def get_portfolio() -> dict[str, Any]:
    """
    获取投资组合摘要
    
    Returns:
        投资组合数据
    """
    try:
        summary = _mock_backend.get_portfolio_summary()
        positions = _mock_backend.get_positions()
        
        return {
            "summary": summary,
            "positions": positions,
        }
        
    except Exception as exc:
        logger.error("get_portfolio_failed", error=str(exc))
        raise TradingError(f"获取投资组合失败: {exc}") from exc
