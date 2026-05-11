"""
UF Stock Assistant — 定时任务调度器
支持日终交收、数据清理等定时任务
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.logging import get_logger
from app.services.market_sync import sync_all_securities
from app.trading.settlement_engine import run_daily_settlement

logger = get_logger("app.trading.scheduler")

_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    """获取全局调度器（单例）"""
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
    return _scheduler


def start_scheduler() -> None:
    """启动定时任务调度器"""
    scheduler = get_scheduler()

    # 日终交收任务：每晚 20:00 执行
    scheduler.add_job(
        _daily_settlement_job,
        trigger=CronTrigger(hour=20, minute=0),
        id="daily_settlement",
        name="日终资金持仓交收",
        replace_existing=True,
    )

    # 数据清理任务：每天凌晨 2:00 执行
    scheduler.add_job(
        _cleanup_job,
        trigger=CronTrigger(hour=2, minute=0),
        id="daily_cleanup",
        name="日终数据清理",
        replace_existing=True,
    )

    # 证券信息同步：每 30 分钟执行一次
    scheduler.add_job(
        _securities_sync_job,
        trigger="interval",
        minutes=30,
        id="securities_sync",
        name="证券信息全量同步",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("trading_scheduler_started", jobs=[j.name for j in scheduler.get_jobs()])


def stop_scheduler() -> None:
    """停止定时任务调度器"""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("trading_scheduler_stopped")


def _daily_settlement_job() -> None:
    """日终交收任务"""
    try:
        logger.info("daily_settlement_job_started")
        result = run_daily_settlement()
        logger.info(
            "daily_settlement_job_completed",
            processed=result.get("processed", 0),
            success=result.get("success", 0),
            failed=result.get("failed", 0),
        )
    except Exception as exc:
        logger.error("daily_settlement_job_failed", error=str(exc))


def _cleanup_job() -> None:
    """数据清理任务（预留）"""
    try:
        logger.info("cleanup_job_started")
        # TODO: 清理过期订单、归档历史数据等
        logger.info("cleanup_job_completed")
    except Exception as exc:
        logger.error("cleanup_job_failed", error=str(exc))


def _securities_sync_job() -> None:
    """证券信息同步定时任务"""
    try:
        logger.info("securities_sync_job_started")
        result = sync_all_securities()
        logger.info(
            "securities_sync_job_completed",
            a_share=result.get("a_share", {}),
            crypto=result.get("crypto", {}),
        )
    except Exception as exc:
        logger.error("securities_sync_job_failed", error=str(exc))


def trigger_settlement_now() -> dict[str, Any]:
    """手动触发日终交收（用于测试）"""
    logger.info("manual_settlement_triggered")
    return run_daily_settlement()
