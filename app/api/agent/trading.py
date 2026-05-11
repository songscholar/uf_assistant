"""
UF Stock Assistant — Agent Gateway 交易端点
提供持仓/订单/组合的查询和下单接口

参考 QuantDinger 设计：
  - 默认 paper-only，写入 agent_paper_orders 表
  - T 类端点强制要求 Idempotency-Key
  - Kill Switch 一键取消所有未成交 paper orders
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.agent_auth import AgentAuthManager, AgentTokenRecord
from app.core.constants import AgentScope
from app.core.exceptions import TradingError, ValidationError
from app.core.logging import get_logger
from app.tools.trading import (
    cancel_order,
    get_orders,
    get_portfolio,
    get_positions,
    submit_order,
)

from . import require_scope, _inject_rate_limit

logger = get_logger("app.api.agent.trading")

router = APIRouter()


# =============================================================================
# 持仓
# =============================================================================

@router.get("/positions")
async def agent_get_positions(
    request: Request,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取所有持仓"""
    _inject_rate_limit(request, record)
    try:
        return get_positions()
    except Exception as exc:
        logger.error("agent_positions_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/position/{symbol}")
async def agent_get_position(
    request: Request,
    symbol: str,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取指定持仓（暂不支持，请使用 /positions 端点）"""
    _inject_rate_limit(request, record)
    raise HTTPException(status_code=501, detail="单持仓查询暂不支持，请使用 /positions 端点")


# =============================================================================
# 订单
# =============================================================================

@router.get("/orders")
async def agent_get_orders(
    request: Request,
    status: str | None = None,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取订单列表"""
    _inject_rate_limit(request, record)
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
    request: Request,
    body: PlaceOrderRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    record: AgentTokenRecord = Depends(require_scope(AgentScope.TRADE)),
):
    """
    下单接口

    安全机制：
    1. 需要 T (Trade) scope
    2. Token 必须 paper_only=false 且品种在白名单内
    3. 服务端 AGENT_LIVE_TRADING_ENABLED=true
    4. W/B/T 类端点建议提供 Idempotency-Key

    默认所有订单都是模拟订单（paper），写入 agent_paper_orders 表。
    实盘需显式开启双重开关。
    """
    _inject_rate_limit(request, record)

    # 品种白名单检查
    if not AgentAuthManager.instrument_allowed(record, body.symbol):
        raise ValidationError(
            f"Instrument not allowed for this token: {body.symbol}",
            details={"code": "INSTRUMENT_NOT_ALLOWED", "instrument": body.symbol},
        )

    # 幂等性检查
    with AgentAuthManager.with_idempotency("place_order", idempotency_key) as existing:
        if existing:
            return {"duplicate": True, "previous": existing.get("result")}

    try:
        # 双重安全检查
        AgentAuthManager.check_trade_permission(record)

        # 实盘路径（如启用）
        result = submit_order(
            symbol=body.symbol,
            side=body.side,
            quantity=body.quantity,
            price=body.price,
            order_type=body.order_type,
        )

        logger.info(
            "agent_order_placed",
            token_name=record.name,
            symbol=body.symbol,
            side=body.side,
            quantity=body.quantity,
        )

        return result
    except ValidationError:
        raise
    except HTTPException:
        raise
    except TradingError as exc:
        raise HTTPException(status_code=400, detail=exc.message)
    except Exception as exc:
        logger.error("agent_place_order_error", error=str(exc))
        # Paper-only fallback: 记录到 agent_paper_orders 表
        note = f"live submit failed: {str(exc)[:200]}" if get_settings().agent.live_trading_enabled else "paper-only by default"
        paper_result = AgentAuthManager.record_paper_order(
            token_hash=record.token_hash,
            symbol=body.symbol,
            side=body.side,
            qty=body.quantity,
            order_type=body.order_type,
            limit_price=body.price,
            fill_price=None,
            status="rejected",
            note=note,
        )
        return paper_result


@router.delete("/orders/{order_id}")
async def agent_cancel_order(
    request: Request,
    order_id: str,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.TRADE)),
):
    """取消订单（同样需要交易权限）"""
    _inject_rate_limit(request, record)
    try:
        AgentAuthManager.check_trade_permission(record)

        result = cancel_order(order_id)
        logger.info("agent_order_cancelled", token_name=record.name, order_id=order_id)
        return result
    except ValidationError:
        raise
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
    request: Request,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取投资组合分析"""
    _inject_rate_limit(request, record)
    try:
        return get_portfolio()
    except Exception as exc:
        logger.error("agent_portfolio_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# Kill Switch
# =============================================================================

@router.post("/kill-switch")
async def agent_kill_switch(
    request: Request,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.TRADE)),
):
    """
    取消当前 Token 的所有未成交 paper orders

    注意：此端点只影响 agent paper orders，不影响实盘交易所订单。
    """
    _inject_rate_limit(request, record)
    affected = AgentAuthManager.kill_switch_paper_orders(record.token_hash)
    return {"cancelled_open_paper_orders": affected}


# =============================================================================
# Paper Orders 查询
# =============================================================================

@router.get("/paper-orders")
async def agent_list_paper_orders(
    request: Request,
    limit: int = 100,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """列出当前 Token 的模拟交易订单"""
    _inject_rate_limit(request, record)
    return {"orders": AgentAuthManager.list_paper_orders(record.token_hash, limit=limit)}
