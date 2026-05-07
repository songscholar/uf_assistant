"""
UF Stock Assistant — Agent Gateway 市场数据端点
提供股票/板块/指数/加密货币的查询接口
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.core.agent_auth import AgentAuthManager, AgentTokenRecord
from app.core.constants import AgentScope
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.tools.crypto_data import get_crypto_price, get_crypto_ticker
from app.tools.market import get_market_index, get_market_overview, get_sector_hot
from app.tools.stock_data import get_stock_history, get_stock_realtime, search_stocks

from . import require_scope, _inject_rate_limit

logger = get_logger("app.api.agent.markets")

router = APIRouter()

AKSHARE_TIMEOUT = 20.0


def _check_instrument(record: AgentTokenRecord, symbol: str) -> None:
    """检查品种白名单"""
    if not AgentAuthManager.instrument_allowed(record, symbol):
        raise ValidationError(
            f"Instrument not allowed for this token: {symbol}",
            details={"code": "INSTRUMENT_NOT_ALLOWED", "instrument": symbol},
        )


async def _call_with_timeout(func, *args, **kwargs):
    """在线程池中执行同步函数，并设置超时"""
    try:
        return await asyncio.wait_for(
            run_in_threadpool(func, *args, **kwargs),
            timeout=AKSHARE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="数据服务响应超时，请稍后重试")


# =============================================================================
# 股票数据
# =============================================================================

@router.get("/stocks/search")
async def agent_search_stocks(
    request: Request,
    q: str = Query(..., description="搜索关键词"),
    limit: int = Query(10, ge=1, le=50),
    record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """搜索股票"""
    _inject_rate_limit(request, record)
    try:
        return await _call_with_timeout(search_stocks, q, limit)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("agent_search_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/stocks/{symbol}/realtime")
async def agent_stock_realtime(
    request: Request,
    symbol: str,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取个股实时行情"""
    _inject_rate_limit(request, record)
    _check_instrument(record, symbol)
    try:
        return await _call_with_timeout(get_stock_realtime, symbol)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("agent_realtime_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/stocks/{symbol}/history")
async def agent_stock_history(
    request: Request,
    symbol: str,
    period: str = Query("daily", description="周期: daily/weekly/monthly"),
    start: str | None = Query(None, description="开始日期 YYYY-MM-DD"),
    end: str | None = Query(None, description="结束日期 YYYY-MM-DD"),
    limit: int = Query(100, ge=1, le=500),
    record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取股票历史 K 线"""
    _inject_rate_limit(request, record)
    _check_instrument(record, symbol)
    try:
        return await _call_with_timeout(
            get_stock_history, symbol, period=period, start=start, end=end, limit=limit
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("agent_history_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# 市场数据
# =============================================================================

@router.get("/overview")
async def agent_market_overview(
    request: Request,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取市场概况"""
    _inject_rate_limit(request, record)
    try:
        return await _call_with_timeout(get_market_overview)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("agent_overview_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/indices")
async def agent_market_indices(
    request: Request,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取大盘指数"""
    _inject_rate_limit(request, record)
    try:
        return await _call_with_timeout(get_market_index)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("agent_indices_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/sectors")
async def agent_market_sectors(
    request: Request,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取板块热点"""
    _inject_rate_limit(request, record)
    try:
        return await _call_with_timeout(get_sector_hot)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("agent_sectors_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# 加密货币
# =============================================================================

@router.get("/crypto/price")
async def agent_crypto_price(
    request: Request,
    symbol: str = Query(..., description="交易对，如 BTC 或 BTC/USDT"),
    record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取加密货币价格"""
    _inject_rate_limit(request, record)
    _check_instrument(record, symbol)
    try:
        return get_crypto_price(symbol)
    except Exception as exc:
        logger.error("agent_crypto_price_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/crypto/ticker")
async def agent_crypto_ticker(
    request: Request,
    symbol: str = Query(..., description="交易对"),
    record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取加密货币行情摘要"""
    _inject_rate_limit(request, record)
    _check_instrument(record, symbol)
    try:
        return get_crypto_ticker(symbol)
    except Exception as exc:
        logger.error("agent_crypto_ticker_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
