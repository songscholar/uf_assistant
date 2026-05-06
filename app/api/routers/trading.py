"""
UF Stock Assistant — 交易接口
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.tools.trading import (
    cancel_order,
    get_orders,
    get_portfolio,
    get_position,
    get_positions,
    submit_order,
)

logger = get_logger("app.api.trading")

router = APIRouter()


class OrderRequest(BaseModel):
    """下单请求"""
    symbol: str = Field(..., description="股票代码")
    side: str = Field(..., description="buy 或 sell")
    quantity: float = Field(..., gt=0, description="数量")
    price: float | None = Field(None, description="价格（限价单必填）")
    order_type: str = Field("market", description="market/limit/stop/stop_limit")


@router.post("/trading/order")
async def place_order(request: OrderRequest):
    """提交订单"""
    try:
        return submit_order(
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            price=request.price,
            order_type=request.order_type,
        )
    except Exception as exc:
        logger.error("place_order_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/trading/positions")
async def positions():
    """获取持仓"""
    try:
        return get_positions()
    except Exception as exc:
        logger.error("positions_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/trading/position/{symbol}")
async def position(symbol: str):
    """获取指定股票持仓"""
    try:
        return get_position(symbol)
    except Exception as exc:
        logger.error("position_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/trading/orders")
async def orders(status: str | None = None):
    """获取订单列表"""
    try:
        return get_orders(status)
    except Exception as exc:
        logger.error("orders_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/trading/orders/{order_id}")
async def cancel(order_id: str):
    """取消订单"""
    try:
        return cancel_order(order_id)
    except Exception as exc:
        logger.error("cancel_error", order_id=order_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/trading/portfolio")
async def portfolio():
    """获取投资组合"""
    try:
        return get_portfolio()
    except Exception as exc:
        logger.error("portfolio_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
