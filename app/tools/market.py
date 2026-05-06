"""
UF Stock Assistant — 市场数据工具
大盘指数、板块热点、龙虎榜等市场层面数据
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from app.core.exceptions import DataProviderError
from app.core.logging import get_logger

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
# 大盘指数
# =============================================================================

def get_market_index() -> str:
    """
    获取主要大盘指数实时行情
    
    Returns:
        JSON 格式的指数数据
    """
    try:
        ak = _get_ak()
        df = ak.stock_zh_index_spot()
        
        indices = []
        key_indices = ["000001", "000002", "000016", "000688", "399001", "399006", "399006"]
        
        for _, row in df.iterrows():
            code = str(row.get("代码", ""))
            # 只保留主要指数
            if code in key_indices or any(name in str(row.get("名称", "")) for name in ["上证", "深证", "创业板", "科创", "沪深300"]):
                indices.append({
                    "symbol": code,
                    "name": row.get("名称"),
                    "price": row.get("最新价"),
                    "change": row.get("涨跌额"),
                    "change_pct": row.get("涨跌幅"),
                    "high": row.get("最高"),
                    "low": row.get("最低"),
                    "volume": row.get("成交量"),
                    "amount": row.get("成交额"),
                })
        
        logger.info("market_index_fetched", indices=len(indices))
        return json.dumps({"indices": indices, "timestamp": datetime.now().isoformat()}, ensure_ascii=False, default=str)
        
    except Exception as exc:
        logger.error("market_index_failed", error=str(exc))
        raise DataProviderError(f"获取大盘指数失败: {exc}") from exc


# =============================================================================
# 板块热点
# =============================================================================

def get_sector_hot() -> str:
    """
    获取板块热点（行业/概念涨幅排行）
    
    Returns:
        JSON 格式的板块数据
    """
    try:
        ak = _get_ak()
        
        # 行业板块涨幅排行
        df_industry = ak.stock_sector_spot(symbol="行业板块")
        industries = []
        for _, row in df_industry.head(10).iterrows():
            industries.append({
                "name": row.get("板块"),
                "change_pct": row.get("涨跌幅"),
                "total_volume": row.get("总成交量"),
                "leading_stock": row.get("领涨股"),
            })
        
        # 概念板块涨幅排行
        df_concept = ak.stock_sector_spot(symbol="概念板块")
        concepts = []
        for _, row in df_concept.head(10).iterrows():
            concepts.append({
                "name": row.get("板块"),
                "change_pct": row.get("涨跌幅"),
                "total_volume": row.get("总成交量"),
                "leading_stock": row.get("领涨股"),
            })
        
        logger.info("sector_hot_fetched", industries=len(industries), concepts=len(concepts))
        return json.dumps({
            "industries": industries,
            "concepts": concepts,
            "timestamp": datetime.now().isoformat(),
        }, ensure_ascii=False, default=str)
        
    except Exception as exc:
        logger.error("sector_hot_failed", error=str(exc))
        raise DataProviderError(f"获取板块热点失败: {exc}") from exc


# =============================================================================
# 龙虎榜
# =============================================================================

def get_longhu_bang(date: str | None = None) -> str:
    """
    获取龙虎榜数据
    
    Args:
        date: 日期 YYYY-MM-DD，默认最近交易日
        
    Returns:
        JSON 格式的龙虎榜数据
    """
    try:
        ak = _get_ak()
        
        if date:
            date_fmt = date.replace("-", "")
        else:
            date_fmt = None
        
        # 龙虎榜详情
        df = ak.stock_lhb_detail_daily_sina(start_date=date_fmt, end_date=date_fmt)
        
        if df.empty:
            return json.dumps({"date": date, "data": []}, ensure_ascii=False)
        
        records = []
        for _, row in df.head(20).iterrows():
            records.append({
                "symbol": row.get("代码"),
                "name": row.get("名称"),
                "close_price": row.get("收盘价"),
                "change_pct": row.get("涨跌幅"),
                "volume": row.get("成交量"),
                "amount": row.get("成交额"),
                "reason": row.get("上榜原因"),
            })
        
        logger.info("longhu_bang_fetched", date=date, records=len(records))
        return json.dumps({"date": date, "data": records}, ensure_ascii=False, default=str)
        
    except Exception as exc:
        logger.error("longhu_bang_failed", date=date, error=str(exc))
        raise DataProviderError(f"获取龙虎榜失败: {exc}") from exc


# =============================================================================
# 市场概况
# =============================================================================

def get_market_overview() -> str:
    """
    获取市场整体概况
    
    Returns:
        JSON 格式的市场概况
    """
    try:
        ak = _get_ak()
        
        # 涨跌家数统计
        df_spot = ak.stock_zh_a_spot_em()
        
        up_count = len(df_spot[df_spot["涨跌幅"] > 0])
        down_count = len(df_spot[df_spot["涨跌幅"] < 0])
        flat_count = len(df_spot[df_spot["涨跌幅"] == 0])
        limit_up = len(df_spot[df_spot["涨跌幅"] >= 9.9])
        limit_down = len(df_spot[df_spot["涨跌幅"] <= -9.9])
        
        # 大盘指数
        df_index = ak.stock_zh_index_spot()
        indices = []
        for _, row in df_index.head(6).iterrows():
            indices.append({
                "symbol": row.get("代码"),
                "name": row.get("名称"),
                "price": row.get("最新价"),
                "change_pct": row.get("涨跌幅"),
            })
        
        overview = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "up": up_count,
                "down": down_count,
                "flat": flat_count,
                "limit_up": limit_up,
                "limit_down": limit_down,
            },
            "indices": indices,
        }
        
        logger.info("market_overview_fetched")
        return json.dumps(overview, ensure_ascii=False, default=str)
        
    except Exception as exc:
        logger.error("market_overview_failed", error=str(exc))
        raise DataProviderError(f"获取市场概况失败: {exc}") from exc


# =============================================================================
# 北向资金
# =============================================================================

def get_northbound_flow() -> str:
    """
    获取北向资金流向（沪深港通）
    
    Returns:
        JSON 格式的北向资金数据
    """
    try:
        ak = _get_ak()
        df = ak.stock_hsgt_hist_em(symbol="北向资金")
        
        if df.empty:
            return json.dumps({"flow": []}, ensure_ascii=False)
        
        records = []
        for _, row in df.head(5).iterrows():
            records.append({
                "date": row.get("日期"),
                "net_inflow": row.get("净流入"),
                "cumulative": row.get("累计净流入"),
            })
        
        return json.dumps({"flow": records}, ensure_ascii=False, default=str)
        
    except Exception as exc:
        logger.error("northbound_flow_failed", error=str(exc))
        raise DataProviderError(f"获取北向资金失败: {exc}") from exc
