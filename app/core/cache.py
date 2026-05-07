"""
UF Stock Assistant — 市场数据共享缓存
为 AKShare 全量数据接口提供 TTL 缓存，避免重复爬取
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

import pandas as pd

from app.core.logging import get_logger

logger = get_logger("app.core.cache")

# 缓存 TTL（秒）— 5 分钟
CACHE_TTL = 300

# 后台刷新间隔（秒）— 5 分钟
REFRESH_INTERVAL = 300

# 全局缓存存储
_cache_store: dict[str, Any] = {}
_cache_timestamp: dict[str, float] = {}
_lock = threading.RLock()


def _is_fresh(key: str, ttl: int = CACHE_TTL) -> bool:
    """检查缓存是否未过期"""
    with _lock:
        if key not in _cache_store:
            return False
        ts = _cache_timestamp.get(key, 0)
        return time.time() - ts < ttl


def get_cached_df(key: str) -> pd.DataFrame | None:
    """获取缓存的 DataFrame"""
    with _lock:
        if _is_fresh(key):
            return _cache_store[key]
        return None


def set_cached_df(key: str, df: pd.DataFrame) -> None:
    """设置缓存的 DataFrame"""
    with _lock:
        _cache_store[key] = df
        _cache_timestamp[key] = time.time()


def invalidate_cache(key: str | None = None) -> None:
    """清除缓存，key 为 None 时清除全部"""
    with _lock:
        if key is None:
            _cache_store.clear()
            _cache_timestamp.clear()
            logger.info("cache_invalidated_all")
        elif key in _cache_store:
            del _cache_store[key]
            del _cache_timestamp[key]
            logger.info("cache_invalidated", key=key)


def get_cache_info() -> dict[str, Any]:
    """获取缓存状态信息"""
    with _lock:
        now = time.time()
        return {
            "keys": list(_cache_store.keys()),
            "ttl_seconds": CACHE_TTL,
            "entries": {
                k: {
                    "age_seconds": round(now - _cache_timestamp.get(k, 0), 1),
                    "is_fresh": _is_fresh(k),
                    "shape": _cache_store[k].shape if hasattr(_cache_store[k], "shape") else None,
                }
                for k in _cache_store
            },
        }


# ========================================================================
# 市场数据缓存加载器
# ========================================================================

def _load_spot_data() -> pd.DataFrame | None:
    """加载全市场 A 股实时数据"""
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        logger.info("cache_load_spot_ok", rows=len(df))
        return df
    except Exception as exc:
        logger.error("cache_load_spot_failed", error=str(exc))
        return None


def _load_index_data() -> pd.DataFrame | None:
    """加载大盘指数实时数据"""
    try:
        import akshare as ak
        df = ak.stock_zh_index_spot_em()
        logger.info("cache_load_index_ok", rows=len(df))
        return df
    except Exception as exc:
        logger.error("cache_load_index_failed", error=str(exc))
        return None


def _load_sector_data() -> pd.DataFrame | None:
    """加载板块热点数据"""
    try:
        import akshare as ak
        # 优先行业板块
        try:
            df = ak.stock_board_industry_spot_em()
        except Exception:
            df = ak.stock_board_concept_spot_em()
        logger.info("cache_load_sector_ok", rows=len(df))
        return df
    except Exception as exc:
        logger.error("cache_load_sector_failed", error=str(exc))
        return None


def refresh_cache(key: str) -> bool:
    """手动刷新指定缓存"""
    loaders = {
        "market:spot": _load_spot_data,
        "market:index": _load_index_data,
        "market:sector": _load_sector_data,
    }
    loader = loaders.get(key)
    if not loader:
        return False
    df = loader()
    if df is not None:
        set_cached_df(key, df)
        return True
    return False


def ensure_cache(key: str) -> pd.DataFrame | None:
    """确保缓存存在，如果不存在或已过期则刷新"""
    df = get_cached_df(key)
    if df is not None:
        return df
    if refresh_cache(key):
        return get_cached_df(key)
    return None


# ========================================================================
# 后台刷新任务（用于 FastAPI lifespan）
# ========================================================================

_stop_event = asyncio.Event()


async def _background_refresh_loop() -> None:
    """后台定时刷新缓存"""
    # 首次延迟 3 秒，让服务先完成启动
    await asyncio.sleep(3)

    while not _stop_event.is_set():
        start = time.perf_counter()
        logger.info("background_refresh_start")

        # 指数和龙虎榜已走东财直连，不再需要缓存刷新
        for key in ("market:spot", "market:sector"):
            if _stop_event.is_set():
                break
            try:
                # 在线程池中执行同步 AKShare 调用
                loop = asyncio.get_running_loop()
                df = await loop.run_in_executor(None, refresh_cache, key)
                if df:
                    logger.info("background_refresh_ok", key=key)
                else:
                    logger.warning("background_refresh_failed", key=key)
            except Exception as exc:
                logger.error("background_refresh_error", key=key, error=str(exc))

        elapsed = time.perf_counter() - start
        logger.info("background_refresh_done", elapsed_ms=int(elapsed * 1000))

        # 等待到下一个周期，但可被 stop_event 中断
        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=REFRESH_INTERVAL)
        except asyncio.TimeoutError:
            pass


def start_background_refresh() -> asyncio.Task:
    """启动后台刷新任务"""
    _stop_event.clear()
    return asyncio.create_task(_background_refresh_loop())


def stop_background_refresh() -> None:
    """停止后台刷新任务"""
    _stop_event.set()
