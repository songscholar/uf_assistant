"""
UF Stock Assistant — Tushare Pro 数据提供层
作为 AKShare / 东方财富 / 腾讯财经的兜底数据源

环境变量: STOCK_ASSISTANT_TUSHARE_TOKEN
注册: https://tushare.pro/register
免费版额度: 约 5000 积分/分钟
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.core.logging import get_logger

logger = get_logger("app.tools.tushare")

_ts_pro: Any | None = None


def _get_pro() -> Any | None:
    """懒加载 Tushare Pro API，未配置 token 时返回 None"""
    global _ts_pro
    if _ts_pro is not None:
        return _ts_pro

    try:
        from app.core.config import get_settings

        token = get_settings().tushare_token
        if not token:
            return None
        import tushare as ts

        _ts_pro = ts.pro_api(token)
        logger.info("tushare_initialized")
        return _ts_pro
    except Exception as exc:
        logger.warning("tushare_init_failed", error=str(exc))
        return None


def _today() -> str:
    return datetime.now().strftime("%Y%m%d")


def _to_symbol_ts(symbol: str) -> str:
    """600519 → 600519.SH, 000001 → 000001.SZ"""
    prefix = "SH" if symbol.startswith("6") else "SZ"
    return f"{symbol}.{prefix}"


def _from_symbol_ts(ts_code: str) -> str:
    """600519.SH → 600519"""
    return ts_code.split(".")[0]


# =============================================================================
# 指数行情
# =============================================================================

_INDEX_MAP = {
    "000001": "000001.SH",
    "000016": "000016.SH",
    "399001": "399001.SZ",
}


def get_indices() -> list[dict[str, Any]] | None:
    """
    获取 A 股主要指数最新行情（Tushare index_daily）
    返回 None 表示未启用或失败
    """
    pro = _get_pro()
    if pro is None:
        return None

    try:
        today = _today()
        start = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
        results: list[dict[str, Any]] = []

        for sym, ts_code in _INDEX_MAP.items():
            df = pro.index_daily(ts_code=ts_code, start_date=start, end_date=today)
            if df.empty:
                continue
            row = df.iloc[0]
            prev_close = float(row["pre_close"])
            close = float(row["close"])
            change = close - prev_close
            change_pct = (change / prev_close * 100) if prev_close else 0.0

            name_map = {"000001": "上证指数", "000016": "上证50", "399001": "深证成指"}
            market_map = {"000001": "A股", "000016": "沪市", "399001": "深市"}
            results.append({
                "symbol": sym,
                "name": name_map.get(sym, ""),
                "market": market_map.get(sym, ""),
                "value": round(close, 2),
                "change": round(change, 2),
                "change_percent": round(change_pct, 2),
            })

        logger.info("tushare_indices_fetched", count=len(results))
        return results if results else None
    except Exception as exc:
        logger.warning("tushare_indices_failed", error=str(exc))
        return None


# =============================================================================
# 北向资金
# =============================================================================

def get_northbound_flow(limit: int = 5) -> list[dict[str, Any]] | None:
    """
    获取北向资金每日流向（Tushare moneyflow_hsgt）
    返回 None 表示未启用或失败
    """
    pro = _get_pro()
    if pro is None:
        return None

    try:
        today = _today()
        start = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
        df = pro.moneyflow_hsgt(start_date=start, end_date=today)
        if df.empty:
            return None

        records = []
        for _, row in df.head(limit).iterrows():
            records.append({
                "date": str(row.get("trade_date", "")),
                "net_inflow": round(float(row.get("north_money", 0)), 2),
                "cumulative": None,  # Tushare 无累计字段
            })

        logger.info("tushare_northbound_fetched", count=len(records))
        return records
    except Exception as exc:
        logger.warning("tushare_northbound_failed", error=str(exc))
        return None


# =============================================================================
# 龙虎榜
# =============================================================================

def get_longhu_bang(trade_date: str | None = None, limit: int = 20) -> list[dict[str, Any]] | None:
    """
    获取龙虎榜数据（Tushare top_list）
    返回 None 表示未启用或失败
    """
    pro = _get_pro()
    if pro is None:
        return None

    try:
        if not trade_date:
            trade_date = _today()
        else:
            trade_date = trade_date.replace("-", "")

        df = pro.top_list(trade_date=trade_date)
        if df.empty:
            return None

        records = []
        for _, row in df.head(limit).iterrows():
            records.append({
                "symbol": _from_symbol_ts(str(row.get("ts_code", ""))),
                "name": str(row.get("name", "")),
                "close_price": row.get("close"),
                "change_pct": row.get("pct_change"),
                "reason": str(row.get("reason", "")),
                "turnover_rate": row.get("turnover_rate"),
            })

        logger.info("tushare_longhu_fetched", count=len(records))
        return records
    except Exception as exc:
        logger.warning("tushare_longhu_failed", error=str(exc))
        return None


# =============================================================================
# 个股最新日线（作为实时兜底）
# =============================================================================

def get_stock_latest(symbol: str) -> dict[str, Any] | None:
    """
    获取个股最新日线数据（Tushare daily）
    返回 None 表示未启用或失败
    """
    pro = _get_pro()
    if pro is None:
        return None

    try:
        ts_code = _to_symbol_ts(symbol)
        today = _today()
        start = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
        df = pro.daily(ts_code=ts_code, start_date=start, end_date=today)
        if df.empty:
            return None

        row = df.iloc[0]
        prev_close = float(row["pre_close"])
        close = float(row["close"])
        change_pct = ((close - prev_close) / prev_close * 100) if prev_close else 0.0

        result = {
            "symbol": symbol,
            "name": "",
            "price": round(close, 2),
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "prev_close": round(prev_close, 2),
            "change_pct": round(change_pct, 2),
            "volume": int(row["vol"]) * 100,  # Tushare 单位是手，转为股
            "amount": float(row["amount"]) * 1000,  # Tushare 单位是千元，转为元
            "timestamp": datetime.now().isoformat(),
            "source": "tushare",
        }

        logger.info("tushare_stock_latest_fetched", symbol=symbol)
        return result
    except Exception as exc:
        logger.warning("tushare_stock_latest_failed", symbol=symbol, error=str(exc))
        return None


# =============================================================================
# 个股资金流向（日线级主力/散户资金）
# =============================================================================

def get_capital_flow(symbol: str, limit: int = 5) -> list[dict[str, Any]] | None:
    """
    获取个股资金流向（Tushare moneyflow）
    返回 None 表示未启用或失败
    """
    pro = _get_pro()
    if pro is None:
        return None

    try:
        ts_code = _to_symbol_ts(symbol)
        today = _today()
        start = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
        df = pro.moneyflow(ts_code=ts_code, start_date=start, end_date=today)
        if df.empty:
            return None

        records = []
        for _, row in df.head(limit).iterrows():
            records.append({
                "date": str(row.get("trade_date", "")),
                "main_inflow": round(float(row.get("net_mf_amount", 0)), 2),
                "main_inflow_pct": round(float(row.get("net_mf_rate", 0)), 2),
                "retail_inflow": None,  # Tushare 无散户净流入字段
            })

        logger.info("tushare_capital_flow_fetched", symbol=symbol, count=len(records))
        return records
    except Exception as exc:
        logger.warning("tushare_capital_flow_failed", symbol=symbol, error=str(exc))
        return None
