"""
UF Stock Assistant — 虚拟货币数据工具
基于 CCXT 的虚拟货币行情获取（默认 Gate.io，国内可访问）
"""

from __future__ import annotations

from typing import Any

import ccxt

from app.core.exceptions import CryptoDataError
from app.core.logging import get_logger

logger = get_logger("app.tools.crypto_data")

# 默认使用 gate（国内可访问，无需 API Key）
_default_exchange: ccxt.Exchange | None = None
_default_exchange_id: str = "gate"


def _get_exchange(exchange_id: str = "gate") -> ccxt.Exchange:
    """获取交易所实例（单例，避免重复加载市场数据）"""
    global _default_exchange, _default_exchange_id
    if _default_exchange is None or _default_exchange_id != exchange_id:
        exchange_class = getattr(ccxt, exchange_id)
        _default_exchange = exchange_class({
            "enableRateLimit": True,
            "timeout": 15000,
        })
        _default_exchange_id = exchange_id
    return _default_exchange


def _normalize_symbol(symbol: str) -> str:
    """标准化交易对格式"""
    if "/" not in symbol:
        return f"{symbol.upper()}/USDT"
    return symbol.upper()


# =============================================================================
# 行情数据
# =============================================================================

def get_crypto_price(symbol: str, exchange: str = "gate") -> dict:
    """获取虚拟货币价格"""
    try:
        ex = _get_exchange(exchange)
        symbol = _normalize_symbol(symbol)
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
            "source": "live",
        }
        logger.info("crypto_price_fetched", symbol=symbol, price=data["price"])
        return data

    except Exception as exc:
        logger.error("crypto_price_failed", symbol=symbol, error=str(exc))
        raise CryptoDataError(f"获取虚拟货币价格失败: {exc}") from exc


def get_crypto_ticker(symbol: str, exchange: str = "gate") -> dict:
    """获取虚拟货币行情摘要"""
    try:
        ex = _get_exchange(exchange)
        symbol = _normalize_symbol(symbol)
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
            "source": "live",
        }
        logger.info("crypto_ticker_fetched", symbol=symbol)
        return data

    except Exception as exc:
        logger.error("crypto_ticker_failed", symbol=symbol, error=str(exc))
        raise CryptoDataError(f"获取行情摘要失败: {exc}") from exc


# 主流币种列表（保证出现在排行中）
_MAJOR_COINS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
    "DOGE/USDT", "ADA/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT",
    "MATIC/USDT", "UNI/USDT", "LTC/USDT", "ATOM/USDT", "FIL/USDT",
    "NEAR/USDT", "APT/USDT", "ARB/USDT", "OP/USDT", "SUI/USDT",
    "PEPE/USDT", "SHIB/USDT", "TRX/USDT", "TON/USDT", "WBTC/USDT",
]


def list_top_cryptos(limit: int = 20, exchange: str = "gate") -> dict:
    """获取市值排行前列的虚拟货币（主流币 + 按成交额排序）"""
    try:
        ex = _get_exchange(exchange)
        markets = ex.load_markets()

        usdt_pairs = [
            s for s in markets
            if s.endswith("/USDT")
            and not any(x in s for x in ["UP", "DOWN", "BULL", "BEAR", "3L", "3S", "5L", "5S"])
        ]

        fetch_set = set(_MAJOR_COINS) | set(usdt_pairs[:50])
        fetch_list = [s for s in fetch_set if s in markets]

        tickers = ex.fetch_tickers(fetch_list)

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
        return {"cryptos": results, "source": "live"}

    except Exception as exc:
        logger.error("top_cryptos_failed", error=str(exc))
        return {
            "cryptos": [
                {"symbol": "BTC/USDT", "price": 0, "change_pct_24h": 0, "volume_24h": 0, "quote_volume_24h": 0},
                {"symbol": "ETH/USDT", "price": 0, "change_pct_24h": 0, "volume_24h": 0, "quote_volume_24h": 0},
                {"symbol": "BNB/USDT", "price": 0, "change_pct_24h": 0, "volume_24h": 0, "quote_volume_24h": 0},
                {"symbol": "SOL/USDT", "price": 0, "change_pct_24h": 0, "volume_24h": 0, "quote_volume_24h": 0},
                {"symbol": "XRP/USDT", "price": 0, "change_pct_24h": 0, "volume_24h": 0, "quote_volume_24h": 0},
            ],
            "source": "demo",
        }


def get_crypto_ohlcv(
    symbol: str,
    timeframe: str = "1d",
    limit: int = 100,
    exchange: str = "gate",
) -> dict:
    """获取虚拟货币 K 线数据"""
    try:
        ex = _get_exchange(exchange)
        symbol = _normalize_symbol(symbol)
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

        logger.info("crypto_ohlcv_fetched", symbol=symbol, records=len(records))
        return {"symbol": symbol, "timeframe": timeframe, "data": records, "source": "live"}

    except Exception as exc:
        logger.error("crypto_ohlcv_failed", symbol=symbol, error=str(exc))
        raise CryptoDataError(f"获取 K 线数据失败: {exc}") from exc
