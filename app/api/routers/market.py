"""
UF Stock Assistant — 市场数据接口
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

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


@router.get("/market/overview")
async def overview():
    """获取市场概况"""
    return get_market_overview()


@router.get("/market/indices")
async def indices():
    """获取大盘指数"""
    return get_market_index()


@router.get("/market/sectors")
async def sectors():
    """获取板块热点"""
    return get_sector_hot()


@router.get("/market/longhu")
async def longhu(date: str | None = Query(None, description="日期 YYYY-MM-DD")):
    """获取龙虎榜"""
    try:
        return get_longhu_bang(date)
    except Exception as exc:
        logger.error("longhu_error", date=date, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/market/northbound")
async def northbound():
    """获取北向资金"""
    try:
        return get_northbound_flow()
    except Exception as exc:
        logger.error("northbound_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
