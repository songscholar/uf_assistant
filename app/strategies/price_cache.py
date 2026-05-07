"""
UF Stock Assistant — 线程安全的内存价格缓存
移植自 QuantDinger TradingExecutor 的价格缓存逻辑
"""

from __future__ import annotations

import threading
import time


class PriceCache:
    """In-memory price cache with per-symbol TTL.

    Reduces redundant API calls when multiple strategies tick within
    the same cache window (default 10s).
    """

    def __init__(self, default_ttl: float = 10.0) -> None:
        self._default_ttl = default_ttl
        self._cache: dict[str, tuple[float, float]] = {}  # symbol -> (price, expiry_ts)
        self._lock = threading.Lock()

    def get(self, symbol: str) -> float | None:
        """Return cached price if not expired, else None."""
        with self._lock:
            entry = self._cache.get(symbol)
            if entry is None:
                return None
            price, expiry = entry
            if time.time() >= expiry:
                del self._cache[symbol]
                return None
            return price

    def set(self, symbol: str, price: float, ttl: float | None = None) -> None:
        """Store a price with TTL (seconds)."""
        with self._lock:
            self._cache[symbol] = (price, time.time() + (ttl or self._default_ttl))

    def clear(self) -> None:
        """Evict all entries."""
        with self._lock:
            self._cache.clear()

    def evict_expired(self) -> int:
        """Remove expired entries. Returns count removed."""
        now = time.time()
        with self._lock:
            expired = [k for k, (_, exp) in self._cache.items() if now >= exp]
            for k in expired:
                del self._cache[k]
            return len(expired)
