"""
UF Stock Assistant — 证券信息同步服务
定时从外部数据源拉取全量证券代码信息，写入本地 securities 表
前端/后端优先从本地表读取，避免每次实时调远程接口
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import insert, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core.logging import get_logger
from app.tools.crypto_data import _get_exchange
from app.trading.models import Security, get_db_session

logger = get_logger("app.services.market_sync")


# ── A股同步 ───────────────────────────────────────────────────────────────────

def _get_akshare() -> Any:
    """懒加载 AKShare"""
    try:
        import akshare as ak
        return ak
    except ImportError:
        logger.warning("akshare_not_installed")
        return None


def sync_a_share_securities() -> dict[str, int]:
    """同步全量 A 股证券信息到本地表

    Returns:
        {"inserted": n, "updated": m, "failed": k}
    """
    ak = _get_akshare()
    if ak is None:
        logger.error("akshare_unavailable")
        return {"inserted": 0, "updated": 0, "failed": 0}

    try:
        logger.info("a_share_sync_started")
        df = ak.stock_zh_a_spot_em()
        logger.info("a_share_data_fetched", rows=len(df))
    except Exception as exc:
        logger.error("a_share_fetch_failed", error=str(exc))
        return {"inserted": 0, "updated": 0, "failed": 0}

    inserted = 0
    updated = 0
    failed = 0

    with get_db_session() as db:
        for _, row in df.iterrows():
            try:
                symbol = str(row.get("代码", "")).strip()
                if not symbol:
                    continue

                # 从 AKShare 的 spot 表提取字段（列名可能因版本而异，防御性处理）
                name = row.get("名称") or row.get("股票名称") or None
                price = _to_float(row.get("最新价"))
                prev_close = _to_float(row.get("昨收"))
                open_price = _to_float(row.get("今开"))
                high = _to_float(row.get("最高"))
                low = _to_float(row.get("最低"))
                limit_up = _to_float(row.get("涨停价"))
                limit_down = _to_float(row.get("跌停价"))
                change_pct = _to_float(row.get("涨跌幅"))
                volume = _to_float(row.get("成交量"))
                amount = _to_float(row.get("成交额"))
                pe_ttm = _to_float(row.get("市盈率-动态")) or _to_float(row.get("市盈率"))
                pb = _to_float(row.get("市净率"))
                market_cap = _to_float(row.get("总市值"))
                float_cap = _to_float(row.get("流通市值"))
                turnover = _to_float(row.get("换手率"))

                # 判断板块（根据代码规则）
                category = _a_share_category(symbol)

                # SQLite upsert: INSERT ... ON CONFLICT DO UPDATE
                stmt = sqlite_insert(Security).values(
                    symbol=symbol,
                    name=name,
                    market_type="a_share",
                    category=category,
                    exchange="SH" if symbol.startswith(("6", "68", "5")) else "SZ",
                    price=price,
                    prev_close=prev_close,
                    open=open_price,
                    high=high,
                    low=low,
                    limit_up=limit_up,
                    limit_down=limit_down,
                    change_pct=change_pct,
                    volume=volume,
                    amount=amount,
                    lot_size=100,
                    pe_ttm=pe_ttm,
                    pb=pb,
                    market_cap=market_cap,
                    float_cap=float_cap,
                    turnover=turnover,
                    timestamp=datetime.now(timezone.utc),
                    source="akshare",
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["symbol"],
                    set_={
                        "name": stmt.excluded.name,
                        "category": stmt.excluded.category,
                        "price": stmt.excluded.price,
                        "prev_close": stmt.excluded.prev_close,
                        "open": stmt.excluded.open,
                        "high": stmt.excluded.high,
                        "low": stmt.excluded.low,
                        "limit_up": stmt.excluded.limit_up,
                        "limit_down": stmt.excluded.limit_down,
                        "change_pct": stmt.excluded.change_pct,
                        "volume": stmt.excluded.volume,
                        "amount": stmt.excluded.amount,
                        "pe_ttm": stmt.excluded.pe_ttm,
                        "pb": stmt.excluded.pb,
                        "market_cap": stmt.excluded.market_cap,
                        "float_cap": stmt.excluded.float_cap,
                        "turnover": stmt.excluded.turnover,
                        "timestamp": stmt.excluded.timestamp,
                        "source": stmt.excluded.source,
                    },
                )
                result = db.execute(stmt)
                if result.rowcount == 1:
                    # SQLite 无法区分 insert 和 update 的 rowcount，简单处理
                    inserted += 1
                else:
                    updated += 1
            except Exception as exc:
                failed += 1
                logger.warning("a_share_row_sync_failed", symbol=symbol, error=str(exc))

        db.commit()

    logger.info(
        "a_share_sync_completed",
        inserted=inserted,
        updated=updated,
        failed=failed,
    )
    return {"inserted": inserted, "updated": updated, "failed": failed}


# ── 币圈同步 ──────────────────────────────────────────────────────────────────

def sync_crypto_securities(exchange_id: str = "gate") -> dict[str, int]:
    """同步币圈交易对信息到本地表

    Returns:
        {"inserted": n, "updated": m, "failed": k}
    """
    try:
        logger.info("crypto_sync_started", exchange=exchange_id)
        ex = _get_exchange(exchange_id)
        tickers = ex.fetch_tickers()
        logger.info("crypto_data_fetched", pairs=len(tickers))
    except Exception as exc:
        logger.error("crypto_fetch_failed", error=str(exc))
        return {"inserted": 0, "updated": 0, "failed": 0}

    inserted = 0
    updated = 0
    failed = 0

    with get_db_session() as db:
        for symbol, ticker in tickers.items():
            try:
                if "/" not in symbol:
                    continue
                price = _to_float(ticker.get("last"))
                if price is None:
                    continue

                change_pct = _to_float(ticker.get("percentage"))
                volume = _to_float(ticker.get("baseVolume"))
                quote_volume = _to_float(ticker.get("quoteVolume"))
                open_price = _to_float(ticker.get("open"))
                high = _to_float(ticker.get("high"))
                low = _to_float(ticker.get("low"))
                bid = _to_float(ticker.get("bid"))
                ask = _to_float(ticker.get("ask"))
                prev_close = _to_float(ticker.get("previousClose"))

                stmt = sqlite_insert(Security).values(
                    symbol=symbol.upper(),
                    name=symbol.upper(),
                    market_type="crypto",
                    exchange=exchange_id.upper(),
                    price=price,
                    prev_close=prev_close,
                    open=open_price,
                    high=high,
                    low=low,
                    change_pct=change_pct,
                    volume=volume,
                    quote_volume=quote_volume,
                    bid_price=bid,
                    ask_price=ask,
                    lot_size=1,
                    timestamp=datetime.now(timezone.utc),
                    source=f"ccxt_{exchange_id}",
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["symbol"],
                    set_={
                        "price": stmt.excluded.price,
                        "prev_close": stmt.excluded.prev_close,
                        "open": stmt.excluded.open,
                        "high": stmt.excluded.high,
                        "low": stmt.excluded.low,
                        "change_pct": stmt.excluded.change_pct,
                        "volume": stmt.excluded.volume,
                        "quote_volume": stmt.excluded.quote_volume,
                        "bid_price": stmt.excluded.bid_price,
                        "ask_price": stmt.excluded.ask_price,
                        "timestamp": stmt.excluded.timestamp,
                        "source": stmt.excluded.source,
                    },
                )
                result = db.execute(stmt)
                if result.rowcount == 1:
                    inserted += 1
                else:
                    updated += 1
            except Exception as exc:
                failed += 1
                logger.warning("crypto_row_sync_failed", symbol=symbol, error=str(exc))

        db.commit()

    logger.info(
        "crypto_sync_completed",
        inserted=inserted,
        updated=updated,
        failed=failed,
    )
    return {"inserted": inserted, "updated": updated, "failed": failed}


# ── 统一入口 ──────────────────────────────────────────────────────────────────

def sync_all_securities() -> dict[str, Any]:
    """同步所有市场证券信息"""
    logger.info("sync_all_securities_started")
    a_result = sync_a_share_securities()
    crypto_result = sync_crypto_securities()
    return {
        "a_share": a_result,
        "crypto": crypto_result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _to_float(value: Any) -> float | None:
    """安全转换为 float"""
    if value is None or value == "-" or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _a_share_category(symbol: str) -> str | None:
    """根据代码判断 A 股板块"""
    if symbol.startswith("60"):
        return "沪市主板"
    if symbol.startswith("68"):
        return "科创板"
    if symbol.startswith("30"):
        return "创业板"
    if symbol.startswith("00"):
        return "深市主板"
    if symbol.startswith("8") or symbol.startswith("4"):
        return "北交所"
    if symbol.startswith("5"):
        return "沪市B股"
    return None
