"""
UF Stock Assistant — 虚拟货币数据工具
基于 CCXT 的虚拟货币行情获取
"""

from __future__ import annotations

import json
from typing import Any

import ccxt

from app.core.exceptions import CryptoDataError
from app.core.logging import get_logger

logger = get_logger("app.tools.crypto_data")

# 默认使用 binance（不需要 API Key 即可获取公开行情）
_default_exchange: ccxt.Exchange | None = None


def _get_exchange(exchange_id: str = "binance") -> ccxt.Exchange:
    """获取交易所实例"""
    global _default_exchange
    if _default_exchange is None:
        exchange_class = getattr(ccxt, exchange_id)
        _default_exchange = exchange_class({
            "enableRateLimit": True,
            "timeout": 30000,
        })
    return _default_exchange


# =============================================================================
# 行情数据
# =============================================================================

def get_crypto_price(symbol: str, exchange: str = "binance") -> str:
    """
    获取虚拟货币价格
    
    Args:
        symbol: 交易对，如 "BTC/USDT"
        exchange: 交易所名称
        
    Returns:
        JSON 格式的价格数据
    """
    try:
        ex = _get_exchange(exchange)
        
        # 标准化交易对格式
        if "/" not in symbol:
            symbol = f"{symbol.upper()}/USDT"
        else:
            symbol = symbol.upper()
        
        ticker = ex.fetch_ticker(symbol)
        
        data = {
            "symbol": symbol,
            "exchange": exchange,
            "price": ticker.get("last"),
            "open": ticker.get("open"),
            "high": ticker.get("high"),
            "low": ticker.get("low"),
            "volume": ticker.get("baseVolume"),
            "quote_volume": ticker.get("quoteVolume"),
            "change": ticker.get("change"),
            "change_pct": ticker.get("percentage"),
            "bid": ticker.get("bid"),
            "ask": ticker.get("ask"),
            "timestamp": ticker.get("timestamp"),
        }
        
        logger.info("crypto_price_fetched", symbol=symbol, exchange=exchange, price=data["price"])
        return json.dumps(data, ensure_ascii=False, default=str)
        
    except Exception as exc:
        logger.error("crypto_price_failed", symbol=symbol, error=str(exc))
        raise CryptoDataError(f"获取虚拟货币价格失败: {exc}") from exc


def get_crypto_ticker(symbol: str, exchange: str = "binance") -> str:
    """
    获取虚拟货币行情摘要
    
    Args:
        symbol: 交易对，如 "BTC/USDT"
        exchange: 交易所名称
        
    Returns:
        JSON 格式的行情摘要
    """
    try:
        ex = _get_exchange(exchange)
        
        if "/" not in symbol:
            symbol = f"{symbol.upper()}/USDT"
        else:
            symbol = symbol.upper()
        
        ticker = ex.fetch_ticker(symbol)
        
        data = {
            "symbol": symbol,
            "exchange": exchange,
            "last_price": ticker.get("last"),
            "high_24h": ticker.get("high"),
            "low_24h": ticker.get("low"),
            "volume_24h": ticker.get("baseVolume"),
            "change_24h": ticker.get("change"),
            "change_pct_24h": ticker.get("percentage"),
            "bid": ticker.get("bid"),
            "ask": ticker.get("ask"),
            "spread": round(ticker.get("ask", 0) - ticker.get("bid", 0), 8) if ticker.get("ask") and ticker.get("bid") else None,
        }
        
        logger.info("crypto_ticker_fetched", symbol=symbol)
        return json.dumps(data, ensure_ascii=False, default=str)
        
    except Exception as exc:
        logger.error("crypto_ticker_failed", symbol=symbol, error=str(exc))
        raise CryptoDataError(f"获取行情摘要失败: {exc}") from exc


def list_top_cryptos(limit: int = 20, exchange: str = "binance") -> str:
    """
    获取市值排行前列的虚拟货币
    
    Args:
        limit: 返回数量
        exchange: 交易所名称
        
    Returns:
        JSON 格式的币种列表
    """
    try:
        ex = _get_exchange(exchange)
        
        # 获取所有交易对
        markets = ex.load_markets()
        
        # 筛选 USDT 交易对
        usdt_pairs = [s for s in markets.keys() if s.endswith("/USDT") and not any(x in s for x in ["UP/USDT", "DOWN/USDT", "BULL/USDT", "BEAR/USDT"])]
        
        # 获取行情
        tickers = ex.fetch_tickers(usdt_pairs[:limit * 2])
        
        # 按成交额排序
        sorted_tickers = sorted(
            tickers.items(),
            key=lambda x: x[1].get("quoteVolume", 0) or 0,
            reverse=True,
        )[:limit]
        
        results = []
        for symbol, ticker in sorted_tickers:
            results.append({
                "symbol": symbol,
                "price": ticker.get("last"),
                "change_pct_24h": ticker.get("percentage"),
                "volume_24h": ticker.get("baseVolume"),
                "quote_volume_24h": ticker.get("quoteVolume"),
            })
        
        logger.info("top_cryptos_fetched", count=len(results))
        return json.dumps({"cryptos": results}, ensure_ascii=False, default=str)
        
    except Exception as exc:
        logger.error("top_cryptos_failed", error=str(exc))
        raise CryptoDataError(f"获取币种排行失败: {exc}") from exc


def get_crypto_ohlcv(
    symbol: str,
    timeframe: str = "1d",
    limit: int = 100,
    exchange: str = "binance",
) -> str:
    """
    获取虚拟货币 K 线数据
    
    Args:
        symbol: 交易对
        timeframe: 周期，如 1m, 5m, 15m, 1h, 4h, 1d
        limit: 条数上限
        exchange: 交易所名称
        
    Returns:
        JSON 格式的 K 线数据
    """
    try:
        ex = _get_exchange(exchange)
        
        if "/" not in symbol:
            symbol = f"{symbol.upper()}/USDT"
        else:
            symbol = symbol.upper()
        
        ohlcv = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        
        records = []
        for candle in ohlcv:
            records.append({
                "timestamp": candle[0],
                "open": candle[1],
                "high": candle[2],
                "low": candle[3],
                "close": candle[4],
                "volume": candle[5],
            })
        
        logger.info("crypto_ohlcv_fetched", symbol=symbol, timeframe=timeframe, records=len(records))
        return json.dumps({"symbol": symbol, "timeframe": timeframe, "data": records}, ensure_ascii=False, default=str)
        
    except Exception as exc:
        logger.error("crypto_ohlcv_failed", symbol=symbol, error=str(exc))
        raise CryptoDataError(f"获取 K 线数据失败: {exc}") from exc
