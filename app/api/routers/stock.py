"""
UF Stock Assistant — 股票数据接口
使用线程池执行同步 AKShare 调用，避免阻塞事件循环
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from app.core.logging import get_logger
from app.tools.stock_data import (
    get_capital_flow,
    get_stock_financial,
    get_stock_history,
    get_stock_info,
    get_stock_realtime,
    search_stocks,
)

logger = get_logger("app.api.stock")

router = APIRouter()

# AKShare 请求超时（秒）— 全量数据拉取较慢，设为 20 秒
AKSHARE_TIMEOUT = 20.0


async def _call_with_timeout(func, *args, **kwargs):
    """在线程池中执行同步函数，并设置超时"""
    try:
        return await asyncio.wait_for(
            run_in_threadpool(func, *args, **kwargs),
            timeout=AKSHARE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("akshare_request_timeout", func=func.__name__)
        raise HTTPException(status_code=504, detail="数据服务响应超时，请稍后重试")


@router.get("/stock/search")
async def search(keyword: str = Query(..., description="搜索关键词"), limit: int = Query(10, ge=1, le=50)):
    """搜索股票"""
    try:
        return await _call_with_timeout(search_stocks, keyword, limit)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("search_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/stock/{symbol}/info")
async def info(symbol: str):
    """获取股票基本信息"""
    try:
        return await _call_with_timeout(get_stock_info, symbol)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("info_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/stock/{symbol}/realtime")
async def realtime(symbol: str):
    """获取股票实时行情"""
    try:
        return await _call_with_timeout(get_stock_realtime, symbol)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("realtime_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/stock/{symbol}/history")
async def history(
    symbol: str,
    period: str = Query("daily", description="周期: daily/weekly/monthly"),
    start: str | None = Query(None, description="开始日期 YYYY-MM-DD"),
    end: str | None = Query(None, description="结束日期 YYYY-MM-DD"),
    limit: int = Query(100, ge=1, le=500),
):
    """获取股票历史 K 线"""
    try:
        return await _call_with_timeout(
            get_stock_history, symbol, period=period, start=start, end=end, limit=limit
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("history_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/stock/{symbol}/financial")
async def financial(symbol: str):
    """获取股票财务数据"""
    try:
        return await _call_with_timeout(get_stock_financial, symbol)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("financial_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/stock/{symbol}/capital-flow")
async def capital_flow(symbol: str):
    """获取个股资金流向"""
    try:
        return await _call_with_timeout(get_capital_flow, symbol)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("capital_flow_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
