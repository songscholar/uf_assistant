"""
UF Stock Assistant — 东方财富直连 API
替代 AKShare 爬虫，单股查询 ~130ms，指数 ~60ms
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any
from urllib import error, request

from app.core.logging import get_logger

logger = get_logger("app.tools.eastmoney")

# 请求头
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "*/*",
}

# 5 大指数 — 腾讯财经代码 + 元信息
_INDEX_CODES: list[tuple[str, str, str]] = [
    ("sh000001", "上证指数", "A股"),
    ("sh000016", "上证50", "沪市"),
    ("sz399001", "深证成指", "深市"),
    ("hkHSI", "恒生指数", "港股"),
    ("usNDX", "纳斯达克", "美股"),
]

# 单股行情字段
STOCK_FIELDS = "f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f60,f116,f117,f162,f167,f168,f170,f171"


def _fetch_json(url: str, timeout: float = 10, retries: int = 2) -> dict[str, Any]:
    """通用 JSON 请求，带重试和 JSONP 解析"""
    for attempt in range(retries + 1):
        try:
            req = request.Request(url, headers=_HEADERS)
            with request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8")
            if text.startswith("jQuery") or text.startswith("callback"):
                text = text[text.index("(") + 1 : text.rindex(")")]
            return json.loads(text)
        except Exception:
            if attempt < retries:
                time.sleep(0.5)
            else:
                raise


# =============================================================================
# 单股实时行情
# =============================================================================

def _get_stock_realtime_tencent(symbol: str) -> dict[str, Any]:
    """腾讯财经单股实时行情（国内直连，~80ms）"""
    prefix = "sh" if symbol.startswith("6") else "sz"
    url = f"https://qt.gtimg.cn/q={prefix}{symbol}"

    t0 = time.time()
    req = request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.qq.com/",
    })
    with request.urlopen(req, timeout=10) as resp:
        text = resp.read().decode("gbk", errors="replace")
    elapsed_ms = int((time.time() - t0) * 1000)

    lines = [l.strip() for l in text.split(";") if l.strip() and "v_" in l]
    if not lines:
        raise ValueError(f"腾讯财经未返回股票 {symbol} 数据")

    line = lines[0]
    eq = line.index("=")
    raw = line[eq + 2 : -1]  # 去掉引号
    fields = raw.split("~")
    if len(fields) < 55:
        raise ValueError(f"腾讯财经返回字段不足: {symbol}")

    def _f(idx: int) -> str:
        return fields[idx] if idx < len(fields) else ""

    def _flt(idx: int) -> float | None:
        v = _f(idx)
        try:
            return float(v) if v else None
        except ValueError:
            return None

    price = _flt(3)
    prev_close = _flt(4)
    change_pct = _flt(32)

    result = {
        "symbol": symbol,
        "name": _f(1),
        "price": price,
        "open": _flt(5),
        "high": _flt(33),
        "low": _flt(34),
        "prev_close": prev_close,
        "change_pct": change_pct,
        "change": round(price - prev_close, 2) if price and prev_close else None,
        "amplitude": None,
        "volume": int(_flt(36) or 0) * 100,  # 手 → 股
        "amount": round((_flt(37) or 0) * 10000, 2),  # 万元 → 元
        "pe_ttm": _flt(39),
        "pb": _flt(46),
        "turnover": _flt(38),
        "market_cap": round((_flt(44) or 0) * 100000000, 2),  # 亿 → 元
        "float_cap": round((_flt(45) or 0) * 100000000, 2),
        "limit_up": _flt(47),
        "limit_down": _flt(48),
        "timestamp": datetime.now().isoformat(),
        "latency_ms": elapsed_ms,
        "source": "tencent",
    }

    logger.info("tencent_stock_realtime", symbol=symbol, latency_ms=elapsed_ms)
    return result


def get_stock_realtime(symbol: str) -> dict[str, Any]:
    """
    获取单股实时行情（~130ms）
    优先东方财富，fallback 到腾讯财经

    Args:
        symbol: 股票代码，如 "600570"

    Returns:
        包含价格、涨跌幅、成交量等的字典
    """
    # 优先东方财富
    try:
        prefix = "1" if symbol.startswith("6") else "0"
        url = (
            f"https://push2.eastmoney.com/api/qt/stock/get"
            f"?secid={prefix}.{symbol}&fields={STOCK_FIELDS}"
            f"&_={int(time.time() * 1000)}"
        )

        t0 = time.time()
        data = _fetch_json(url)
        elapsed_ms = int((time.time() - t0) * 1000)

        raw = data.get("data")
        if not raw:
            raise ValueError(f"未找到股票 {symbol}")

        def _div100(v: Any) -> float | None:
            if isinstance(v, (int, float)) and v != "-":
                return v / 100
            return None

        result = {
            "symbol": str(raw.get("f57", symbol)),
            "name": str(raw.get("f58", "")),
            "price": _div100(raw.get("f43")),
            "open": _div100(raw.get("f46")),
            "high": _div100(raw.get("f44")),
            "low": _div100(raw.get("f45")),
            "prev_close": _div100(raw.get("f60")),
            "change_pct": _div100(raw.get("f170")),
            "amplitude": _div100(raw.get("f171")),
            "volume": raw.get("f47"),  # 手
            "amount": raw.get("f48"),  # 元
            "pe_ttm": _div100(raw.get("f162")),
            "pb": _div100(raw.get("f167")),
            "turnover": _div100(raw.get("f168")),
            "market_cap": raw.get("f116"),
            "float_cap": raw.get("f117"),
            "limit_up": _div100(raw.get("f51")),
            "limit_down": _div100(raw.get("f52")),
            "timestamp": datetime.now().isoformat(),
            "latency_ms": elapsed_ms,
            "source": "eastmoney",
        }

        logger.info("em_stock_realtime", symbol=symbol, latency_ms=elapsed_ms)
        return result
    except Exception as exc:
        logger.warning("em_stock_realtime_failed", symbol=symbol, error=str(exc))

    # Fallback: 腾讯财经
    return _get_stock_realtime_tencent(symbol)


# =============================================================================
# 5 大市场指数
# =============================================================================

def _parse_tencent_quote(line: str, idx_name: str, market: str) -> dict[str, Any] | None:
    """解析腾讯财经单行行情数据"""
    try:
        # 格式: v_CODE="fields..."
        eq_pos = line.index("=")
        raw = line[eq_pos + 2 : -2]  # 去掉引号
        fields = raw.split("~")
        if len(fields) < 35:
            return None
        return {
            "symbol": fields[2],
            "name": idx_name,
            "market": market,
            "value": float(fields[3]) if fields[3] else 0,
            "change": float(fields[31]) if fields[31] else 0,
            "change_percent": float(fields[32]) if fields[32] else 0,
        }
    except Exception:
        return None


def get_indices() -> list[dict[str, Any]]:
    """
    获取 5 大市场指数实时行情（腾讯财经 API，国内直连）

    Returns:
        [{symbol, name, market, value, change, change_percent}, ...]
    """
    codes = ",".join(s[0] for s in _INDEX_CODES)
    url = f"https://qt.gtimg.cn/q={codes}"

    t0 = time.time()
    req = request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.qq.com/",
    })
    with request.urlopen(req, timeout=10) as resp:
        text = resp.read().decode("gbk", errors="replace")
    elapsed_ms = int((time.time() - t0) * 1000)

    lines = [l.strip() for l in text.split(";") if l.strip()]

    results: list[dict[str, Any]] = []
    for i, line in enumerate(lines):
        if i < len(_INDEX_CODES):
            _, idx_name, market = _INDEX_CODES[i]
            parsed = _parse_tencent_quote(line, idx_name, market)
            if parsed:
                results.append(parsed)

    # 补齐缺失的指数
    existing_names = {r["name"] for r in results}
    for _, name, market in _INDEX_CODES:
        if name not in existing_names:
            results.append({"symbol": "", "name": name, "market": market, "value": 0, "change": 0, "change_percent": 0})

    logger.info("tencent_indices", count=len(results), latency_ms=elapsed_ms)
    return results


# =============================================================================
# 龙虎榜
# =============================================================================

def get_longhu_bang(date: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """
    获取龙虎榜数据（~256ms）

    Args:
        date: 日期，格式 YYYY-MM-DD，默认今天
        limit: 返回条数

    Returns:
        [{symbol, name, close_price, change_pct, reason}, ...]
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    url = (
        f"https://datacenter-web.eastmoney.com/api/data/v1/get"
        f"?sortColumns=TURNOVERRATE&sortTypes=-1&pageSize={limit}&pageNumber=1"
        f"&reportName=RPT_DAILYBILLBOARD_DETAILSNEW"
        f"&columns=ALL&filter=(TRADE_DATE%3E%3D%27{date}%27)"
        f"&source=WEB&client=WEB&_={int(time.time() * 1000)}"
    )

    t0 = time.time()
    data = _fetch_json(url)
    elapsed_ms = int((time.time() - t0) * 1000)

    records = data.get("result", {}).get("data", [])

    results: list[dict[str, Any]] = []
    for r in records:
        results.append({
            "symbol": r.get("SECURITY_CODE", ""),
            "name": r.get("SECURITY_NAME_ABBR", ""),
            "close_price": r.get("CLOSE_PRICE"),
            "change_pct": r.get("CHANGE_RATE"),
            "reason": r.get("EXPLANATION", ""),
            "turnover_rate": r.get("TURNOVERRATE"),
        })

    logger.info("em_longhu", date=date, count=len(results), latency_ms=elapsed_ms)
    return results


