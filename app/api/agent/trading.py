"""
UF Stock Assistant — Agent Gateway 交易端点
提供持仓/订单/组合的查询和下单接口
默认 paper-only，实盘需双重安全开关
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.agent_auth import AgentAuthManager, AgentTokenRecord
from app.core.constants import AgentScope
from app.core.exceptions import TradingError
from app.core.logging import get_logger
from app.tools.trading import (
    cancel_order,
    get_orders,
    get_portfolio,
    get_position,
    get_positions,
    submit_order,
)

from . import require_scope

logger = get_logger("app.api.agent.trading")

router = APIRouter()


# =============================================================================
# 持仓
# =============================================================================

@router.get("/positions")
async def agent_get_positions(
    _record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取所有持仓"""
    try:
        return get_positions()
    except Exception as exc:
        logger.error("agent_positions_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/position/{symbol}")
async def agent_get_position(
    symbol: str,
    _record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取指定持仓"""
    try:
        return get_position(symbol)
    except Exception as exc:
        logger.error("agent_position_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# 订单
# =============================================================================

@router.get("/orders")
async def agent_get_orders(
    status: str | None = None,
    _record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取订单列表"""
    try:
        return get_orders(status=status)
    except Exception as exc:
        logger.error("agent_orders_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


class PlaceOrderRequest(BaseModel):
    """下单请求"""
    symbol: str = Field(..., description="股票代码")
    side: str = Field(..., description="buy 或 sell")
    quantity: float = Field(..., gt=0, description="数量")
    price: float | None = Field(None, description="价格（限价单）")
    order_type: str = Field("market", description="market 或 limit")


@router.post("/orders")
async def agent_place_order(
    request: PlaceOrderRequest,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.TRADE)),
):
    """
    下单接口
    
    安全机制：
    1. 需要 T (Trade) scope
    2. Token 必须 paper_only=false
    3. 服务端 AGENT_LIVE_TRADING_ENABLED=true
    
    默认所有订单都是模拟订单（paper），实盘需显式开启双重开关。
    """
    try:
        # 双重安全检查
        AgentAuthManager.check_trade_permission(record)
        
        result = submit_order(
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            price=request.price,
            order_type=request.order_type,
        )
        
        logger.info(
            "agent_order_placed",
            token_name=record.name,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
        )
        
        return result
    except HTTPException:
        raise
    except TradingError as exc:
        raise HTTPException(status_code=400, detail=exc.message)
    except Exception as exc:
        logger.error("agent_place_order_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/orders/{order_id}")
async def agent_cancel_order(
    order_id: str,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.TRADE)),
):
    """取消订单（同样需要交易权限）"""
    try:
        AgentAuthManager.check_trade_permission(record)
        
        result = cancel_order(order_id)
        logger.info("agent_order_cancelled", token_name=record.name, order_id=order_id)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("agent_cancel_order_error", order_id=order_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# 投资组合
# =============================================================================

@router.get("/portfolio")
async def agent_get_portfolio(
    _record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取投资组合分析"""
    try:
        return get_portfolio()
    except Exception as exc:
        logger.error("agent_portfolio_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
