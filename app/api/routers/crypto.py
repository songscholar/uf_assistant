"""
UF Stock Assistant — 虚拟货币接口
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.logging import get_logger
from app.tools.crypto_data import get_crypto_ohlcv, get_crypto_price, get_crypto_ticker, list_top_cryptos

logger = get_logger("app.api.crypto")

router = APIRouter()


@router.get("/crypto/price")
async def price(
    symbol: str = Query(..., description="交易对，如 BTC/USDT 或 BTC"),
    exchange: str = Query("binance", description="交易所"),
):
    """获取虚拟货币价格"""
    try:
        return get_crypto_price(symbol, exchange)
    except Exception as exc:
        logger.error("crypto_price_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/crypto/ticker")
async def ticker(
    symbol: str = Query(..., description="交易对"),
    exchange: str = Query("binance", description="交易所"),
):
    """获取行情摘要"""
    try:
        return get_crypto_ticker(symbol, exchange)
    except Exception as exc:
        logger.error("crypto_ticker_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/crypto/top")
async def top(
    limit: int = Query(20, ge=1, le=100),
    exchange: str = Query("binance", description="交易所"),
):
    """获取市值排行"""
    try:
        return list_top_cryptos(limit, exchange)
    except Exception as exc:
        logger.error("crypto_top_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/crypto/ohlcv")
async def ohlcv(
    symbol: str = Query(..., description="交易对"),
    timeframe: str = Query("1d", description="周期: 1m/5m/15m/1h/4h/1d"),
    limit: int = Query(100, ge=1, le=500),
    exchange: str = Query("binance", description="交易所"),
):
    """获取 K 线数据"""
    try:
        return get_crypto_ohlcv(symbol, timeframe, limit, exchange)
    except Exception as exc:
        logger.error("crypto_ohlcv_error", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
