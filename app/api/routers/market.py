"""
UF Stock Assistant — 市场数据接口
使用线程池执行同步 AKShare 调用，避免阻塞事件循环
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from app.core.logging import get_logger
from app.tools.market import (
    get_longhu_bang,
    get_market_index,
    get_market_overview,
    get_northbound_flow,
    get_sector_hot,
)

logger = get_logger("app.api.market")

router = APIRouter()

# AKShare 请求超时（秒）
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


@router.get("/market/overview")
async def overview():
    """获取市场概况"""
    try:
        return await _call_with_timeout(get_market_overview)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("overview_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/market/indices")
async def indices():
    """获取大盘指数"""
    try:
        return await _call_with_timeout(get_market_index)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("indices_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/market/sectors")
async def sectors():
    """获取板块热点"""
    try:
        return await _call_with_timeout(get_sector_hot)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("sectors_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/market/longhu")
async def longhu(date: str | None = Query(None, description="日期 YYYY-MM-DD")):
    """获取龙虎榜"""
    try:
        return await _call_with_timeout(get_longhu_bang, date)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("longhu_error", date=date, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/market/northbound")
async def northbound():
    """获取北向资金"""
    try:
        return await _call_with_timeout(get_northbound_flow)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("northbound_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
