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
        user_id: str | None = None,
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
            result["overall_rating"] = self._score_to_rating(overall_score)
            result["score_breakdown"] = objective.get("score_breakdown", {})

            # 3. Build human-readable report (always available as baseline)
            human_report = self._build_human_report(data, objective, current_price, decision)
            result["metrics_snapshot"] = human_report["metrics_snapshot"]
            result["trading_levels"] = human_report["trading_levels"]

            # 4. LLM analysis (enhances the baseline report)
            try:
                llm_result = self._call_llm(data, current_price, objective, language)
                result.update(llm_result)
            except Exception as exc:
                logger.warning("llm_call_failed", error=str(exc))
                # Use human report as fallback
                result["summary"] = human_report["summary"]
                result["analysis"] = {}
                result["key_reasons"] = human_report["key_reasons"]
                result["risks"] = human_report["risks"]

            # 5. Calibrate confidence
            try:
                result["confidence"] = self._calibrate_confidence(
                    overall_score,
                    result.get("confidence", 0),
                    market_type,
                    data.get("_meta"),
                )
            except Exception:
                pass

            # 6. Store in memory
            try:
                self._store_memory(symbol, market_type, result, current_price, user_id=user_id)
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
    ) -> dict[str, Any]:
        """
        Multi-dimensional objective scoring with human-readable details.
        Score range: -100 to +100 per dimension.
        """
        indicators = data.get("indicators") or {}
        fundamental = data.get("fundamental") or {}
        price_data = data.get("price") or {}

        technical = self._score_technical(indicators, price_data)
        fundamental_r = self._score_fundamental(fundamental)
        macro = self._score_macro(indicators)

        # Re-weight: only use present modules
        weights = {"technical": 0.35, "fundamental": 0.25, "macro": 0.40}
        present = {
            "technical": bool(indicators),
            "fundamental": bool(fundamental),
            "macro": True,
        }
        total_w = sum(w for k, w in weights.items() if present.get(k))
        if total_w <= 0:
            overall = technical["score"]
        else:
            overall = (
                (technical["score"] * weights["technical"] if present["technical"] else 0)
                + (fundamental_r["score"] * weights["fundamental"] if present["fundamental"] else 0)
                + (macro["score"] * weights["macro"] if present["macro"] else 0)
            ) / total_w

        return {
            "technical_score": round(technical["score"], 2),
            "fundamental_score": round(fundamental_r["score"], 2),
            "macro_score": round(macro["score"], 2),
            "overall_score": round(overall, 2),
            "score_breakdown": {
                "technical": {
                    "score": round(technical["score"], 2),
                    "weight": 0.35,
                    "details": technical["details"],
                },
                "fundamental": {
                    "score": round(fundamental_r["score"], 2),
                    "weight": 0.25,
                    "details": fundamental_r["details"],
                },
                "macro": {
                    "score": round(macro["score"], 2),
                    "weight": 0.40,
                    "details": macro["details"],
                },
            },
        }

    @staticmethod
    def _score_technical(indicators: dict[str, Any], price_data: dict[str, Any]) -> dict[str, Any]:
        """Score technical indicators. Returns {score, details}."""
        score = 0.0
        weight_sum = 0.0
        details: list[str] = []

        # Guard: no indicator data at all
        if not indicators:
            details.append("无技术指标数据（可能为非标准代码或数据暂不可用）")
            return {"score": 0.0, "details": details}

        # RSI (weight 0.30)
        rsi_data = indicators.get("rsi") or {}
        rsi = rsi_data.get("value", 50)
        if rsi > 0:
            if rsi > 70:
                rsi_score = -50
                details.append(f"RSI {rsi:.1f} 处于超买区间（>70），短期回调风险大，偏空 -50分")
            elif rsi > 60:
                rsi_score = -30
                details.append(f"RSI {rsi:.1f} 偏高（>60），上涨动能减弱，偏空 -30分")
            elif rsi < 30:
                rsi_score = +50
                details.append(f"RSI {rsi:.1f} 处于超卖区间（<30），可能出现反弹，偏多 +50分")
            elif rsi < 40:
                rsi_score = +30
                details.append(f"RSI {rsi:.1f} 偏低（<40），下跌动能减弱，偏多 +30分")
            else:
                rsi_score = (50 - rsi) * 0.6
                bias = "轻微偏多" if rsi < 50 else "轻微偏空"
                details.append(f"RSI {rsi:.1f} 中性区间，{bias} {rsi_score:+.1f}分")
            score += rsi_score * 0.30
            weight_sum += 0.30

        # MACD (weight 0.25)
        macd_data = indicators.get("macd") or {}
        macd_signal = macd_data.get("signal", "neutral")
        macd_hist = macd_data.get("histogram", 0)
        if macd_signal == "bullish":
            score += 40 * 0.25
            details.append(f"MACD 金叉/看多信号（柱状图 {macd_hist:+.4f}），偏多 +40分")
        elif macd_signal == "bearish":
            score += -40 * 0.25
            details.append(f"MACD 死叉/看空信号（柱状图 {macd_hist:+.4f}），偏空 -40分")
        else:
            details.append(f"MACD 中性（柱状图 {macd_hist:+.4f}），趋势不明确")
        weight_sum += 0.25

        # MA trend (weight 0.25)
        ma_data = indicators.get("moving_averages") or {}
        ma_trend = ma_data.get("trend", "sideways")
        ma5 = ma_data.get("ma5")
        ma20 = ma_data.get("ma20")
        if "strong_uptrend" in ma_trend:
            score += 40 * 0.25
            details.append(f"均线多头排列（MA5 {ma5:.2f} > MA20 {ma20:.2f}），强势上涨，偏多 +40分")
        elif "uptrend" in ma_trend:
            score += 25 * 0.25
            details.append(f"均线呈上升趋势（MA5 {ma5:.2f} 在 MA20 {ma20:.2f} 上方），偏多 +25分")
        elif "strong_downtrend" in ma_trend:
            score += -40 * 0.25
            details.append(f"均线空头排列（MA5 {ma5:.2f} < MA20 {ma20:.2f}），强势下跌，偏空 -40分")
        elif "downtrend" in ma_trend:
            score += -25 * 0.25
            details.append(f"均线呈下降趋势（MA5 {ma5:.2f} 在 MA20 {ma20:.2f} 下方），偏空 -25分")
        else:
            details.append(f"均线纠缠（MA5 {ma5:.2f} / MA20 {ma20:.2f}），趋势不明")
        weight_sum += 0.25

        # 24h change (weight 0.20)
        change = price_data.get("changePercent", 0) or 0
        if change > 10:
            change_score = -20
            details.append(f"单日涨幅 {change:.2f}% 过大（>10%），追高风险高，偏空 -20分")
        elif change > 5:
            change_score = -10
            details.append(f"单日涨幅 {change:.2f}% 较大（>5%），短期过热，偏空 -10分")
        elif change < -10:
            change_score = +20
            details.append(f"单日跌幅 {change:.2f}% 过大（<-10%），恐慌抛售可能超调，偏多 +20分")
        elif change < -5:
            change_score = +10
            details.append(f"单日跌幅 {change:.2f}% 较大（<-5%），可能出现反弹，偏多 +10分")
        else:
            change_score = change * 2
            bias = "偏多" if change > 0 else "偏空" if change < 0 else "中性"
            details.append(f"单日涨跌 {change:+.2f}%，波动温和，{bias} {change_score:+.1f}分")
        score += change_score * 0.20
        weight_sum += 0.20

        final = score / weight_sum if weight_sum > 0 else 0.0
        return {"score": round(final, 2), "details": details}

    @staticmethod
    def _score_fundamental(fundamental: dict[str, Any]) -> dict[str, Any]:
        """Score fundamental data. Returns {score, details}."""
        if not fundamental:
            return {"score": 0.0, "details": ["无基本面数据"]}

        score = 0.0
        count = 0
        details: list[str] = []

        pe = fundamental.get("pe_ratio")
        if pe is not None and pe > 0:
            if pe < 15:
                score += 30
                details.append(f"市盈率 {pe:.1f} 较低（<15），估值有吸引力，+30分")
            elif pe < 25:
                score += 10
                details.append(f"市盈率 {pe:.1f} 合理（15-25），估值适中，+10分")
            elif pe > 60:
                score += -30
                details.append(f"市盈率 {pe:.1f} 过高（>60），估值泡沫风险，-30分")
            elif pe > 40:
                score += -10
                details.append(f"市盈率 {pe:.1f} 偏高（40-60），估值偏贵，-10分")
            else:
                details.append(f"市盈率 {pe:.1f} 处于正常区间（25-40），估值中性")
            count += 1

        pb = fundamental.get("pb_ratio")
        if pb is not None and pb > 0:
            if pb < 1.0:
                score += 25
                details.append(f"市净率 {pb:.2f} 较低（<1），可能破净，+25分")
            elif pb < 2.0:
                score += 10
                details.append(f"市净率 {pb:.2f} 合理（1-2），资产估值适中，+10分")
            elif pb > 5.0:
                score += -25
                details.append(f"市净率 {pb:.2f} 过高（>5），资产溢价严重，-25分")
            elif pb > 3.0:
                score += -10
                details.append(f"市净率 {pb:.2f} 偏高（3-5），资产偏贵，-10分")
            else:
                details.append(f"市净率 {pb:.2f} 处于正常区间（2-3），资产估值中性")
            count += 1

        mc = fundamental.get("market_cap")
        if mc is not None and mc > 0:
            mc_yi = mc / 100_000_000
            if mc > 100_000_000_000:
                score += 5
                details.append(f"总市值 {mc_yi:.0f}亿，大盘股，稳定性较好，+5分")
            else:
                details.append(f"总市值 {mc_yi:.0f}亿，中小盘股，波动可能较大")
            count += 1

        turnover = fundamental.get("turnover_rate")
        if turnover is not None and turnover > 0:
            if turnover > 10:
                details.append(f"换手率 {turnover:.2f}% 极高，交易活跃但波动大")
            elif turnover > 5:
                details.append(f"换手率 {turnover:.2f}% 较高，市场关注度好")
            elif turnover < 1:
                details.append(f"换手率 {turnover:.2f}% 较低，流动性一般")
            else:
                details.append(f"换手率 {turnover:.2f}% 正常")

        return {"score": score / max(count, 1) if count > 0 else 0.0, "details": details}

    @staticmethod
    def _score_macro(indicators: dict[str, Any]) -> dict[str, Any]:
        """Score macro/volatility. Returns {score, details}."""
        score = 0.0
        details: list[str] = []

        vol = indicators.get("volatility") or {}
        vol_level = vol.get("level", "medium")
        vol_pct = vol.get("pct", 0)
        if vol_level == "high":
            score += -25
            details.append(f"波动率高（{vol_pct:.1f}%），市场风险大，-25分")
        elif vol_level == "low":
            score += 10
            details.append(f"波动率低（{vol_pct:.1f}%），走势稳定，+10分")
        else:
            details.append(f"波动率中等（{vol_pct:.1f}%），风险可控")

        vr = indicators.get("volume_ratio", 1.0)
        trend = indicators.get("trend", "sideways")
        if vr > 2.0:
            if "downtrend" in trend:
                score += -15
                details.append(f"放量下跌（量比 {vr:.1f}），抛压重，-15分")
            elif "uptrend" in trend:
                score += 15
                details.append(f"放量上涨（量比 {vr:.1f}），资金流入，+15分")
            else:
                details.append(f"成交量放大（量比 {vr:.1f}），等待方向确认")
        elif vr < 0.5:
            details.append(f"成交量萎缩（量比 {vr:.1f}），市场观望情绪浓")
        else:
            details.append(f"成交量正常（量比 {vr:.1f}）")

        pp = indicators.get("price_position", 50)
        if pp > 80:
            score += -10
            details.append(f"价格处于近期高位（{pp:.0f}%），接近超买，-10分")
        elif pp < 20:
            score += 10
            details.append(f"价格处于近期低位（{pp:.0f}%），可能超卖，+10分")
        else:
            details.append(f"价格处于近期中部（{pp:.0f}%），位置中性")

        bb = indicators.get("bollinger") or {}
        if bb:
            upper = bb.get("upper")
            lower = bb.get("lower")
            price = indicators.get("current_price")
            if price and upper and lower:
                if price > upper:
                    score += -10
                    details.append(f"价格突破布林上轨（{upper:.2f}），短期超买，-10分")
                elif price < lower:
                    score += 10
                    details.append(f"价格跌破布林下轨（{lower:.2f}），短期超卖，+10分")
                else:
                    details.append(f"价格在布林带内运行（{lower:.2f}-{upper:.2f}）")

        return {"score": score, "details": details}

    @staticmethod
    def _score_to_decision(score: float) -> str:
        """Convert overall score to BUY/SELL/HOLD decision."""
        if score >= 20:
            return "BUY"
        if score <= -20:
            return "SELL"
        return "HOLD"

    @staticmethod
    def _score_to_rating(score: float) -> str:
        """Convert score to human-readable rating text."""
        if score >= 50:
            return "强烈看多"
        if score >= 20:
            return "看多"
        if score >= 5:
            return "轻微偏多"
        if score > -5:
            return "中性观望"
        if score > -20:
            return "轻微偏空"
        if score > -50:
            return "看空"
        return "强烈看空"

    def _build_human_report(
        self,
        data: dict[str, Any],
        objective: dict[str, Any],
        current_price: float,
        decision: str,
    ) -> dict[str, Any]:
        """
        Build human-readable analysis report when LLM is unavailable.
        Returns summary, key_reasons, risks, metrics_snapshot, trading_levels.
        """
        indicators = data.get("indicators") or {}
        fundamental = data.get("fundamental") or {}
        price_data = data.get("price") or {}
        breakdown = objective.get("score_breakdown", {})

        tech = breakdown.get("technical", {})
        fund = breakdown.get("fundamental", {})
        macro = breakdown.get("macro", {})

        # --- Helper: pick most representative detail ---
        def _pick_detail(dim: dict[str, Any]) -> str:
            details = dim.get("details", [])
            if not details:
                return "无数据"
            # Pick the detail with the largest absolute score impact
            best = details[0]
            best_score = 0
            for d in details:
                # Extract numeric score from detail text like "+40分" or "-30分"
                import re
                m = re.search(r"([+-]?\d+(?:\.\d+)?)分", d)
                if m:
                    s = abs(float(m.group(1)))
                    if s > best_score:
                        best_score = s
                        best = d
            return best

        # --- Summary ---
        rating = self._score_to_rating(objective["overall_score"])
        parts: list[str] = []

        parts.append(f"综合评级：{rating}（评分 {objective['overall_score']:+.1f}/100）")
        parts.append(f"技术面 {tech.get('score', 0):+.1f}分：{_pick_detail(tech)}")
        if fund.get("details"):
            parts.append(f"基本面 {fund['score']:+.1f}分：{_pick_detail(fund)}")
        parts.append(f"情绪面 {macro.get('score', 0):+.1f}分：{_pick_detail(macro)}")

        change = price_data.get("changePercent", 0) or 0
        parts.append(f"当前股价 {current_price:.2f} 元，较昨日{'上涨' if change >= 0 else '下跌'} {abs(change):.2f}%。")

        if decision == "BUY":
            parts.append("综合信号偏积极，可考虑逢低布局，但需设置止损。")
        elif decision == "SELL":
            parts.append("综合信号偏消极，建议控制仓位或考虑减仓。")
        else:
            parts.append("多空信号交织，建议观望等待更明确的趋势信号。")

        summary = "\n".join(parts)

        # --- Key reasons (positive signals) ---
        positive_keywords = ("偏多", "看多", "超卖", "反弹", "吸引力", "较多", "强势上涨", "金叉", "多头排列", "破")
        key_reasons: list[str] = []
        for dim in (tech, fund, macro):
            for d in dim.get("details", []):
                if any(kw in d for kw in positive_keywords) and "+" in d:
                    key_reasons.append(d.split("，")[0])
        if not key_reasons:
            key_reasons = ["技术指标中性，暂无强烈看多信号"]

        # --- Risks (negative signals) ---
        negative_keywords = ("偏空", "看空", "超买", "风险", "过高", "偏大", "回调", "死叉", "空头", "下跌")
        risks: list[str] = []
        for dim in (tech, fund, macro):
            for d in dim.get("details", []):
                if any(kw in d for kw in negative_keywords) and "-" in d:
                    risks.append(d.split("，")[0])
        if not risks:
            risks = ["暂无显著风险信号，但需关注大盘走势"]

        # --- Metrics snapshot ---
        rsi_data = indicators.get("rsi") or {}
        macd_data = indicators.get("macd") or {}
        ma_data = indicators.get("moving_averages") or {}
        vol_data = indicators.get("volatility") or {}
        levels = indicators.get("levels") or {}
        trading = indicators.get("trading_levels") or {}
        bb = indicators.get("bollinger") or {}

        metrics_snapshot = {
            "current_price": current_price,
            "change_percent": change,
            "rsi": rsi_data.get("value"),
            "macd_signal": macd_data.get("signal"),
            "ma_trend": ma_data.get("trend"),
            "volatility_level": vol_data.get("level"),
            "volatility_pct": vol_data.get("pct"),
            "support": levels.get("support"),
            "resistance": levels.get("resistance"),
            "pe_ratio": fundamental.get("pe_ratio"),
            "pb_ratio": fundamental.get("pb_ratio"),
            "turnover_rate": fundamental.get("turnover_rate"),
            "volume_ratio": indicators.get("volume_ratio"),
            "price_position": indicators.get("price_position"),
            "bollinger_upper": bb.get("upper"),
            "bollinger_lower": bb.get("lower"),
        }

        # --- Trading levels ---
        sl = trading.get("stop_loss")
        tp = trading.get("take_profit")
        if decision == "BUY":
            entry = round(current_price * 0.98, 2)
        elif decision == "SELL":
            entry = round(current_price * 1.02, 2)
        else:
            entry = current_price

        trading_levels = {
            "entry_price": entry,
            "stop_loss": sl,
            "take_profit": tp,
            "risk_reward": trading.get("risk_reward"),
        }

        return {
            "summary": summary,
            "key_reasons": key_reasons[:5],
            "risks": risks[:5],
            "metrics_snapshot": metrics_snapshot,
            "trading_levels": trading_levels,
        }

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
        overall_score: float, llm_confidence: int, market_type: str, data_meta: dict[str, Any] | None = None
    ) -> int:
        """Calibrate confidence based on signal strength + data completeness.

        Args:
            overall_score: -100 to +100 objective score
            llm_confidence: LLM raw confidence (0-100), ignored if LLM unavailable
            market_type: "stock" or "crypto"
            data_meta: data collection metadata with "success" and "failed" lists
        """
        # 1. Signal strength component (20-70) — linear mapping for smooth gradation
        abs_score = abs(overall_score)
        # Map 0-100 abs_score to 20-70 (minimum 20 even for neutral signals)
        signal_conf = 20 + (abs_score / 100.0) * 50

        # 2. Data completeness component (0-30)
        success_modules = data_meta.get("success", []) if data_meta else []
        failed_modules = data_meta.get("failed", []) if data_meta else []
        total_modules = len(success_modules) + len(failed_modules)
        if total_modules > 0:
            completeness = len(success_modules) / total_modules
        else:
            completeness = 0.0

        # Map completeness to 0-30 points
        completeness_conf = completeness * 30

        # 3. LLM component (0-20), only if LLM was actually called successfully
        llm_conf = 0.0
        if llm_confidence >= 50:  # LLM responded with reasonable confidence
            llm_conf = min(20, (llm_confidence - 50) * 0.4)

        # Total: signal + completeness + llm_bonus
        calibrated = signal_conf + completeness_conf + llm_conf
        return max(15, min(95, round(calibrated)))

    # ── Memory Storage ──────────────────────────────────────────────────────

    @staticmethod
    def _store_memory(
        symbol: str, market_type: str, result: dict[str, Any], current_price: float, user_id: str | None = None
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
                user_id=user_id,
                # 透传完整分析结果用于历史详情展示
                score_breakdown=result.get("score_breakdown"),
                metrics_snapshot=result.get("metrics_snapshot"),
                trading_levels=result.get("trading_levels"),
                key_reasons=result.get("key_reasons"),
                risks=result.get("risks"),
                overall_rating=result.get("overall_rating"),
                overall_score=result.get("overall_score"),
                data_meta=result.get("data_meta"),
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
