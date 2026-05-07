"""
UF Stock Assistant — AI 校准服务（离线）
基于历史验证结果自动搜索最优决策阈值
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from app.core.logging import get_logger
from app.data.analysis_models import AICalibrationModel, AnalysisMemoryModel
from app.data.billing_models import Base
from app.services.billing import BillingStore

logger = get_logger("app.services.ai_calibration")

DEFAULTS: Dict[str, float] = {
    "buy_threshold": 20.0,
    "sell_threshold": -20.0,
    "min_consensus_abs_override": 15.0,
    "quality_hold_threshold": 0.7,
}


@dataclass
class CalibrationResult:
    market: str
    buy_threshold: float
    sell_threshold: float
    best_accuracy: float
    coverage: Dict[str, int]
    sample_count: int
    validated_count: int
    updated_at_ts: float


class AICalibrationService:
    """AI 校准服务"""

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

    def get_latest(self, market: str) -> Dict[str, float]:
        """获取市场最新校准配置，无记录则返回默认值"""
        market = (market or "").strip()
        if not market:
            return dict(DEFAULTS)
        try:
            session = self._get_session()
            row = (
                session.query(AICalibrationModel)
                .filter_by(market=market)
                .order_by(AICalibrationModel.validated_at.desc())
                .first()
            )
            session.close()
            if not row:
                return dict(DEFAULTS)
            return {
                "buy_threshold": float(row.buy_threshold or DEFAULTS["buy_threshold"]),
                "sell_threshold": float(row.sell_threshold or DEFAULTS["sell_threshold"]),
                "min_consensus_abs_override": float(
                    row.min_consensus_abs_override or DEFAULTS["min_consensus_abs_override"]
                ),
                "quality_hold_threshold": float(
                    row.quality_hold_threshold or DEFAULTS["quality_hold_threshold"]
                ),
            }
        except Exception as e:
            logger.warning(f"get_latest calibration failed: {e}")
            return dict(DEFAULTS)

    def calibrate_market(
        self,
        market: str = "AStock",
        *,
        lookback_days: int = 30,
        min_samples: int = 80,
        validate_before: bool = True,
    ) -> Optional[CalibrationResult]:
        """对指定市场进行阈值校准"""
        market = (market or "").strip()
        if not market:
            return None

        abs_thresholds = _candidate_abs_thresholds()
        validated_count = 0

        # 可选：先验证旧记录
        if validate_before:
            try:
                from app.services.analysis_memory import AnalysisMemoryService
                mem = AnalysisMemoryService()
                stats = mem.validate_unvalidated_older_than(min_age_days=7, limit=300)
                validated_count = int(stats.get("validated", 0))
            except Exception as e:
                logger.warning(f"pre-validation failed (skipped): {e}")

        # 拉取已验证样本
        rows: List[AnalysisMemoryModel] = []
        try:
            session = self._get_session()
            since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
            rows = (
                session.query(AnalysisMemoryModel)
                .filter_by(market=market)
                .filter(AnalysisMemoryModel.validated_at.isnot(None))
                .filter(AnalysisMemoryModel.actual_return_pct.isnot(None))
                .filter(AnalysisMemoryModel.consensus_score.isnot(None))
                .filter(AnalysisMemoryModel.created_at > since)
                .all()
            )
            session.close()
        except Exception as e:
            logger.error(f"Failed to fetch memory rows for calibration: {e}")
            return None

        sample_count = len(rows)
        if sample_count < min_samples:
            logger.warning(f"[AI Calibration] Not enough samples for {market}: {sample_count} < {min_samples}")
            return None

        best_abs_thr = abs_thresholds[0]
        best_accuracy = -1.0
        best_coverage: Dict[str, int] = {"BUY": 0, "SELL": 0, "HOLD": 0}

        for thr in abs_thresholds:
            correct = total = 0
            coverage: Dict[str, int] = {"BUY": 0, "SELL": 0, "HOLD": 0}
            for r in rows:
                try:
                    score = float(r.consensus_score or 0.0)
                    return_pct = float(r.actual_return_pct or 0.0)
                except Exception:
                    continue
                pred = _predict_from_score(score, thr)
                coverage[pred] += 1
                total += 1
                if _correctness(pred, return_pct):
                    correct += 1
            if total <= 0:
                continue
            acc = correct / total * 100.0
            buy_sell_cov = coverage["BUY"] + coverage["SELL"]
            best_buy_sell = best_coverage["BUY"] + best_coverage["SELL"]
            if acc > best_accuracy or (acc == best_accuracy and buy_sell_cov > best_buy_sell):
                best_accuracy = acc
                best_abs_thr = thr
                best_coverage = coverage

        # 写入校准结果
        cfg = self.get_latest(market)
        try:
            session = self._get_session()
            row = AICalibrationModel(
                market=market,
                buy_threshold=Decimal(str(best_abs_thr)),
                sell_threshold=Decimal(str(-best_abs_thr)),
                min_consensus_abs_override=Decimal(str(cfg.get("min_consensus_abs_override", DEFAULTS["min_consensus_abs_override"]))),
                quality_hold_threshold=Decimal(str(cfg.get("quality_hold_threshold", DEFAULTS["quality_hold_threshold"]))),
                best_accuracy=Decimal(str(best_accuracy)),
                sample_count=sample_count,
                validated_count=validated_count,
                coverage=best_coverage,
            )
            session.add(row)
            session.commit()
            session.close()
        except Exception as e:
            logger.error(f"[AI Calibration] Failed to persist: {e}")
            return None

        return CalibrationResult(
            market=market,
            buy_threshold=float(best_abs_thr),
            sell_threshold=float(-best_abs_thr),
            best_accuracy=float(best_accuracy),
            coverage=best_coverage,
            sample_count=sample_count,
            validated_count=validated_count,
            updated_at_ts=__import__("time").time(),
        )


# ------------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------------

def _candidate_abs_thresholds() -> List[float]:
    env = os.getenv("AI_CALIBRATION_CANDIDATE_ABS_THRESHOLDS", "").strip()
    if env:
        out = []
        for p in env.split(","):
            p = p.strip()
            if p:
                try:
                    out.append(float(p))
                except Exception:
                    continue
        if out:
            return sorted(set(out))
    return [10, 12, 14, 16, 18, 20, 22, 25, 30]


def _predict_from_score(score: float, abs_thr: float) -> str:
    if score >= abs_thr:
        return "BUY"
    if score <= -abs_thr:
        return "SELL"
    return "HOLD"


def _correctness(decision: str, return_pct: float) -> bool:
    if decision == "BUY":
        return return_pct > 2.0
    if decision == "SELL":
        return return_pct < -2.0
    return abs(return_pct) <= 5.0
