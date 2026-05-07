"""
UF Stock Assistant — Fast Analysis Service

Single-call AI analysis with multi-dimensional objective scoring.
Adapted from QuantDinger: uses UF's LlmService, MarketDataCollector,
AnalysisMemoryService, and AICalibrationService.

Simplifications vs QuantDinger:
- No news/geopolitical sentiment (UF has no news source)
- No Polymarket integration
- No crypto derivatives factors (funding rate, OI, etc.)
- No multi-timeframe consensus (single timeframe)
- UF uses LlmService.chat() instead of LLMService wrapper
"""

from __future__ import annotations

import json
import time
from typing import Any

from app.core.logging import get_logger
from app.strategies.market_data_collector import get_market_data_collector

logger = get_logger("app.strategies.fast_analysis")


class FastAnalysisService:
    """
    Fast single-call analysis service.

    Architecture:
    1. Data collection — MarketDataCollector
    2. Objective scoring — technical(35%) + fundamental(25%) + macro(40%)
    3. LLM call — structured analysis prompt
    4. Memory storage — AnalysisMemoryService
    5. Confidence calibration — AICalibrationService
    """

    def analyze(
        self,
        symbol: str,
        market_type: str = "stock",
        timeframe: str = "1D",
        language: str = "zh-CN",
    ) -> dict[str, Any]:
        """
        Run fast single-call analysis.

        Returns:
            Complete analysis result with decision, scores, and LLM text.
        """
        start = time.time()
        result: dict[str, Any] = {
            "symbol": symbol,
            "market_type": market_type,
            "timeframe": timeframe,
            "language": language,
            "analysis_time_ms": 0,
            "error": None,
        }

        try:
            # 1. Collect data
            logger.info("fast_analysis_start", symbol=symbol, market_type=market_type)
            collector = get_market_data_collector()
            data = collector.collect_all(symbol, market_type, timeframe)
            result["data_meta"] = data.get("_meta", {})

            # 2. Objective scoring
            price_data = data.get("price") or {}
            current_price = float(price_data.get("price", 0) or 0)
            if current_price <= 0:
                kline = data.get("kline") or []
                if kline:
                    current_price = float(kline[-1].get("close", 0))

            objective = self._calculate_objective_score(data, current_price)
            overall_score = objective["overall_score"]
            decision = self._score_to_decision(overall_score)

            result["objective_score"] = objective
            result["overall_score"] = overall_score
            result["decision"] = decision

            # 3. LLM analysis
            try:
                llm_result = self._call_llm(data, current_price, objective, language)
                result.update(llm_result)
            except Exception as exc:
                logger.warning("llm_call_failed", error=str(exc))
                result["summary"] = f"Objective score: {overall_score:.1f} → {decision}"
                result["analysis"] = {}
                result["key_reasons"] = []
                result["risks"] = []

            # 4. Calibrate confidence
            try:
                result["confidence"] = self._calibrate_confidence(
                    overall_score, result.get("confidence", 60), market_type
                )
            except Exception:
                pass

            # 5. Store in memory
            try:
                self._store_memory(symbol, market_type, result, current_price)
            except Exception as exc:
                logger.warning("memory_store_failed", error=str(exc))

            result["analysis_time_ms"] = int((time.time() - start) * 1000)
            logger.info(
                "fast_analysis_done",
                symbol=symbol,
                decision=decision,
                score=overall_score,
                duration_ms=result["analysis_time_ms"],
            )

        except Exception as exc:
            logger.error("fast_analysis_failed", symbol=symbol, error=str(exc), exc_info=True)
            result["error"] = str(exc)
            result["analysis_time_ms"] = int((time.time() - start) * 1000)

        return result

    # ── Objective Scoring ───────────────────────────────────────────────────

    def _calculate_objective_score(
        self, data: dict[str, Any], current_price: float
    ) -> dict[str, float]:
        """
        Multi-dimensional objective scoring: -100 to +100.

        Weights (re-normalized when modules are missing):
        - technical: 35%
        - fundamental: 25%
        - macro: 40% (includes sentiment proxy from volatility)
        """
        indicators = data.get("indicators") or {}
        fundamental = data.get("fundamental") or {}

        technical_score = self._score_technical(indicators, data.get("price") or {})
        fundamental_score = self._score_fundamental(fundamental)
        macro_score = self._score_macro(indicators)

        # Re-weight: only use present modules
        weights = {"technical": 0.35, "fundamental": 0.25, "macro": 0.40}
        present = {
            "technical": bool(indicators),
            "fundamental": bool(fundamental),
            "macro": True,  # always available from indicators
        }
        total_w = sum(w for k, w in weights.items() if present.get(k))
        if total_w <= 0:
            overall = technical_score
        else:
            overall = (
                (technical_score * weights["technical"] if present["technical"] else 0)
                + (fundamental_score * weights["fundamental"] if present["fundamental"] else 0)
                + (macro_score * weights["macro"] if present["macro"] else 0)
            ) / total_w

        return {
            "technical_score": round(technical_score, 2),
            "fundamental_score": round(fundamental_score, 2),
            "macro_score": round(macro_score, 2),
            "overall_score": round(overall, 2),
        }

    @staticmethod
    def _score_technical(indicators: dict[str, Any], price_data: dict[str, Any]) -> float:
        """Score technical indicators: -100 to +100."""
        score = 0.0
        weight_sum = 0.0

        # RSI (weight 0.30)
        rsi_data = indicators.get("rsi") or {}
        rsi = rsi_data.get("value", 50)
        if rsi > 0:
            if rsi > 70:
                rsi_score = -50
            elif rsi > 60:
                rsi_score = -30
            elif rsi < 30:
                rsi_score = +50
            elif rsi < 40:
                rsi_score = +30
            else:
                rsi_score = (50 - rsi) * 0.6
            score += rsi_score * 0.30
            weight_sum += 0.30

        # MACD (weight 0.25)
        macd_data = indicators.get("macd") or {}
        macd_signal = macd_data.get("signal", "neutral")
        if macd_signal == "bullish":
            score += 40 * 0.25
        elif macd_signal == "bearish":
            score += -40 * 0.25
        weight_sum += 0.25

        # MA trend (weight 0.25)
        ma_data = indicators.get("moving_averages") or {}
        ma_trend = ma_data.get("trend", "sideways")
        if "strong_uptrend" in ma_trend:
            score += 40 * 0.25
        elif "uptrend" in ma_trend:
            score += 25 * 0.25
        elif "strong_downtrend" in ma_trend:
            score += -40 * 0.25
        elif "downtrend" in ma_trend:
            score += -25 * 0.25
        weight_sum += 0.25

        # 24h change (weight 0.20)
        change = price_data.get("changePercent", 0) or 0
        if change > 10:
            change_score = -20
        elif change > 5:
            change_score = -10
        elif change < -10:
            change_score = +20
        elif change < -5:
            change_score = +10
        else:
            change_score = change * 2
        score += change_score * 0.20
        weight_sum += 0.20

        return score / weight_sum if weight_sum > 0 else 0.0

    @staticmethod
    def _score_fundamental(fundamental: dict[str, Any]) -> float:
        """Score fundamental data: -100 to +100. Simplified for A-stock."""
        if not fundamental:
            return 0.0

        score = 0.0
        count = 0

        # PE ratio: low PE = undervalued (bullish)
        pe = fundamental.get("pe_ratio")
        if pe is not None and pe > 0:
            if pe < 15:
                score += 30
            elif pe < 25:
                score += 10
            elif pe > 60:
                score += -30
            elif pe > 40:
                score += -10
            count += 1

        # PB ratio: low PB = undervalued
        pb = fundamental.get("pb_ratio")
        if pb is not None and pb > 0:
            if pb < 1.0:
                score += 25
            elif pb < 2.0:
                score += 10
            elif pb > 5.0:
                score += -25
            elif pb > 3.0:
                score += -10
            count += 1

        # Market cap (stability signal)
        mc = fundamental.get("market_cap")
        if mc is not None and mc > 0:
            # Large cap = more stable, slight positive
            if mc > 100_000_000_000:  # >100B
                score += 5
            count += 1

        return score / max(count, 1) if count > 0 else 0.0

    @staticmethod
    def _score_macro(indicators: dict[str, Any]) -> float:
        """Score macro/volatility from indicators: -100 to +100."""
        score = 0.0

        # Volatility: high volatility = risk-off (bearish)
        vol = indicators.get("volatility") or {}
        vol_level = vol.get("level", "medium")
        if vol_level == "high":
            score += -25
        elif vol_level == "low":
            score += 10

        # Volume ratio: high volume with price drop = bearish
        vr = indicators.get("volume_ratio", 1.0)
        if vr > 2.0:
            # High volume — direction depends on price action
            trend = indicators.get("trend", "sideways")
            if "downtrend" in trend:
                score += -15
            elif "uptrend" in trend:
                score += 15

        # Price position: near top = overbought risk
        pp = indicators.get("price_position", 50)
        if pp > 80:
            score += -10
        elif pp < 20:
            score += 10

        return score

    @staticmethod
    def _score_to_decision(score: float) -> str:
        """Convert overall score to BUY/SELL/HOLD decision."""
        if score >= 20:
            return "BUY"
        if score <= -20:
            return "SELL"
        return "HOLD"

    # ── LLM Integration ─────────────────────────────────────────────────────

    def _call_llm(
        self,
        data: dict[str, Any],
        current_price: float,
        objective: dict[str, float],
        language: str,
    ) -> dict[str, Any]:
        """Call LLM for structured analysis. Returns parsed result dict."""
        from app.core.llm_adapter import LlmService

        llm = LlmService.from_env()
        symbol = data.get("symbol", "")
        indicators = data.get("indicators") or {}
        fundamental = data.get("fundamental") or {}

        system_prompt = self._build_system_prompt(language)
        user_prompt = self._build_user_prompt(
            symbol, data, indicators, fundamental, current_price, objective
        )

        response_text = llm.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=2000,
        )

        return self._parse_llm_response(response_text, current_price, objective)

    def _build_system_prompt(self, language: str) -> str:
        is_zh = language.startswith("zh")
        if is_zh:
            return """你是一位资深金融分析师，具有20年以上经验。你保守、客观，分析必须基于数据而非猜测。

关键决策规则：
1. 综合考虑技术指标、基本面、宏观环境
2. BUY: RSI<40, MACD看多, 上升趋势，或有强基本面催化剂
3. SELL: RSI>60, MACD看空, 下降趋势，或重大负面事件
4. HOLD: 信号不明确时
5. 置信度>=60才给出BUY/SELL

仅输出JSON，不要包含其他内容：
{
  "decision": "BUY" | "SELL" | "HOLD",
  "confidence": 0-100,
  "summary": "2-3句摘要",
  "analysis": {"technical": "...", "fundamental": "...", "macro": "..."},
  "entry_price": 数字,
  "stop_loss": 数字,
  "take_profit": 数字,
  "key_reasons": ["原因1", "原因2", "原因3"],
  "risks": ["风险1", "风险2"]
}"""
        return """You are a senior financial analyst with 20+ years of experience. Be conservative and objective.

Decision rules:
1. Consider technical, fundamental, and macro factors
2. BUY: RSI<40, bullish MACD, uptrend, or strong catalyst
3. SELL: RSI>60, bearish MACD, downtrend, or negative event
4. HOLD: only when signals are truly mixed
5. Confidence >= 60 required for BUY/SELL

Output ONLY valid JSON:
{
  "decision": "BUY" | "SELL" | "HOLD",
  "confidence": 0-100,
  "summary": "2-3 sentence summary",
  "analysis": {"technical": "...", "fundamental": "...", "macro": "..."},
  "entry_price": number,
  "stop_loss": number,
  "take_profit": number,
  "key_reasons": ["reason1", "reason2", "reason3"],
  "risks": ["risk1", "risk2"]
}"""

    def _build_user_prompt(
        self,
        symbol: str,
        data: dict[str, Any],
        indicators: dict[str, Any],
        fundamental: dict[str, Any],
        current_price: float,
        objective: dict[str, float],
    ) -> str:
        rsi_data = indicators.get("rsi") or {}
        macd_data = indicators.get("macd") or {}
        ma_data = indicators.get("moving_averages") or {}
        vol_data = indicators.get("volatility") or {}
        levels = indicators.get("levels") or {}
        trading = indicators.get("trading_levels") or {}

        fund_lines = ""
        if fundamental:
            fund_lines = "\n".join(
                f"- {k}: {v}" for k, v in fundamental.items() if v is not None
            )

        return f"""Analyze {symbol}.

PRICE: {current_price}
INDICATORS:
- RSI(14): {rsi_data.get('value', 'N/A')} ({rsi_data.get('signal', 'N/A')})
- MACD: {macd_data.get('signal', 'N/A')}
- MA Trend: {ma_data.get('trend', 'N/A')}
- Volatility: {vol_data.get('level', 'N/A')} ({vol_data.get('pct', 0)}%)
- Support: {levels.get('support', 'N/A')}
- Resistance: {levels.get('resistance', 'N/A')}
- Stop Loss: {trading.get('stop_loss', 'N/A')}
- Take Profit: {trading.get('take_profit', 'N/A')}
- Volume Ratio: {indicators.get('volume_ratio', 'N/A')}
- Price Position (20d): {indicators.get('price_position', 'N/A')}%

OBJECTIVE SCORES:
- Technical: {objective['technical_score']}
- Fundamental: {objective['fundamental_score']}
- Macro: {objective['macro_score']}
- Overall: {objective['overall_score']}

FUNDAMENTALS:
{fund_lines or 'N/A'}

Provide analysis. Entry/SL/TP within 10% of {current_price}."""

    @staticmethod
    def _parse_llm_response(
        text: str, current_price: float, objective: dict[str, float]
    ) -> dict[str, Any]:
        """Parse LLM JSON response with fallback."""
        try:
            # Extract JSON from response
            text = text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            parsed = json.loads(text)

            result: dict[str, Any] = {
                "decision": parsed.get("decision", "HOLD"),
                "confidence": int(parsed.get("confidence", 50)),
                "summary": parsed.get("summary", ""),
                "analysis": parsed.get("analysis", {}),
                "key_reasons": parsed.get("key_reasons", []),
                "risks": parsed.get("risks", []),
            }

            # Price fields with bounds checking
            for field in ("entry_price", "stop_loss", "take_profit"):
                val = parsed.get(field)
                if val is not None:
                    try:
                        fval = float(val)
                        if current_price > 0 and abs(fval - current_price) / current_price > 0.15:
                            fval = current_price  # reject outlier
                        result[field] = round(fval, 6)
                    except (TypeError, ValueError):
                        pass

            return result

        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("llm_parse_failed", error=str(exc))
            return {
                "decision": objective.get("overall_score", 0) >= 20
                and "BUY"
                or (objective.get("overall_score", 0) <= -20 and "SELL")
                or "HOLD",
                "confidence": 50,
                "summary": f"LLM parse failed. Objective score: {objective.get('overall_score', 0):.1f}",
                "analysis": {},
                "key_reasons": [],
                "risks": [],
            }

    # ── Confidence Calibration ──────────────────────────────────────────────

    @staticmethod
    def _calibrate_confidence(
        overall_score: float, llm_confidence: int, market_type: str
    ) -> int:
        """Calibrate confidence using objective score as anchor."""
        # Objective-based confidence
        abs_score = abs(overall_score)
        if abs_score >= 50:
            obj_confidence = 80
        elif abs_score >= 30:
            obj_confidence = 65
        elif abs_score >= 15:
            obj_confidence = 50
        else:
            obj_confidence = 35

        # Blend: 60% objective + 40% LLM
        calibrated = int(obj_confidence * 0.6 + llm_confidence * 0.4)
        return max(10, min(95, calibrated))

    # ── Memory Storage ──────────────────────────────────────────────────────

    @staticmethod
    def _store_memory(
        symbol: str, market_type: str, result: dict[str, Any], current_price: float
    ) -> None:
        """Store analysis result in AnalysisMemoryService."""
        try:
            from app.services.analysis_memory import get_analysis_memory

            memory = get_analysis_memory()
            memory.store(
                symbol=symbol,
                market=market_type,
                decision=result.get("decision", "HOLD"),
                price=current_price,
                confidence=result.get("confidence", 50),
                technical_score=result.get("objective_score", {}).get("technical_score", 0),
                fundamental_score=result.get("objective_score", {}).get("fundamental_score", 0),
                sentiment_score=result.get("objective_score", {}).get("macro_score", 0),
                summary=result.get("summary", ""),
            )
        except Exception as exc:
            logger.warning("memory_store_error", error=str(exc))


# ── Module-level singleton ─────────────────────────────────────────────────

_service: FastAnalysisService | None = None


def get_fast_analysis_service() -> FastAnalysisService:
    """Return the module-level FastAnalysisService singleton."""
    global _service
    if _service is None:
        _service = FastAnalysisService()
    return _service