# =============================================================================
# A股涨跌统计
# =============================================================================

def get_market_stats() -> dict[str, Any]:
    """
    获取 A 股涨跌家数统计

    Returns:
        {up, down, flat, limit_up, limit_down, total}
    """
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        "?pn=1&pz=5000&po=1&np=1&fltt=2&invt=2&fid=f3"
        "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
        "&fields=f3&_=" + str(int(time.time() * 1000))
    )

    t0 = time.time()
    data = _fetch_json(url, timeout=15)
    elapsed_ms = int((time.time() - t0) * 1000)

    items = data.get("data", {}).get("diff", [])
    total = data.get("data", {}).get("total", 0)

    up = sum(1 for i in items if isinstance(i.get("f3"), (int, float)) and i["f3"] > 0)
    down = sum(1 for i in items if isinstance(i.get("f3"), (int, float)) and i["f3"] < 0)
    flat = sum(1 for i in items if isinstance(i.get("f3"), (int, float)) and i["f3"] == 0)
    limit_up = sum(1 for i in items if isinstance(i.get("f3"), (int, float)) and i["f3"] >= 9.9)
    limit_down = sum(1 for i in items if isinstance(i.get("f3"), (int, float)) and i["f3"] <= -9.9)

    result = {
        "up": up,
        "down": down,
        "flat": flat,
        "limit_up": limit_up,
        "limit_down": limit_down,
        "total": total,
        "latency_ms": elapsed_ms,
    }

    logger.info("em_market_stats", **result)
    return result
