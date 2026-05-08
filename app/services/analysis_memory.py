"""
UF Stock Assistant — AI 分析记忆服务
存储分析历史、验证决策正确性、相似模式匹配、性能统计
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.data.analysis_models import AnalysisMemoryModel, AICalibrationModel
from app.data.billing_models import Base
from app.services.billing import BillingStore
from app.tools.stock_data import get_stock_realtime

logger = get_logger("app.services.analysis_memory")


def _safe_json(val: Any, default: Any = None) -> Any:
    """安全解析 JSON 或返回默认值"""
    if val is None:
        return default
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return default
    return default


def _vol_bands_similar(a: str, b: str) -> bool:
    """判断两个波动率级别是否在同一区间"""
    low = {"low", "normal", "normal_low"}
    high = {"high", "elevated", "volatile", "very_high"}
    a, b = str(a).lower(), str(b).lower()
    return (a in low and b in low) or (a in high and b in high)


class _AnalysisMemoryAdapter:
    """适配 fast_analysis.py 的 store(symbol=..., market=..., ...) 调用方式"""

    def __init__(self) -> None:
        self._svc = AnalysisMemoryService()

    def store(
        self,
        symbol: str,
        market: str,
        decision: str,
        price: float,
        confidence: int = 50,
        technical_score: float = 0,
        fundamental_score: float = 0,
        sentiment_score: float = 0,
        summary: str = "",
        user_id: str | None = None,
    ) -> int | None:
        """将扁平参数转换为 AnalysisMemoryService.store 期望的 dict 格式"""
        analysis_result = {
            "symbol": symbol,
            "market": market,
            "decision": decision,
            "confidence": confidence,
            "summary": summary,
            "scores": {
                "technical_score": technical_score,
                "fundamental_score": fundamental_score,
                "sentiment_score": sentiment_score,
            },
            "market_data": {
                "current_price": price,
            },
        }
        return self._svc.store(analysis_result, user_id=user_id)


class AnalysisMemoryService:
    """AI 分析记忆服务"""

    def __init__(self, session=None) -> None:
        self._session = session
        if self._session is None:
            self._ensure_tables()

    def _ensure_tables(self) -> None:
        Base.metadata.create_all(BillingStore.get_engine())

    def _get_session(self):
        if self._session is not None:
            return self._session
        return BillingStore.get_session()

    # ------------------------------------------------------------------
    # 存储与查询
    # ------------------------------------------------------------------

    def store(self, analysis_result: Dict[str, Any], user_id: str | None = None) -> int | None:
        """存储分析结果，返回 memory_id"""
        try:
            session = self._get_session()
            consensus = analysis_result.get("consensus") or {}
            row = AnalysisMemoryModel(
                user_id=user_id,
                market=analysis_result.get("market"),
                symbol=analysis_result.get("symbol"),
                decision=analysis_result.get("decision"),
                confidence=analysis_result.get("confidence"),
                price_at_analysis=_extract_price(analysis_result),
                summary=analysis_result.get("summary"),
                reasons=_safe_json(analysis_result.get("reasons")),
                scores=_safe_json(analysis_result.get("scores")),
                indicators_snapshot=_safe_json(analysis_result.get("indicators")),
                raw_result=_safe_json(analysis_result),
                consensus_score=consensus.get("consensus_score"),
                consensus_abs=consensus.get("consensus_abs"),
                agreement_ratio=consensus.get("agreement_ratio"),
                quality_multiplier=consensus.get("quality_multiplier"),
                task_status="completed",
            )
            session.add(row)
            session.commit()
            memory_id = row.id
            session.close()
            logger.info(f"Stored analysis memory #{memory_id} for {analysis_result.get('symbol')} by user {user_id}")
            return memory_id
        except Exception as e:
            logger.error(f"Failed to store analysis memory: {e}", exc_info=True)
            return None

    def get_recent(self, market: str, symbol: str, days: int = 7, limit: int = 5) -> List[Dict[str, Any]]:
        """获取近期分析历史"""
        try:
            session = self._get_session()
            since = datetime.now(timezone.utc) - timedelta(days=days)
            rows = (
                session.query(AnalysisMemoryModel)
                .filter_by(market=market, symbol=symbol)
                .filter(AnalysisMemoryModel.created_at > since)
                .order_by(AnalysisMemoryModel.created_at.desc())
                .limit(limit)
                .all()
            )
            result = [_row_to_dict(r) for r in rows]
            session.close()
            return result
        except Exception as e:
            logger.error(f"Failed to get recent memories: {e}")
            return []

    def get_history(self, user_id: str | None = None, symbol: str | None = None, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """分页查询分析历史"""
        try:
            offset = (page - 1) * page_size
            session = self._get_session()
            query = session.query(AnalysisMemoryModel)
            if user_id:
                query = query.filter_by(user_id=user_id)
            if symbol:
                query = query.filter_by(symbol=symbol)
            total = query.count()
            rows = (
                query.order_by(AnalysisMemoryModel.created_at.desc())
                .offset(offset)
                .limit(page_size)
                .all()
            )
            items = [_row_to_dict(r, full=True) for r in rows]
            session.close()
            return {"items": items, "total": total, "page": page, "page_size": page_size}
        except Exception as e:
            logger.error(f"Failed to get history: {e}")
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

    # ------------------------------------------------------------------
    # 验证与反思
    # ------------------------------------------------------------------

    def validate_unvalidated_older_than(self, min_age_days: int = 7, limit: int = 200) -> Dict[str, Any]:
        """验证未验证的历史决策（用于离线校准）"""
        stats = {"validated": 0, "correct": 0, "incorrect": 0, "errors": 0}
        try:
            session = self._get_session()
            since = datetime.now(timezone.utc) - timedelta(days=min_age_days)
            rows = (
                session.query(AnalysisMemoryModel)
                .filter(AnalysisMemoryModel.validated_at.is_(None))
                .filter(AnalysisMemoryModel.created_at < since)
                .limit(limit)
                .all()
            )

            for row in rows:
                try:
                    current_price = _fetch_current_price(row.market, row.symbol)
                    if not current_price or current_price <= 0:
                        continue
                    analysis_price = float(row.price_at_analysis or 0)
                    if analysis_price <= 0:
                        continue

                    return_pct = ((current_price - analysis_price) / analysis_price) * 100
                    was_correct = _decision_correctness(row.decision, return_pct)

                    row.validated_at = datetime.now(timezone.utc)
                    row.actual_return_pct = Decimal(str(return_pct))
                    row.was_correct = was_correct

                    stats["validated"] += 1
                    if was_correct:
                        stats["correct"] += 1
                    else:
                        stats["incorrect"] += 1
                except Exception as e:
                    logger.warning(f"Failed to validate memory {row.id}: {e}")
                    stats["errors"] += 1

            session.commit()
            session.close()
        except Exception as e:
            logger.error(f"validate_unvalidated_older_than failed: {e}", exc_info=True)

        stats["accuracy_pct"] = round(stats["correct"] / stats["validated"] * 100, 2) if stats["validated"] > 0 else 0
        logger.info(f"Validation completed: {stats}")
        return stats

    # ------------------------------------------------------------------
    # 相似模式匹配
    # ------------------------------------------------------------------

    def get_similar_patterns(
        self, market: str, symbol: str, current_indicators: Dict[str, Any], limit: int = 3
    ) -> List[Dict[str, Any]]:
        """查找历史相似技术指标模式"""
        try:
            session = self._get_session()
            rows = (
                session.query(AnalysisMemoryModel)
                .filter_by(market=market, symbol=symbol)
                .filter(AnalysisMemoryModel.validated_at.isnot(None))
                .filter(AnalysisMemoryModel.was_correct.isnot(None))
                .order_by(AnalysisMemoryModel.validated_at.desc())
                .limit(limit * 5)
                .all()
            )

            rsi = float(_deep_get(current_indicators, "rsi", "value") or 50)
            macd_signal = str(_deep_get(current_indicators, "macd", "signal") or "neutral").lower()
            ma_trend = str(_deep_get(current_indicators, "moving_averages", "trend") or "sideways").lower()
            vol_level = str(_deep_get(current_indicators, "volatility", "level") or "normal").lower()

            scored = []
            for row in rows:
                ind = _safe_json(row.indicators_snapshot, {})
                hist_rsi = float(_deep_get(ind, "rsi", "value") or 50)
                hist_macd = str(_deep_get(ind, "macd", "signal") or "neutral").lower()
                hist_ma = str(_deep_get(ind, "moving_averages", "trend") or "sideways").lower()
                hist_vol = str(_deep_get(ind, "volatility", "level") or "normal").lower()

                rsi_diff = abs(hist_rsi - rsi)
                rsi_score = max(0, 1 - rsi_diff / 30) * 0.3
                macd_score = 0.3 if hist_macd == macd_signal else 0
                ma_score = 0.25 if hist_ma == ma_trend else 0
                vol_score = 0.15 if hist_vol == vol_level else (0.08 if _vol_bands_similar(vol_level, hist_vol) else 0)

                sim = rsi_score + macd_score + ma_score + vol_score
                if sim < 0.25:
                    continue

                bonus = 0.1 if row.was_correct else 0
                scored.append((sim + bonus, {
                    "id": row.id,
                    "decision": row.decision,
                    "confidence": row.confidence,
                    "price": float(row.price_at_analysis) if row.price_at_analysis else None,
                    "summary": row.summary,
                    "was_correct": row.was_correct,
                    "actual_return_pct": float(row.actual_return_pct) if row.actual_return_pct else None,
                    "similarity_score": round(sim + bonus, 3),
                }))

            scored.sort(key=lambda x: -x[0])
            session.close()
            return [p[1] for p in scored[:limit]]
        except Exception as e:
            logger.error(f"Failed to get similar patterns: {e}")
            return []

    # ------------------------------------------------------------------
    # 用户反馈
    # ------------------------------------------------------------------

    def record_feedback(self, memory_id: int, feedback: str) -> bool:
        """记录用户对某条分析的反馈"""
        try:
            session = self._get_session()
            row = session.query(AnalysisMemoryModel).filter_by(id=memory_id).first()
            if row:
                row.user_feedback = feedback
                row.feedback_at = datetime.now(timezone.utc)
                session.commit()
            session.close()
            return True
        except Exception as e:
            logger.error(f"Failed to record feedback: {e}")
            return False

    # ------------------------------------------------------------------
    # 性能统计
    # ------------------------------------------------------------------

    def get_performance_stats(self, market: str | None = None, symbol: str | None = None, days: int = 30) -> Dict[str, Any]:
        """获取 AI 性能统计"""
        from sqlalchemy import func
        try:
            session = self._get_session()
            query = session.query(AnalysisMemoryModel).filter(AnalysisMemoryModel.validated_at.isnot(None))
            if market:
                query = query.filter_by(market=market)
            if symbol:
                query = query.filter_by(symbol=symbol)
            since = datetime.now(timezone.utc) - timedelta(days=days)
            query = query.filter(AnalysisMemoryModel.created_at > since)

            total = query.count()
            if total == 0:
                return {"total_analyses": 0, "accuracy_pct": 0, "avg_return_pct": 0}

            correct = query.filter(AnalysisMemoryModel.was_correct == True).count()
            avg_return = query.with_entities(func.avg(AnalysisMemoryModel.actual_return_pct)).scalar() or 0

            buy_count = query.filter(AnalysisMemoryModel.decision == "BUY").count()
            sell_count = query.filter(AnalysisMemoryModel.decision == "SELL").count()
            hold_count = query.filter(AnalysisMemoryModel.decision == "HOLD").count()

            helpful = query.filter(AnalysisMemoryModel.user_feedback == "helpful").count()
            feedback_total = query.filter(AnalysisMemoryModel.user_feedback.isnot(None)).count()

            session.close()
            return {
                "total_analyses": total,
                "accuracy_pct": round(correct / total * 100, 2),
                "avg_return_pct": round(float(avg_return), 2),
                "decision_distribution": {"buy": buy_count, "sell": sell_count, "hold": hold_count},
                "user_satisfaction_pct": round(helpful / feedback_total * 100, 2) if feedback_total > 0 else 0,
                "period_days": days,
            }
        except Exception as e:
            logger.error(f"Failed to get performance stats: {e}")
            return {"total_analyses": 0, "accuracy_pct": 0, "error": str(e)}

    def get_adjusted_confidence(self, raw_confidence: int, market: str | None = None, symbol: str | None = None) -> int:
        """基于历史准确率桶校准置信度"""
        buckets = [(50, 60, "50_60"), (60, 70, "60_70"), (70, 80, "70_80"), (80, 90, "80_90"), (90, 101, "90_100")]
        bucket_key = None
        for lo, hi, key in buckets:
            if lo <= raw_confidence < hi:
                bucket_key = key
                break
        if not bucket_key:
            return max(1, min(99, int(raw_confidence)))

        acc_map = self._get_confidence_accuracy_by_bucket(market=market, symbol=symbol)
        acc = acc_map.get(bucket_key)
        if acc is None or acc <= 0:
            return max(1, min(99, int(raw_confidence)))

        expected = 0.5 + (raw_confidence - 50) / 100
        if expected <= 0:
            return raw_confidence
        factor = acc / expected
        adjusted = int(raw_confidence * factor)
        return max(1, min(99, adjusted))

    def _get_confidence_accuracy_by_bucket(self, market: str | None = None, symbol: str | None = None, days: int = 90) -> Dict[str, float]:
        """按置信度桶计算实际准确率"""
        from sqlalchemy import func
        try:
            session = self._get_session()
            query = (
                session.query(AnalysisMemoryModel.confidence, AnalysisMemoryModel.was_correct)
                .filter(AnalysisMemoryModel.validated_at.isnot(None))
                .filter(AnalysisMemoryModel.was_correct.isnot(None))
                .filter(AnalysisMemoryModel.confidence.isnot(None))
            )
            if market:
                query = query.filter_by(market=market)
            if symbol:
                query = query.filter_by(symbol=symbol)
            since = datetime.now(timezone.utc) - timedelta(days=days)
            query = query.filter(AnalysisMemoryModel.created_at > since)
            rows = query.all()
            session.close()

            out = {}
            for lo, hi in [(50, 60), (60, 70), (70, 80), (80, 90), (90, 101)]:
                subset = [r for r in rows if lo <= (r.confidence or 0) < hi]
                if len(subset) < 5:
                    continue
                correct = sum(1 for r in subset if r.was_correct)
                out[f"{lo}_{hi}"] = correct / len(subset)
            return out
        except Exception as e:
            logger.warning(f"get_confidence_accuracy_by_bucket failed: {e}")
            return {}


# ------------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------------

def get_analysis_memory() -> _AnalysisMemoryAdapter:
    """返回兼容 fast_analysis.py 调用方式的适配器实例"""
    return _AnalysisMemoryAdapter()


def _extract_price(analysis_result: Dict[str, Any]) -> Decimal | None:
    """从分析结果中提取价格"""
    try:
        price = analysis_result.get("market_data", {}).get("current_price")
        if price is not None:
            return Decimal(str(price))
        return None
    except Exception:
        return None


def _fetch_current_price(market: str, symbol: str) -> float | None:
    """获取当前价格（A 股用东财 API）"""
    try:
        if market.lower() in ("a_stock", "astock", "cn", "china"):
            data = get_stock_realtime(symbol)
            if isinstance(data, dict):
                return float(data.get("price") or data.get("最新价") or 0)
        # TODO: 扩展 Crypto / USStock 支持
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch price for {market}/{symbol}: {e}")
        return None


def _decision_correctness(decision: str, return_pct: float) -> bool:
    """判断决策是否正确"""
    d = str(decision or "HOLD").upper()
    if d == "BUY":
        return return_pct > 2.0
    if d == "SELL":
        return return_pct < -2.0
    return abs(return_pct) <= 5.0


def _deep_get(d: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """深度字典取值"""
    for key in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(key, default)
    return d


def _row_to_dict(row: AnalysisMemoryModel, full: bool = False) -> Dict[str, Any]:
    """ORM 行转字典（前端兼容格式）"""
    # confidence 数据库存的是 0-100 整数，前端期望 0-1 小数
    confidence_raw = row.confidence or 0
    confidence_normalized = confidence_raw / 100.0 if confidence_raw <= 100 else confidence_raw

    d: Dict[str, Any] = {
        "id": row.id,
        "decision": row.decision,
        "signal": row.decision,  # 前端兼容字段
        "confidence": confidence_normalized,
        "price": float(row.price_at_analysis) if row.price_at_analysis else None,
        "summary": row.summary,
        "was_correct": row.was_correct,
        "actual_return_pct": float(row.actual_return_pct) if row.actual_return_pct else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if full:
        d.update({
            "market": row.market,
            "symbol": row.symbol,
            "reasons": _safe_json(row.reasons, []),
            "scores": _safe_json(row.scores, {}),
            "indicators": _safe_json(row.indicators_snapshot, {}),
            "status": row.task_status or "completed",
            "user_feedback": row.user_feedback,
        })
    return d
