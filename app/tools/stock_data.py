"""
UF Stock Assistant — 股票数据工具
基于 AKShare 的 A 股数据获取封装（带共享缓存）
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from app.core.cache import ensure_cache
from app.core.exceptions import StockDataError
from app.core.logging import get_logger
from app.tools import eastmoney_api
from app.tools import tushare_provider

logger = get_logger("app.tools.stock_data")

_ak = None


def _get_ak() -> Any:
    """懒加载 akshare"""
    global _ak
    if _ak is None:
        import akshare as ak
        _ak = ak
    return _ak


# =============================================================================
# 股票搜索与信息
# =============================================================================

def search_stocks(keyword: str, limit: int = 10) -> str:
    """
    根据关键词搜索股票（优先从全市场缓存中过滤）
    """
    try:
        # 优先从缓存获取全市场数据
        df = ensure_cache("market:spot")
        if df is None:
            # 缓存未命中，回退到直接请求
            logger.warning("search_cache_miss_fallback")
            ak = _get_ak()
            df = ak.stock_zh_a_spot_em()

        matched = df[
            df["名称"].str.contains(keyword, case=False, na=False) |
            df["代码"].str.contains(keyword, case=False, na=False)
        ].head(limit)

        results = []
        for _, row in matched.iterrows():
            results.append({
                "symbol": row["代码"],
                "name": row["名称"],
                "price": row.get("最新价"),
                "change_pct": row.get("涨跌幅"),
                "market": "sh" if str(row["代码"]).startswith("6") else "sz",
            })

        logger.info("stock_search", keyword=keyword, results=len(results), cached=ensure_cache("market:spot") is not None)
        return json.dumps({"keyword": keyword, "stocks": results}, ensure_ascii=False, default=str)

    except Exception as exc:
        logger.error("stock_search_failed", keyword=keyword, error=str(exc))
        raise StockDataError(f"搜索股票失败: {exc}") from exc


def get_stock_info(symbol: str) -> str:
    """
    获取股票基本信息
    """
    try:
        ak = _get_ak()
        df = ak.stock_individual_info_em(symbol=symbol)

        info = {}
        for _, row in df.iterrows():
            info[row["item"]] = row["value"]

        logger.info("stock_info_fetched", symbol=symbol)
        return json.dumps(info, ensure_ascii=False, default=str)

    except Exception as exc:
        logger.error("stock_info_failed", symbol=symbol, error=str(exc))
        raise StockDataError(f"获取股票信息失败: {exc}") from exc


# =============================================================================
# 实时行情（从缓存过滤）
# =============================================================================

def get_stock_realtime(symbol: str | None = None) -> str | dict:
    """
    获取股票实时行情
    单只股票走东财直连 API（~130ms），fallback 到 Tushare Pro 日线
    """
    try:
        if symbol:
            # 单只股票：东财直连（返回 dict，由 FastAPI 自动序列化）
            data = eastmoney_api.get_stock_realtime(symbol)
            logger.info("realtime_data_fetched", symbol=symbol, source="eastmoney")
            return data
        else:
            # 市场概况：从缓存取指数
            df = ensure_cache("market:index")
            if df is None:
                logger.warning("realtime_index_cache_miss_fallback")
                ak = _get_ak()
                df = ak.stock_zh_index_spot()

            indices = []
            for _, row in df.head(10).iterrows():
                indices.append({
                    "symbol": row.get("代码"),
                    "name": row.get("名称"),
                    "price": row.get("最新价"),
                    "change_pct": row.get("涨跌幅"),
                })
            data = {"market_overview": indices}

        logger.info("realtime_data_fetched", symbol=symbol)
        return json.dumps(data, ensure_ascii=False, default=str)

    except Exception as exc:
        logger.warning("realtime_eastmoney_failed", symbol=symbol, error=str(exc))

    # Fallback: Tushare Pro（日线级最新数据）
    if symbol:
        ts_data = tushare_provider.get_stock_latest(symbol)
        if ts_data:
            logger.info("realtime_data_fetched", symbol=symbol, source="tushare")
            return ts_data

    logger.error("realtime_all_failed", symbol=symbol)
    raise StockDataError(f"获取实时行情失败: 所有数据源均不可用")


# =============================================================================
# 历史数据
# =============================================================================

def get_stock_history(
    symbol: str,
    period: str = "daily",
    start: str | None = None,
    end: str | None = None,
    limit: int = 100,
) -> str:
    """
    获取股票历史K线数据
    优先使用 MarketDataCollector（腾讯财经 + AKShare fallback），
    避免直接调用 AKShare 东财接口导致 RemoteDisconnected。
    """
    # ── 第一层：MarketDataCollector（腾讯财经优先）──
    try:
        from app.strategies.market_data_collector import get_market_data_collector

        collector = get_market_data_collector()
        period_map = {"daily": "1D", "weekly": "1W", "monthly": "1M"}
        timeframe = period_map.get(period, "1D")

        klines = collector._get_kline(symbol, "stock", timeframe, limit)
        if klines:
            logger.info("history_fetched_tencent", symbol=symbol, period=period, records=len(klines))
            return json.dumps({"symbol": symbol, "period": period, "data": klines}, ensure_ascii=False, default=str)
    except Exception as exc:
        logger.warning("history_tencent_failed", symbol=symbol, error=str(exc))

    # ── 第二层：AKShare 东财接口 fallback ──
    try:
        ak = _get_ak()

        if not end:
            end = datetime.now().strftime("%Y%m%d")
        if not start:
            start_date = datetime.now() - timedelta(days=365)
            start = start_date.strftime("%Y%m%d")

        start_fmt = start.replace("-", "")
        end_fmt = end.replace("-", "")

        ak_period = {"daily": "daily", "weekly": "weekly", "monthly": "monthly"}.get(period, "daily")

        if ak_period == "daily":
            df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_fmt, end_date=end_fmt, adjust="qfq")
        elif ak_period == "weekly":
            df = ak.stock_zh_a_hist(symbol=symbol, period="weekly", start_date=start_fmt, end_date=end_fmt, adjust="qfq")
        else:
            df = ak.stock_zh_a_hist(symbol=symbol, period="monthly", start_date=start_fmt, end_date=end_fmt, adjust="qfq")

        if df.empty:
            return json.dumps({"symbol": symbol, "data": []}, ensure_ascii=False)

        df = df.tail(limit)

        records = []
        for _, row in df.iterrows():
            records.append({
                "date": row.get("日期"),
                "open": row.get("开盘"),
                "high": row.get("最高"),
                "low": row.get("最低"),
                "close": row.get("收盘"),
                "volume": row.get("成交量"),
                "amount": row.get("成交额"),
                "amplitude": row.get("振幅"),
                "change_pct": row.get("涨跌幅"),
                "change": row.get("涨跌额"),
                "turnover": row.get("换手率"),
            })

        logger.info("history_fetched_akshare", symbol=symbol, period=period, records=len(records))
        return json.dumps({"symbol": symbol, "period": period, "data": records}, ensure_ascii=False, default=str)

    except Exception as exc:
        logger.error("history_failed", symbol=symbol, error=str(exc))
        raise StockDataError(f"获取历史数据失败: {exc}") from exc


# =============================================================================
# 财务数据
# =============================================================================

def get_stock_financial(symbol: str) -> dict:
    """
    获取股票财务数据
    """
    try:
        ak = _get_ak()

        df = ak.stock_financial_report_sina(stock=symbol, symbol="利润表")

        financial = {
            "symbol": symbol,
            "profit": [],
        }

        if not df.empty:
            for _, row in df.head(4).iterrows():
                financial["profit"].append({
                    "date": row.get("报表日期"),
                    "revenue": row.get("营业收入"),
                    "net_profit": row.get("净利润"),
                })

        logger.info("financial_fetched", symbol=symbol)
        return financial

    except Exception as exc:
        logger.error("financial_failed", symbol=symbol, error=str(exc))
        raise StockDataError(f"获取财务数据失败: {exc}") from exc


# =============================================================================
# 资金流向
# =============================================================================

def get_capital_flow(symbol: str) -> dict:
    """
    获取个股资金流向（AKShare / Tushare fallback）
    """
    try:
        ak = _get_ak()
        df = ak.stock_individual_fund_flow(stock=symbol, market="sh" if symbol.startswith("6") else "sz")

        if not df.empty:
            records = []
            for _, row in df.head(5).iterrows():
                records.append({
                    "date": row.get("日期"),
                    "main_inflow": row.get("主力净流入-净额"),
                    "main_inflow_pct": row.get("主力净流入-净占比"),
                    "retail_inflow": row.get("散户净流入-净额"),
                })
            logger.info("capital_flow_fetched", symbol=symbol, count=len(records), source="akshare")
            return {"symbol": symbol, "flow": records}
    except Exception as exc:
        logger.warning("capital_flow_akshare_failed", symbol=symbol, error=str(exc))

    # Fallback: Tushare Pro
    ts_records = tushare_provider.get_capital_flow(symbol, limit=5)
    if ts_records is not None:
        logger.info("capital_flow_fetched", symbol=symbol, count=len(ts_records), source="tushare")
        return {"symbol": symbol, "flow": ts_records}

    logger.error("capital_flow_all_failed", symbol=symbol)
    raise StockDataError(f"获取资金流向失败: 所有数据源均不可用")
