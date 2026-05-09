"""
UF Stock Assistant — Market Data Collector

Collects price, kline, technical indicators, and fundamental data
for AI analysis. Uses UF's existing AKShare (A-stock) and CCXT (crypto) tools.

Technical indicators are computed inline — no external TA library required.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any
from urllib import request

from app.core.logging import get_logger

logger = get_logger("app.strategies.market_data_collector")


class MarketDataCollector:
    """Collect market data for AI analysis — price, kline, indicators, fundamentals."""

    def collect_all(
        self,
        symbol: str,
        market_type: str = "stock",
        timeframe: str = "1D",
        limit: int = 60,
    ) -> dict[str, Any]:
        """
        Collect all available data for a symbol.

        Args:
            symbol: e.g. "600519" (A-stock) or "BTC/USDT" (crypto)
            market_type: "stock" or "crypto"
            timeframe: kline timeframe
            limit: number of kline bars

        Returns:
            Dict with keys: price, kline, indicators, fundamental, _meta
        """
        start = time.time()
        data: dict[str, Any] = {
            "symbol": symbol,
            "market_type": market_type,
            "timeframe": timeframe,
            "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "price": None,
            "kline": None,
            "indicators": {},
            "fundamental": {},
            "_meta": {"success": [], "failed": [], "duration_ms": 0},
        }

        # Core data: price + kline in parallel
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                pool.submit(self._get_price, symbol, market_type): "price",
                pool.submit(self._get_kline, symbol, market_type, timeframe, limit): "kline",
            }
            try:
                for future in as_completed(futures, timeout=15):
                    key = futures[future]
                    try:
                        result = future.result(timeout=5)
                        if result:
                            data[key] = result
                            data["_meta"]["success"].append(key)
                        else:
                            data["_meta"]["failed"].append(key)
                    except Exception as exc:
                        logger.warning("core_data_failed", key=key, error=str(exc))
                        data["_meta"]["failed"].append(key)
            except Exception:
                logger.warning("core_data_timeout", symbol=symbol)

        # Technical indicators from kline
        if data["kline"]:
            try:
                data["indicators"] = self._calculate_indicators(data["kline"])
                data["_meta"]["success"].append("indicators")
            except Exception as exc:
                logger.warning("indicators_failed", error=str(exc))
                data["_meta"]["failed"].append("indicators")

        # Fundamental (A-stock only via AKShare)
        if market_type == "stock":
            try:
                data["fundamental"] = self._get_fundamental(symbol)
                if data["fundamental"]:
                    data["_meta"]["success"].append("fundamental")
                else:
                    data["_meta"]["failed"].append("fundamental")
            except Exception as exc:
                logger.warning("fundamental_failed", error=str(exc))
                data["_meta"]["failed"].append("fundamental")

        data["_meta"]["duration_ms"] = int((time.time() - start) * 1000)
        logger.info(
            "collect_done",
            symbol=symbol,
            duration_ms=data["_meta"]["duration_ms"],
            success=data["_meta"]["success"],
            failed=data["_meta"]["failed"],
        )
        return data

    # ── Data Fetchers ───────────────────────────────────────────────────────

    def _get_price(self, symbol: str, market_type: str) -> dict[str, Any] | None:
        """Fetch latest price. Returns price dict or None."""
        try:
            if market_type == "crypto":
                return self._get_crypto_price(symbol)
            return self._get_stock_price(symbol)
        except Exception as exc:
            logger.warning("price_fetch_failed", symbol=symbol, error=str(exc))
            return None

    def _get_stock_price(self, symbol: str) -> dict[str, Any] | None:
        """Fetch A-stock price via eastmoney_api (with tencent fallback)."""
        try:
            from app.tools import eastmoney_api

            raw = eastmoney_api.get_stock_realtime(symbol)
            if not raw:
                return None

            price = raw.get("price")
            prev_close = raw.get("prev_close")
            return {
                "price": price,
                "change": round(price - prev_close, 2) if price and prev_close else None,
                "changePercent": raw.get("change_pct"),
                "high": raw.get("high"),
                "low": raw.get("low"),
                "open": raw.get("open"),
                "volume": raw.get("volume"),
                "amount": raw.get("amount"),
                "source": raw.get("source", "eastmoney"),
            }
        except Exception as exc:
            logger.warning("stock_price_failed", symbol=symbol, error=str(exc))
            return None

    def _get_crypto_price(self, symbol: str) -> dict[str, Any] | None:
        """Fetch crypto price via UF's exchange client or CCXT directly."""
        try:
            import ccxt

            exchange = ccxt.binance({"enableRateLimit": True})
            ticker = exchange.fetch_ticker(symbol)
            return {
                "price": ticker.get("last", 0),
                "change": (ticker.get("last", 0) or 0) - (ticker.get("open", 0) or 0),
                "changePercent": ticker.get("percentage", 0),
                "high": ticker.get("high", 0),
                "low": ticker.get("low", 0),
                "open": ticker.get("open", 0),
                "volume": ticker.get("baseVolume", 0),
                "source": "ccxt",
            }
        except Exception as exc:
            logger.warning("crypto_price_failed", symbol=symbol, error=str(exc))
            return None

    def _get_kline(
        self, symbol: str, market_type: str, timeframe: str, limit: int
    ) -> list[dict[str, Any]] | None:
        """Fetch kline data. Returns list of OHLCV dicts or None."""
        try:
            if market_type == "crypto":
                return self._get_crypto_kline(symbol, timeframe, limit)
            return self._get_stock_kline(symbol, timeframe, limit)
        except Exception as exc:
            logger.warning("kline_fetch_failed", symbol=symbol, error=str(exc))
            return None

    def _get_stock_kline(
        self, symbol: str, timeframe: str, limit: int
    ) -> list[dict[str, Any]] | None:
        """Fetch A-stock kline via tencent finance API (bypass AKShare EM restriction)."""
        try:
            return self._get_stock_kline_tencent(symbol, timeframe, limit)
        except Exception as exc:
            logger.warning("stock_kline_tencent_failed", symbol=symbol, error=str(exc))
            # Fallback: try AKShare if available
            try:
                import akshare as ak

                period_map = {"1D": "daily", "1W": "weekly", "1M": "monthly"}
                period = period_map.get(timeframe, "daily")
                df = ak.stock_zh_a_hist(symbol=symbol, period=period, adjust="qfq")

                if df is None or df.empty:
                    return None

                df = df.tail(limit)
                klines: list[dict[str, Any]] = []
                for _, row in df.iterrows():
                    klines.append({
                        "date": str(row.get("日期", "")),
                        "open": float(row.get("开盘", 0)),
                        "high": float(row.get("最高", 0)),
                        "low": float(row.get("最低", 0)),
                        "close": float(row.get("收盘", 0)),
                        "volume": float(row.get("成交量", 0)),
                        "amount": float(row.get("成交额", 0)),
                    })
                return klines
            except Exception as exc2:
                logger.warning("stock_kline_akshare_failed", symbol=symbol, error=str(exc2))
                return None

    def _get_stock_kline_tencent(
        self, symbol: str, timeframe: str, limit: int
    ) -> list[dict[str, Any]] | None:
        """Fetch A-stock kline via Tencent finance API (direct HTTP)."""
        from app.tools.stock_exchange import get_tencent_prefix

        if timeframe not in ("1D", "day"):
            # Tencent API only supports daily; fallback for weekly/monthly
            raise ValueError("Tencent kline only supports daily timeframe")

        prefix = get_tencent_prefix(symbol)
        end = datetime.now()
        start = end - timedelta(days=limit * 2 + 30)  # buffer for holidays
        end_str = end.strftime("%Y-%m-%d")
        start_str = start.strftime("%Y-%m-%d")

        url = (
            f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
            f"?param={prefix}{symbol},day,{start_str},{end_str},{limit},qfq"
        )

        req = request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.qq.com/",
        })
        with request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))

        if data.get("code") != 0:
            raise ValueError(f"Tencent kline API error: {data.get('msg')}")

        stock_data = data.get("data", {}).get(f"{prefix}{symbol}", {})
        # Try qfqday first (前复权), then day (不复权)
        rows = stock_data.get("qfqday") or stock_data.get("day")
        if not rows:
            raise ValueError("No kline data returned")

        klines: list[dict[str, Any]] = []
        for row in rows:
            if len(row) < 6:
                continue
            klines.append({
                "date": str(row[0]),
                "open": float(row[1]),
                "close": float(row[2]),
                "high": float(row[3]),
                "low": float(row[4]),
                "volume": float(row[5]),
            })

        # Return last `limit` bars
        return klines[-limit:] if len(klines) > limit else klines

    def _get_crypto_kline(
        self, symbol: str, timeframe: str, limit: int
    ) -> list[dict[str, Any]] | None:
        """Fetch crypto kline via CCXT."""
        try:
            import ccxt

            tf_map = {"1D": "1d", "1W": "1w", "1M": "1M", "1h": "1h", "4h": "4h"}
            tf = tf_map.get(timeframe, "1d")

            exchange = ccxt.binance({"enableRateLimit": True})
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=limit)

            if not ohlcv:
                return None

            klines: list[dict[str, Any]] = []
            for candle in ohlcv:
                klines.append({
                    "timestamp": candle[0],
                    "open": candle[1],
                    "high": candle[2],
                    "low": candle[3],
                    "close": candle[4],
                    "volume": candle[5],
                })
            return klines
        except Exception as exc:
            logger.warning("crypto_kline_failed", symbol=symbol, error=str(exc))
            return None

    def _get_fundamental(self, symbol: str) -> dict[str, Any] | None:
        """Fetch A-stock fundamental data via eastmoney_api (real-time quote includes PE/PB/cap)."""
        try:
            from app.tools import eastmoney_api

            raw = eastmoney_api.get_stock_realtime(symbol)
            if not raw:
                return None

            info: dict[str, Any] = {}
            if raw.get("pe_ttm") is not None:
                info["pe_ratio"] = raw["pe_ttm"]
            if raw.get("pb") is not None:
                info["pb_ratio"] = raw["pb"]
            if raw.get("market_cap") is not None:
                info["market_cap"] = raw["market_cap"]
            if raw.get("float_cap") is not None:
                info["float_market_cap"] = raw["float_cap"]
            if raw.get("turnover") is not None:
                info["turnover_rate"] = raw["turnover"]
            if raw.get("name"):
                info["name"] = raw["name"]

            return info if info else None
        except Exception as exc:
            logger.warning("fundamental_failed", symbol=symbol, error=str(exc))
            return None

    # ── Technical Indicators (inline, no external deps) ─────────────────────

    def _calculate_indicators(self, klines: list[dict[str, Any]]) -> dict[str, Any]:
        """Calculate RSI, MACD, ATR, Bollinger, MA, support/resistance from klines."""
        if not klines or len(klines) < 5:
            return {}

        closes = [float(k.get("close", 0)) for k in klines]
        highs = [float(k.get("high", 0)) for k in klines]
        lows = [float(k.get("low", 0)) for k in klines]
        volumes = [float(k.get("volume", 0)) for k in klines]

        if not closes or closes[-1] <= 0:
            return {}

        price = closes[-1]
        indicators: dict[str, Any] = {"current_price": round(price, 6)}

        # RSI
        if len(closes) >= 15:
            rsi = self._calc_rsi(closes, 14)
            indicators["rsi"] = {
                "value": round(rsi, 2),
                "signal": "oversold" if rsi < 30 else ("overbought" if rsi > 70 else "neutral"),
            }

        # MACD
        if len(closes) >= 35:
            macd = self._calc_macd(closes)
            indicators["macd"] = macd

        # Moving Averages
        ma5 = sum(closes[-5:]) / 5 if len(closes) >= 5 else price
        ma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else price
        ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else price

        if price > ma5 > ma10 > ma20:
            ma_trend = "strong_uptrend"
        elif price > ma20:
            ma_trend = "uptrend"
        elif price < ma5 < ma10 < ma20:
            ma_trend = "strong_downtrend"
        elif price < ma20:
            ma_trend = "downtrend"
        else:
            ma_trend = "sideways"

        indicators["moving_averages"] = {
            "ma5": round(ma5, 6),
            "ma10": round(ma10, 6),
            "ma20": round(ma20, 6),
            "trend": ma_trend,
        }
        indicators["trend"] = ma_trend

        # Bollinger Bands
        if len(closes) >= 20:
            bb = self._calc_bollinger(closes, 20, 2.0)
            if bb:
                indicators["bollinger"] = bb

        # ATR + Volatility
        if len(klines) >= 15:
            atr = self._calc_atr(klines, 14)
            vol_pct = (atr / price * 100) if price > 0 else 0
            indicators["volatility"] = {
                "level": "high" if vol_pct > 5 else ("medium" if vol_pct > 2 else "low"),
                "pct": round(vol_pct, 2),
                "atr": round(atr, 6),
            }

            # Trading levels
            sl = max(price - 2 * atr, price * 0.95) if atr > 0 else price * 0.95
            tp = price + 3 * atr if atr > 0 else price * 1.05
            risk = price - sl
            reward = tp - price
            indicators["trading_levels"] = {
                "stop_loss": round(sl, 6),
                "take_profit": round(tp, 6),
                "risk_reward": round(reward / risk, 2) if risk > 0 else 0,
            }

        # Support/Resistance
        if len(klines) >= 2:
            indicators["levels"] = self._calc_levels(closes, highs, lows)

        # Volume ratio
        if len(volumes) >= 20:
            avg_vol = sum(volumes[-20:]) / 20
            if avg_vol > 0:
                indicators["volume_ratio"] = round(volumes[-1] / avg_vol, 2)

        # Price position (0-100 in 20-bar range)
        if len(closes) >= 20:
            h20 = max(highs[-20:])
            l20 = min(lows[-20:])
            if h20 > l20:
                indicators["price_position"] = round((price - l20) / (h20 - l20) * 100, 1)

        return indicators

    # ── Indicator Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _calc_rsi(closes: list[float], period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0.0 for d in deltas]
        losses = [-d if d < 0 else 0.0 for d in deltas]
        if len(gains) < period:
            return 50.0
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def _ema_series(data: list[float], period: int) -> list[float | None]:
        """EMA with SMA seed. Returns list of floats (None for warmup)."""
        n = len(data)
        out: list[float | None] = [None] * n
        if n < period:
            return out
        k = 2.0 / (period + 1)
        out[period - 1] = sum(data[:period]) / period
        for i in range(period, n):
            prev = out[i - 1]
            if prev is None:
                break
            out[i] = (data[i] - prev) * k + prev
        return out

    def _calc_macd(self, closes: list[float]) -> dict[str, Any]:
        n = len(closes)
        ema12 = self._ema_series(closes, 12)
        ema26 = self._ema_series(closes, 26)
        if n < 26 or ema12[-1] is None or ema26[-1] is None:
            return {"value": 0.0, "signal_line": 0.0, "histogram": 0.0, "signal": "neutral"}

        macd_sub: list[float] = []
        for i in range(25, n):
            v12, v26 = ema12[i], ema26[i]
            if v12 is not None and v26 is not None:
                macd_sub.append(v12 - v26)

        if not macd_sub:
            return {"value": 0.0, "signal_line": 0.0, "histogram": 0.0, "signal": "neutral"}

        sig_series = self._ema_series(macd_sub, 9)
        last_macd = macd_sub[-1]
        last_sig = sig_series[-1] if sig_series[-1] is not None else last_macd
        hist = last_macd - last_sig

        if last_macd > last_sig and hist > 0:
            signal = "bullish"
        elif last_macd < last_sig and hist < 0:
            signal = "bearish"
        else:
            signal = "neutral"

        return {
            "value": round(last_macd, 6),
            "signal_line": round(last_sig, 6),
            "histogram": round(hist, 6),
            "signal": signal,
        }

    @staticmethod
    def _calc_atr(klines: list[dict[str, Any]], period: int = 14) -> float:
        """Wilder's ATR."""
        trs: list[float] = []
        for i, k in enumerate(klines):
            h = float(k.get("high", 0))
            l = float(k.get("low", 0))
            if h <= 0 or l <= 0:
                trs.append(0.0)
                continue
            if i == 0:
                trs.append(h - l)
            else:
                pc = float(klines[i - 1].get("close", 0))
                trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        if len(trs) < period:
            return 0.0
        atr = sum(trs[:period]) / period
        for i in range(period, len(trs)):
            atr = (atr * (period - 1) + trs[i]) / period
        return atr

    @staticmethod
    def _calc_bollinger(
        closes: list[float], period: int = 20, std_dev: float = 2.0
    ) -> dict[str, float] | None:
        if len(closes) < period:
            return None
        recent = closes[-period:]
        mid = sum(recent) / period
        variance = sum((x - mid) ** 2 for x in recent) / period
        std = variance ** 0.5
        return {
            "upper": round(mid + std_dev * std, 6),
            "middle": round(mid, 6),
            "lower": round(mid - std_dev * std, 6),
            "width": round((std_dev * std * 2) / mid * 100, 2) if mid > 0 else 0,
        }

    @staticmethod
    def _calc_levels(
        closes: list[float], highs: list[float], lows: list[float]
    ) -> dict[str, float]:
        """Pivot + swing support/resistance."""
        price = closes[-1]
        if len(closes) >= 2:
            ph, pl, pc = highs[-2], lows[-2], closes[-2]
            pivot = (ph + pl + pc) / 3
            r1 = 2 * pivot - pl
            s1 = 2 * pivot - ph
        else:
            pivot = price
            r1 = price * 1.02
            s1 = price * 0.98

        h20 = max(highs[-20:]) if len(highs) >= 20 else max(highs)
        l20 = min(lows[-20:]) if len(lows) >= 20 else min(lows)

        resistance = round((r1 + h20) / 2, 6)
        support = round((s1 + l20) / 2, 6)

        return {
            "support": support,
            "resistance": resistance,
            "pivot": round(pivot, 6),
            "swing_high": round(h20, 6),
            "swing_low": round(l20, 6),
        }

    @staticmethod
    def _safe_float(val: Any, default: float = 0.0) -> float:
        try:
            return float(val)
        except (TypeError, ValueError):
            return default


# ── Module-level singleton ─────────────────────────────────────────────────

_collector: MarketDataCollector | None = None


def get_market_data_collector() -> MarketDataCollector:
    """Return the module-level MarketDataCollector singleton."""
    global _collector
    if _collector is None:
        _collector = MarketDataCollector()
    return _collector
