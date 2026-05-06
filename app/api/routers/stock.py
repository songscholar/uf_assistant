"""
UF Stock Assistant — 股票数据接口
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

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


@router.get("/stock/search")
async def search(keyword: str = Query(..., description="搜索关键词"), limit: int = Query(10, ge=1, le=50)):
    """搜索股票"""
    try:
        return search_stocks(keyword, limit)
    except Exception as exc:
        logger.error("search_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/stock/{symbol}/info")
async def info(symbol: str):
    """获取股票基本信息"""
    try:
        return get_stock_info(symbol)
    except Exception as exc:
        logger.error("info_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/stock/{symbol}/realtime")
async def realtime(symbol: str):
    """获取股票实时行情"""
    try:
        return get_stock_realtime(symbol)
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
        return get_stock_history(symbol, period=period, start=start, end=end, limit=limit)
    except Exception as exc:
        logger.error("history_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/stock/{symbol}/financial")
async def financial(symbol: str):
    """获取股票财务数据"""
    try:
        return get_stock_financial(symbol)
    except Exception as exc:
        logger.error("financial_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/stock/{symbol}/capital-flow")
async def capital_flow(symbol: str):
    """获取个股资金流向"""
    try:
        return get_capital_flow(symbol)
    except Exception as exc:
        logger.error("capital_flow_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
