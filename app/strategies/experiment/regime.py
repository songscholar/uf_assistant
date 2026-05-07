"""
UF Stock Assistant — Market Regime Detection

Rule-based market regime detection. Pure Python, no pandas/numpy required.
Adapted from QuantDinger: works with both DataFrame and list[dict] input.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RegimeProfile:
    key: str
    label: str
    strategy_families: list[str]


class MarketRegimeService:
    """Rule-based market regime detection."""

    REGIME_VERSION = "market-regime-v1"

    REGIME_PROFILES: dict[str, RegimeProfile] = {
        "bull_trend": RegimeProfile(
            key="bull_trend",
            label="Bull Trend",
            strategy_families=["trend_following", "breakout", "pullback_continuation"],
        ),
        "bear_trend": RegimeProfile(
            key="bear_trend",
            label="Bear Trend",
            strategy_families=["trend_following", "breakdown", "short_pullback"],
        ),
        "range_compression": RegimeProfile(
            key="range_compression",
            label="Range Compression",
            strategy_families=["mean_reversion", "bollinger_reversion", "range_breakout_watch"],
        ),
        "high_volatility": RegimeProfile(
            key="high_volatility",
            label="High Volatility",
            strategy_families=["volatility_breakout", "reduced_risk_trend", "event_drive"],
        ),
        "transition": RegimeProfile(
            key="transition",
            label="Transition",
            strategy_families=["hybrid", "wait_and_see", "confirmation_breakout"],
        ),
    }

    def detect(
        self,
        klines: list[dict[str, Any]],
        *,
        symbol: str = "",
        market: str = "",
        timeframe: str = "",
    ) -> dict[str, Any]:
        """
        Detect market regime from kline data.

        Args:
            klines: List of OHLCV dicts (with keys: open, high, low, close, volume).
            symbol: Symbol name for context.
            market: Market type for context.
            timeframe: Timeframe for context.

        Returns:
            Regime detection result dict.
        """
        frame = self._normalize_klines(klines)
        if len(frame) < 30:
            raise ValueError("At least 30 candles are required for regime detection")

        features = self._extract_features(frame)
        regime_key, confidence = self._classify(features)
        profile = self.REGIME_PROFILES[regime_key]
        segments = self._build_segments(frame, max_segments=4)

        return {
            "version": self.REGIME_VERSION,
            "symbol": symbol,
            "market": market,
            "timeframe": timeframe,
            "regime": profile.key,
            "label": profile.label,
            "confidence": round(confidence, 2),
            "features": features,
            "strategyFamilies": profile.strategy_families,
            "segments": segments,
        }

    def _normalize_klines(self, klines: list[dict[str, Any]]) -> list[dict[str, float]]:
        """Normalize klines to consistent float format, dropping incomplete bars."""
        normalized: list[dict[str, float]] = []
        for k in klines:
            try:
                o = float(k.get("open", 0))
                h = float(k.get("high", 0))
                l = float(k.get("low", 0))
                c = float(k.get("close", 0))
                if o <= 0 or h <= 0 or l <= 0 or c <= 0:
                    continue
                normalized.append({
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": float(k.get("volume", 0)),
                })
            except (TypeError, ValueError):
                continue
        return normalized

    def _extract_features(self, klines: list[dict[str, float]]) -> dict[str, float]:
        """Extract regime features from klines using pure Python."""
        closes = [k["close"] for k in klines]
        highs = [k["high"] for k in klines]
        lows = [k["low"] for k in klines]
        volumes = [k["volume"] for k in klines]
        n = len(closes)

        # Price change %
        price_change_pct = ((closes[-1] / max(closes[0], 1e-9)) - 1.0) * 100.0

        # EMA gap %
        ema_fast = self._ema(closes, 10)
        ema_slow = self._ema(closes, 30)
        ema_gap_pct = abs(ema_fast - ema_slow) / max(closes[-1], 1e-9) * 100.0

        # Realized volatility (30-day)
        if n >= 30:
            returns = [(closes[i] / max(closes[i - 1], 1e-9)) - 1.0 for i in range(n - 30, n)]
            mean_ret = sum(returns) / len(returns)
            var = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
            realized_vol_pct = math.sqrt(var) * math.sqrt(30) * 100.0
        else:
            realized_vol_pct = 0.0

        # ATR %
        atr = self._calc_atr(klines, 14)
        atr_pct = (atr / max(closes[-1], 1e-9)) * 100.0

        # Directional efficiency (30-bar)
        if n >= 30:
            net_move = abs(closes[-1] - closes[-30])
            sum_moves = sum(abs(closes[i] - closes[i - 1]) for i in range(n - 29, n))
            directional_efficiency = net_move / max(sum_moves, 1e-9)
        else:
            directional_efficiency = 0.0

        # Volume ratio
        if n >= 20:
            avg_vol = sum(volumes[-20:]) / 20
            volume_ratio = volumes[-1] / max(avg_vol, 1e-9)
        else:
            volume_ratio = 1.0

        return {
            "priceChangePct": round(price_change_pct, 4),
            "emaGapPct": round(ema_gap_pct, 4),
            "realizedVolPct": round(realized_vol_pct, 4),
            "atrPct": round(atr_pct, 4),
            "directionalEfficiency": round(directional_efficiency, 4),
            "volumeRatio": round(volume_ratio, 4),
        }

    def _classify(self, features: dict[str, float]) -> tuple[str, float]:
        """Classify regime from features. Returns (regime_key, confidence)."""
        change = features["priceChangePct"]
        gap = features["emaGapPct"]
        vol = features["realizedVolPct"]
        atr = features["atrPct"]
        efficiency = features["directionalEfficiency"]

        if gap >= 1.0 and efficiency >= 0.55 and change > 1.0:
            return "bull_trend", min(0.99, 0.55 + gap * 0.12 + efficiency * 0.3)
        if gap >= 1.0 and efficiency >= 0.55 and change < -1.0:
            return "bear_trend", min(0.99, 0.55 + gap * 0.12 + efficiency * 0.3)
        if vol >= 4.5 or atr >= 3.5:
            return "high_volatility", min(0.99, 0.5 + max(vol / 10.0, atr / 7.0))
        if gap <= 0.45 and efficiency <= 0.38 and atr <= 2.0:
            return "range_compression", min(
                0.99, 0.52 + (0.45 - gap) * 0.35 + (0.38 - efficiency) * 0.25
            )
        return "transition", 0.55

    def _build_segments(
        self, klines: list[dict[str, float]], *, max_segments: int = 4
    ) -> list[dict[str, Any]]:
        """Build regime segments for sub-periods."""
        segment_size = max(30, len(klines) // max_segments)
        segments: list[dict[str, Any]] = []
        for start in range(0, len(klines), segment_size):
            subset = klines[start : start + segment_size]
            if len(subset) < 20:
                continue
            features = self._extract_features(subset)
            regime_key, confidence = self._classify(features)
            profile = self.REGIME_PROFILES[regime_key]
            segments.append({
                "regime": regime_key,
                "label": profile.label,
                "confidence": round(confidence, 2),
                "barIndex": start,
                "barCount": len(subset),
            })
        return segments

    @staticmethod
    def _ema(data: list[float], period: int) -> float:
        """Calculate EMA over the full series, return the last value."""
        if not data:
            return 0.0
        if len(data) < period:
            return sum(data) / len(data)
        k = 2.0 / (period + 1)
        ema = sum(data[:period]) / period
        for val in data[period:]:
            ema = (val - ema) * k + ema
        return ema

    @staticmethod
    def _calc_atr(klines: list[dict[str, float]], period: int = 14) -> float:
        """Wilder's ATR."""
        trs: list[float] = []
        for i, k in enumerate(klines):
            h, l = k["high"], k["low"]
            if h <= 0 or l <= 0:
                trs.append(0.0)
                continue
            if i == 0:
                trs.append(h - l)
            else:
                pc = klines[i - 1]["close"]
                trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        if len(trs) < period:
            return sum(trs) / max(len(trs), 1)
        atr = sum(trs[:period]) / period
        for i in range(period, len(trs)):
            atr = (atr * (period - 1) + trs[i]) / period
        return atr
