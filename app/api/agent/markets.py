"""
UF Stock Assistant — Agent Gateway 市场数据端点
提供股票/板块/指数/加密货币的查询接口
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.core.agent_auth import AgentTokenRecord
from app.core.constants import AgentScope
from app.core.logging import get_logger
from app.tools.crypto_data import get_crypto_price, get_crypto_ticker
from app.tools.market import get_market_index, get_market_overview, get_sector_hot
from app.tools.stock_data import get_stock_history, get_stock_realtime, search_stocks

from . import require_scope

logger = get_logger("app.api.agent.markets")

router = APIRouter()

AKSHARE_TIMEOUT = 20.0


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
    q: str = Query(..., description="搜索关键词"),
    limit: int = Query(10, ge=1, le=50),
    _record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """搜索股票"""
    try:
        return await _call_with_timeout(search_stocks, q, limit)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("agent_search_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/stocks/{symbol}/realtime")
async def agent_stock_realtime(
    symbol: str,
    _record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取个股实时行情"""
    try:
        return await _call_with_timeout(get_stock_realtime, symbol)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("agent_realtime_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/stocks/{symbol}/history")
async def agent_stock_history(
    symbol: str,
    period: str = Query("daily", description="周期: daily/weekly/monthly"),
    start: str | None = Query(None, description="开始日期 YYYY-MM-DD"),
    end: str | None = Query(None, description="结束日期 YYYY-MM-DD"),
    limit: int = Query(100, ge=1, le=500),
    _record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取股票历史 K 线"""
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
    _record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取市场概况"""
    try:
        return await _call_with_timeout(get_market_overview)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("agent_overview_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/indices")
async def agent_market_indices(
    _record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取大盘指数"""
    try:
        return await _call_with_timeout(get_market_index)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("agent_indices_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/sectors")
async def agent_market_sectors(
    _record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取板块热点"""
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
    symbol: str = Query(..., description="交易对，如 BTC 或 BTC/USDT"),
    _record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取加密货币价格"""
    try:
        return get_crypto_price(symbol)
    except Exception as exc:
        logger.error("agent_crypto_price_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/crypto/ticker")
async def agent_crypto_ticker(
    symbol: str = Query(..., description="交易对"),
    _record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取加密货币行情摘要"""
    try:
        return get_crypto_ticker(symbol)
    except Exception as exc:
        logger.error("agent_crypto_ticker_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
