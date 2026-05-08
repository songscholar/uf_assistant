"""
UF Stock Assistant — 市场数据工具
大盘指数、板块热点、龙虎榜等市场层面数据（带共享缓存）
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib import request

from app.core.cache import ensure_cache
from app.core.exceptions import DataProviderError
from app.core.logging import get_logger
from app.tools import eastmoney_api
from app.tools import tushare_provider

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
    获取 5 大市场指数实时行情（腾讯财经 / Tushare Pro fallback）
    A股（上证指数）、沪市（上证50）、深市（深证成指）、港股（恒生指数）、美股（纳斯达克）
    """
    try:
        indices = eastmoney_api.get_indices()
        logger.info("market_index_fetched", indices=len(indices), source="tencent")
        return {"indices": indices, "timestamp": datetime.now().isoformat(), "source": "live"}

    except Exception as exc:
        logger.warning("market_index_tencent_failed", error=str(exc))

    # Fallback: Tushare Pro
    ts_indices = tushare_provider.get_indices()
    if ts_indices:
        # Tushare 只有 A 股指数，补充港股/美股 demo 数据占位
        existing = {i["symbol"] for i in ts_indices}
        if "HSI" not in existing:
            ts_indices.append({"symbol": "HSI", "name": "恒生指数", "market": "港股", "value": 0, "change": 0, "change_percent": 0})
        if "NDX" not in existing:
            ts_indices.append({"symbol": "NDX", "name": "纳斯达克", "market": "美股", "value": 0, "change": 0, "change_percent": 0})
        logger.info("market_index_fetched", indices=len(ts_indices), source="tushare")
        return {"indices": ts_indices, "timestamp": datetime.now().isoformat(), "source": "live"}

    logger.error("market_index_all_failed")
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
    获取板块热点（行业涨幅排行）
    使用 AKShare 同花顺板块摘要接口
    """
    try:
        ak = _get_ak()
        df = ak.stock_board_industry_summary_ths()
        sectors = []
        for _, row in df.head(15).iterrows():
            name = str(row.get("板块", "")).strip()
            if not name:
                continue
            sectors.append({
                "name": name,
                "change_percent": float(row.get("涨跌幅", 0)),
                "up_count": int(row.get("上涨家数", 0)),
                "down_count": int(row.get("下跌家数", 0)),
                "net_inflow": float(row.get("净流入", 0)),
                "leader": str(row.get("领涨股", "")),
                "leader_change": float(row.get("领涨股-涨跌幅", 0)),
            })
            if len(sectors) >= 10:
                break

        if not sectors:
            raise DataProviderError("无法获取板块数据")

        logger.info("sector_hot_fetched", sectors=len(sectors), source="ths")
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

def get_longhu_bang(date: str | None = None) -> dict:
    """
    获取龙虎榜数据（东方财富 / Tushare fallback）
    """
    try:
        result = eastmoney_api.get_longhu_bang(date)
        logger.info("longhu_bang_fetched", date=result.get("date"), records=len(result.get("data", [])), source="eastmoney")
        return result
    except Exception as exc:
        logger.warning("longhu_bang_eastmoney_failed", date=date, error=str(exc))

    # Fallback: Tushare Pro
    ts_records = tushare_provider.get_longhu_bang(trade_date=date)
    if ts_records is not None:
        logger.info("longhu_bang_fetched", date=date, records=len(ts_records), source="tushare")
        return {"date": date, "data": ts_records}

    logger.error("longhu_bang_all_failed", date=date)
    raise DataProviderError("获取龙虎榜失败: 所有数据源均不可用")


# =============================================================================
# 市场概况（从缓存读取）
# =============================================================================

def _get_tencent_market_stats() -> dict[str, Any]:
    """用腾讯财经批量获取全市场个股行情，统计涨跌家数。"""
    ak = _get_ak()
    df = ak.stock_info_a_code_name()
    codes = []
    for _, row in df.iterrows():
        c = str(row["code"]).strip()
        prefix = "sh" if c.startswith("6") else "sz"
        codes.append(prefix + c)

    batch_size = 800
    all_changes: list[float] = []
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i + batch_size]
        url = "https://qt.gtimg.cn/q=" + ",".join(batch)
        req = request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("gbk", errors="replace")
        for line in text.split(";"):
            line = line.strip()
            if not line or "v_" not in line:
                continue
            try:
                eq = line.index("=")
                raw = line[eq + 2 : -1]  # 去掉引号
                fields = raw.split("~")
                if len(fields) < 35:
                    continue
                change_pct = float(fields[32]) if fields[32] else 0.0
                all_changes.append(change_pct)
            except Exception:
                continue

    return {
        "up": sum(1 for x in all_changes if x > 0),
        "down": sum(1 for x in all_changes if x < 0),
        "flat": sum(1 for x in all_changes if x == 0),
        "limit_up": sum(1 for x in all_changes if x >= 9.9),
        "limit_down": sum(1 for x in all_changes if x <= -9.9),
        "total": len(all_changes),
    }


def get_market_overview() -> dict:
    """
    获取市场整体概况
    腾讯财经批量获取全市场个股行情，自统计涨跌家数 + 5 大指数
    """
    try:
        stats = _get_tencent_market_stats()
        indices = eastmoney_api.get_indices()

        logger.info("market_overview_fetched", **stats)
        return {
            "timestamp": datetime.now().isoformat(),
            "source": "live",
            "summary": {
                "up": stats["up"],
                "down": stats["down"],
                "flat": stats["flat"],
                "limit_up": stats["limit_up"],
                "limit_down": stats["limit_down"],
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
    优先 AKShare，fallback 到 Tushare Pro
    """
    records: list[dict[str, Any]] = []
    try:
        ak = _get_ak()
        df = ak.stock_hsgt_hist_em(symbol="北向资金")

        if not df.empty:
            # 修复列名：AKShare 实际列名是"当日成交净买额"和"历史累计净买额"
            # 数据源从 2024-08 后部分断档，倒序遍历全表找最新有效数据
            for _, row in df.iloc[::-1].iterrows():  # 倒序遍历
                net = row.get("当日成交净买额")
                cum = row.get("历史累计净买额")
                date = str(row.get("日期", ""))
                if net is None or (isinstance(net, float) and net != net):  # NaN check
                    continue
                records.append({
                    "date": date,
                    "net_inflow": round(float(net), 2) if net is not None else None,
                    "cumulative": round(float(cum), 2) if cum is not None else None,
                })
                if len(records) >= 5:
                    break

        if records:
            logger.info("northbound_fetched", count=len(records), source="akshare")
            return {"flow": records, "source": "live"}
    except Exception as exc:
        logger.warning("northbound_akshare_failed", error=str(exc))

    # Fallback: Tushare Pro（覆盖 AKShare 断档或异常场景）
    ts_records = tushare_provider.get_northbound_flow(limit=5)
    if ts_records:
        logger.info("northbound_fetched", count=len(ts_records), source="tushare")
        return {"flow": ts_records, "source": "live"}

    logger.error("northbound_all_failed")
    return {"flow": [], "source": "demo"}
