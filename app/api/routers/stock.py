"""
UF Stock Assistant — 股票数据接口
使用线程池执行同步 AKShare 调用，避免阻塞事件循环
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from app.auth.dependencies import get_current_user
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

router = APIRouter(dependencies=[Depends(get_current_user)])

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


# ── 自选股票 ────────────────────────────────────────────────────────────────

from pydantic import BaseModel

from app.data.watchlist_models import add_watchlist_item, get_watchlist, remove_watchlist_item


class WatchlistAddRequest(BaseModel):
    symbol: str
    name: str | None = None


@router.get("/stock/watchlist")
async def watchlist_list(current_user: dict = Depends(get_current_user)):
    """获取用户自选股票列表（含实时行情、添加价格、自添加涨跌幅）"""
    try:
        user_id = current_user["user_id"]
        items = get_watchlist(user_id)
        if not items:
            return {"items": []}

        # 批量获取实时行情
        results = []
        for item in items:
            try:
                rt = get_stock_realtime(item["symbol"])
                if isinstance(rt, dict):
                    price = rt.get("price")
                    prev_close = rt.get("prev_close")
                    # 计算涨跌额
                    change = rt.get("change")
                    if change is None and price is not None and prev_close is not None:
                        change = round(price - prev_close, 2)
                    # 计算自添加以来涨跌幅
                    added_price = item.get("added_price")
                    since_added_pct = None
                    if added_price and price is not None and added_price > 0:
                        since_added_pct = round((price - added_price) / added_price * 100, 2)
                    results.append({
                        "symbol": item["symbol"],
                        "name": rt.get("name") or item["name"] or item["symbol"],
                        "price": price,
                        "change": change,
                        "change_pct": rt.get("change_pct"),
                        "volume": rt.get("volume"),
                        "amount": rt.get("amount"),
                        "high": rt.get("high"),
                        "low": rt.get("low"),
                        "open": rt.get("open"),
                        "prev_close": prev_close,
                        "added_at": item.get("created_at"),
                        "added_price": added_price,
                        "since_added_pct": since_added_pct,
                    })
                else:
                    results.append({
                        "symbol": item["symbol"],
                        "name": item["name"],
                        "error": "数据获取失败",
                        "added_at": item.get("created_at"),
                        "added_price": item.get("added_price"),
                    })
            except Exception as exc:
                logger.warning("watchlist_realtime_failed", symbol=item["symbol"], error=str(exc))
                results.append({
                    "symbol": item["symbol"],
                    "name": item["name"],
                    "error": "数据获取失败",
                    "added_at": item.get("created_at"),
                    "added_price": item.get("added_price"),
                })

        return {"items": results}
    except Exception as exc:
        logger.error("watchlist_list_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/stock/watchlist")
async def watchlist_add(
    request: WatchlistAddRequest,
    current_user: dict = Depends(get_current_user),
):
    """添加自选股票"""
    try:
        user_id = current_user["user_id"]
        # 如果 name 为空，尝试从缓存查找
        name = request.name
        if not name:
            try:
                from app.core.cache import get_cached_df
                df = get_cached_df("market:spot")
                if df is not None and not df.empty:
                    row = df[df["代码"] == request.symbol]
                    if not row.empty:
                        name = row.iloc[0]["名称"]
            except Exception:
                pass
        # 获取添加时的实时价格快照
        added_price = None
        try:
            rt = get_stock_realtime(request.symbol)
            if isinstance(rt, dict):
                added_price = rt.get("price")
        except Exception as exc:
            logger.warning("watchlist_add_price_failed", symbol=request.symbol, error=str(exc))

        result = add_watchlist_item(user_id, request.symbol, name, added_price)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("watchlist_add_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/stock/watchlist/{symbol}")
async def watchlist_delete(symbol: str, current_user: dict = Depends(get_current_user)):
    """删除自选股票"""
    try:
        user_id = current_user["user_id"]
        success = remove_watchlist_item(user_id, symbol)
        if not success:
            raise HTTPException(status_code=404, detail="该股票不在自选列表中")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("watchlist_delete_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
