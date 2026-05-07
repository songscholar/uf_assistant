"""
UF Stock Assistant — AI 反思服务
定期验证历史 AI 决策与实际价格结果，触发校准
"""

from __future__ import annotations

import os
import threading
import time
from typing import Dict, Any, Optional

from app.core.logging import get_logger
from app.services.analysis_memory import AnalysisMemoryService

logger = get_logger("app.services.reflection")

_reflection_thread: Optional[threading.Thread] = None
_reflection_stop = threading.Event()


class ReflectionService:
    """反思服务：验证历史决策 + 触发校准"""

    def run_verification_cycle(self) -> Dict[str, Any]:
        """运行一次验证周期"""
        memory = AnalysisMemoryService()
        min_age_days = int(os.getenv("REFLECTION_MIN_AGE_DAYS", "7"))
        limit = int(os.getenv("REFLECTION_VALIDATE_LIMIT", "200"))

        stats = memory.validate_unvalidated_older_than(min_age_days=min_age_days, limit=limit)
        logger.info(f"Reflection validation: {stats}")

        if stats.get("validated", 0) > 0:
            self._maybe_run_calibration()
        else:
            logger.debug("No new validations, skipping calibration")

        return stats

    def _maybe_run_calibration(self) -> None:
        """条件触发 AI 校准"""
        if os.getenv("ENABLE_OFFLINE_AI_CALIBRATION", "true").lower() != "true":
            return
        try:
            from app.services.ai_calibration import AICalibrationService
            svc = AICalibrationService()
            markets = (os.getenv("AI_CALIBRATION_MARKETS", "AStock") or "AStock").strip().split(",")
            for market in markets:
                market = market.strip()
                if not market:
                    continue
                result = svc.calibrate_market(
                    market=market,
                    lookback_days=int(os.getenv("AI_CALIBRATION_LOOKBACK_DAYS", "30")),
                    min_samples=int(os.getenv("AI_CALIBRATION_MIN_SAMPLES", "80")),
                    validate_before=False,
                )
                if result:
                    logger.info(
                        f"[Reflection] Calibration updated for {market}: "
                        f"accuracy={result.best_accuracy:.1f}% thr=±{result.buy_threshold:.1f}"
                    )
        except Exception as e:
            logger.warning(f"Reflection calibration failed: {e}", exc_info=True)


def start_reflection_worker() -> None:
    """启动后台反思 Worker（daemon 线程）"""
    global _reflection_thread
    if os.getenv("ENABLE_REFLECTION_WORKER", "true").lower() != "true":
        logger.info("Reflection worker disabled (ENABLE_REFLECTION_WORKER != true).")
        return
    interval_sec = int(os.getenv("REFLECTION_WORKER_INTERVAL_SEC", "86400"))
    if _reflection_thread and _reflection_thread.is_alive():
        return

    def _run() -> None:
        _reflection_stop.clear()
        logger.info(f"Reflection worker started, interval={interval_sec}s")
        while not _reflection_stop.is_set():
            try:
                ReflectionService().run_verification_cycle()
            except Exception as e:
                logger.error(f"Reflection cycle failed: {e}", exc_info=True)
            _reflection_stop.wait(timeout=interval_sec)
        logger.info("Reflection worker stopped.")

    _reflection_thread = threading.Thread(target=_run, name="ReflectionWorker", daemon=True)
    _reflection_thread.start()


def stop_reflection_worker() -> None:
    """停止反思 Worker"""
    _reflection_stop.set()
    if _reflection_thread:
        _reflection_thread.join(timeout=5)
