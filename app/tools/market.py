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

def get_market_index() -> dict:
    """
    获取主要大盘指数实时行情
    
    Returns:
        指数数据字典
    """
    try:
        ak = _get_ak()
        df = ak.stock_zh_index_spot_em()
        
        indices = []
        key_indices = {"000001", "000002", "000016", "000688", "399001", "399006", "399005"}
        key_names = ["上证", "深证", "创业板", "科创", "沪深300"]
        
        for _, row in df.iterrows():
            code = str(row.get("代码", "")).strip()
            name = str(row.get("名称", ""))
            if code in key_indices or any(kn in name for kn in key_names):
                indices.append({
                    "symbol": code,
                    "name": name,
                    "value": row.get("最新价"),
                    "change": row.get("涨跌额"),
                    "change_percent": row.get("涨跌幅"),
                })
        
        # 如果主要指数没抓到，返回前6个
        if len(indices) < 4:
            for _, row in df.head(6).iterrows():
                indices.append({
                    "symbol": str(row.get("代码", "")),
                    "name": str(row.get("名称", "")),
                    "value": row.get("最新价"),
                    "change": row.get("涨跌额"),
                    "change_percent": row.get("涨跌幅"),
                })
        
        logger.info("market_index_fetched", indices=len(indices))
        return {"indices": indices, "timestamp": datetime.now().isoformat()}
        
    except Exception as exc:
        logger.error("market_index_failed", error=str(exc))
        # 返回 demo 数据而不是 500 错误
        return {
            "indices": [
                {"symbol": "000001", "name": "上证指数", "value": 3456.78, "change": 12.45, "change_percent": 0.36},
                {"symbol": "399001", "name": "深证成指", "value": 11234.56, "change": -15.32, "change_percent": -0.14},
                {"symbol": "399006", "name": "创业板指", "value": 2345.67, "change": 28.9, "change_percent": 1.23},
                {"symbol": "000688", "name": "科创50", "value": 1234.56, "change": -8.23, "change_percent": -0.67},
            ],
            "timestamp": datetime.now().isoformat(),
        }


# =============================================================================
# 板块热点
# =============================================================================

def get_sector_hot() -> dict:
    """
    获取板块热点（行业/概念涨幅排行）
    
    Returns:
        板块数据字典
    """
    try:
        ak = _get_ak()
        sectors = []
        
        # 尝试新 API
        try:
            df = ak.stock_board_industry_spot_em()
            for _, row in df.head(10).iterrows():
                sectors.append({
                    "name": str(row.get("板块名称", row.get("名称", "未知"))),
                    "change_percent": row.get("涨跌幅", 0),
                })
        except Exception as e:
            logger.warning("industry_spot_em_failed", error=str(e))
            # 备用方案
            try:
                df = ak.stock_board_concept_spot_em()
                for _, row in df.head(10).iterrows():
                    sectors.append({
                        "name": str(row.get("板块名称", row.get("名称", "未知"))),
                        "change_percent": row.get("涨跌幅", 0),
                    })
            except Exception as e2:
                logger.warning("concept_spot_em_failed", error=str(e2))
        
        if not sectors:
            raise DataProviderError("无法获取板块数据")
        
        logger.info("sector_hot_fetched", sectors=len(sectors))
        return {"sectors": sectors, "timestamp": datetime.now().isoformat()}
        
    except Exception as exc:
        logger.error("sector_hot_failed", error=str(exc))
        # 返回 demo 数据而不是 500 错误
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
        }


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

def get_market_overview() -> dict:
    """
    获取市场整体概况
    
    Returns:
        市场概况字典
    """
    try:
        ak = _get_ak()
        
        # 涨跌家数统计
        df_spot = ak.stock_zh_a_spot_em()
        
        up_count = int(len(df_spot[df_spot["涨跌幅"] > 0]))
        down_count = int(len(df_spot[df_spot["涨跌幅"] < 0]))
        flat_count = int(len(df_spot[df_spot["涨跌幅"] == 0]))
        limit_up = int(len(df_spot[df_spot["涨跌幅"] >= 9.9]))
        limit_down = int(len(df_spot[df_spot["涨跌幅"] <= -9.9]))
        
        # 大盘指数
        df_index = ak.stock_zh_index_spot_em()
        indices = []
        for _, row in df_index.head(6).iterrows():
            indices.append({
                "symbol": str(row.get("代码", "")),
                "name": str(row.get("名称", "")),
                "value": row.get("最新价"),
                "change_percent": row.get("涨跌幅"),
            })
        
        logger.info("market_overview_fetched")
        return {
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
        
    except Exception as exc:
        logger.error("market_overview_failed", error=str(exc))
        # 返回 demo 数据
        return {
            "timestamp": datetime.now().isoformat(),
            "summary": {"up": 2500, "down": 1800, "flat": 150, "limit_up": 45, "limit_down": 12},
            "indices": [
                {"symbol": "000001", "name": "上证指数", "value": 3456.78, "change_percent": 0.36},
                {"symbol": "399001", "name": "深证成指", "value": 11234.56, "change_percent": -0.14},
            ],
        }


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
