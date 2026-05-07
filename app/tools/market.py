"""
UF Stock Assistant — 市场数据工具
大盘指数、板块热点、龙虎榜等市场层面数据（带共享缓存）
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from app.core.cache import ensure_cache
from app.core.exceptions import DataProviderError
from app.core.logging import get_logger
from app.tools import eastmoney_api

logger = get_logger("app.tools.market")

_ak = None


def _get_ak() -> Any:
    """懒加载 akshare"""
    global _ak
    if _ak is None:
        import akshare as ak
        _ak = ak
    return _ak


# =============================================================================
# 大盘指数（从缓存读取）
# =============================================================================

def get_market_index() -> dict:
    """
    获取 5 大市场指数实时行情（东财直连 ~60ms）
    A股（上证指数）、沪市（上证50）、深市（深证成指）、港股（恒生指数）、美股（纳斯达克）
    """
    try:
        indices = eastmoney_api.get_indices()
        logger.info("market_index_fetched", indices=len(indices))
        return {"indices": indices, "timestamp": datetime.now().isoformat(), "source": "live"}

    except Exception as exc:
        logger.error("market_index_failed", error=str(exc))
        return {
            "indices": [
                {"symbol": "000001", "name": "上证指数", "market": "A股", "value": 0, "change": 0, "change_percent": 0},
                {"symbol": "000016", "name": "上证50", "market": "沪市", "value": 0, "change": 0, "change_percent": 0},
                {"symbol": "399001", "name": "深证成指", "market": "深市", "value": 0, "change": 0, "change_percent": 0},
                {"symbol": "HSI", "name": "恒生指数", "market": "港股", "value": 0, "change": 0, "change_percent": 0},
                {"symbol": "NDX", "name": "纳斯达克", "market": "美股", "value": 0, "change": 0, "change_percent": 0},
            ],
            "timestamp": datetime.now().isoformat(),
            "source": "demo",
        }


# =============================================================================
# 板块热点（从缓存读取）
# =============================================================================

def get_sector_hot() -> dict:
    """
    获取板块热点（行业/概念涨幅排行）
    优先从共享缓存读取
    """
    try:
        df = ensure_cache("market:sector")
        sectors = []

        if df is not None:
            for _, row in df.head(15).iterrows():
                name = str(row.get("板块名称", row.get("名称", "")))
                if not name or name == "未知":
                    continue
                sectors.append({
                    "name": name,
                    "change_percent": row.get("涨跌幅", 0),
                })
                if len(sectors) >= 10:
                    break
        else:
            logger.warning("sector_cache_miss_fallback")
            ak = _get_ak()
            # 尝试新 API
            try:
                df = ak.stock_board_industry_spot_em()
                for _, row in df.head(15).iterrows():
                    name = str(row.get("板块名称", row.get("名称", "")))
                    if not name or name == "未知":
                        continue
                    sectors.append({"name": name, "change_percent": row.get("涨跌幅", 0)})
                    if len(sectors) >= 10:
                        break
            except Exception as e:
                logger.warning("industry_spot_em_failed", error=str(e))
                try:
                    df = ak.stock_board_concept_spot_em()
                    for _, row in df.head(15).iterrows():
                        name = str(row.get("板块名称", row.get("名称", "")))
                        if not name or name == "未知":
                            continue
                        sectors.append({"name": name, "change_percent": row.get("涨跌幅", 0)})
                        if len(sectors) >= 10:
                            break
                except Exception as e2:
                    logger.warning("concept_spot_em_failed", error=str(e2))

        if not sectors:
            raise DataProviderError("无法获取板块数据")

        logger.info("sector_hot_fetched", sectors=len(sectors), cached=ensure_cache("market:sector") is not None)
        return {"sectors": sectors, "timestamp": datetime.now().isoformat(), "source": "live"}

    except Exception as exc:
        logger.error("sector_hot_failed", error=str(exc))
        return {
            "sectors": [
                {"name": "半导体", "change_percent": 3.45},
                {"name": "新能源", "change_percent": 2.87},
                {"name": "人工智能", "change_percent": 2.34},
                {"name": "医药生物", "change_percent": 1.89},
                {"name": "消费电子", "change_percent": 1.56},
                {"name": "汽车整车", "change_percent": -0.78},
                {"name": "银行", "change_percent": -0.45},
                {"name": "房地产", "change_percent": -1.23},
            ],
            "timestamp": datetime.now().isoformat(),
            "source": "demo",
        }


# =============================================================================
# 龙虎榜
# =============================================================================

def get_longhu_bang(date: str | None = None) -> str:
    """
    获取龙虎榜数据
    """
    try:
        records = eastmoney_api.get_longhu_bang(date)

        logger.info("longhu_bang_fetched", date=date, records=len(records))
        return json.dumps({"date": date, "data": records}, ensure_ascii=False, default=str)

    except Exception as exc:
        logger.error("longhu_bang_failed", date=date, error=str(exc))
        raise DataProviderError(f"获取龙虎榜失败: {exc}") from exc


# =============================================================================
# 市场概况（从缓存读取）
# =============================================================================

def get_market_overview() -> dict:
    """
    获取市场整体概况（东财直连）
    包含涨跌家数统计 + 5 大指数
    """
    try:
        # 涨跌统计
        stats = eastmoney_api.get_market_stats()

        # 大盘指数
        indices = eastmoney_api.get_indices()

        logger.info("market_overview_fetched")
        return {
            "timestamp": datetime.now().isoformat(),
            "source": "live",
            "summary": {
                "up": stats.get("up", 0),
                "down": stats.get("down", 0),
                "flat": stats.get("flat", 0),
                "limit_up": stats.get("limit_up", 0),
                "limit_down": stats.get("limit_down", 0),
            },
            "indices": indices,
        }

    except Exception as exc:
        logger.error("market_overview_failed", error=str(exc))
        return {
            "timestamp": datetime.now().isoformat(),
            "source": "demo",
            "summary": {"up": 0, "down": 0, "flat": 0, "limit_up": 0, "limit_down": 0},
            "indices": [],
        }


# =============================================================================
# 北向资金
# =============================================================================

def get_northbound_flow() -> dict:
    """
    获取北向资金流向（沪深港通）
    """
    try:
        ak = _get_ak()
        df = ak.stock_hsgt_hist_em(symbol="北向资金")

        if df.empty:
            return {"flow": [], "source": "live"}

        records = []
        for _, row in df.head(5).iterrows():
            records.append({
                "date": str(row.get("日期", "")),
                "net_inflow": row.get("净流入"),
                "cumulative": row.get("累计净流入"),
            })

        return {"flow": records, "source": "live"}

    except Exception as exc:
        logger.error("northbound_flow_failed", error=str(exc))
        return {"flow": [], "source": "demo", "error": str(exc)}
