"""
UF Stock Assistant — 持仓监控器
后台线程持续更新所有活跃持仓的最新价格和未实现盈亏
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.logging import get_logger
from app.strategies.models import StrategyPosition

logger = get_logger("app.strategies.portfolio_monitor")


class PortfolioMonitor:
    """监控所有运行中策略的持仓，同步实时盈亏"""

    def __init__(self, db_url: str, update_interval: float = 30.0) -> None:
        self._update_interval = update_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        # 独立数据库连接池
        self._engine = create_engine(db_url, pool_size=2, max_overflow=2)
        self._session_factory = sessionmaker(bind=self._engine)

        # 价格获取回调（由外部注入，签名: (symbol: str) -> float | None）
        self._price_fetcher: Any = None

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------

    def set_price_fetcher(self, fetcher: Any) -> None:
        """注入实时价格获取回调

        Args:
            fetcher: callable(symbol) -> float | None
        """
        self._price_fetcher = fetcher
        logger.info("price_fetcher_set")

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self) -> None:
        """启动监控线程"""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("portfolio_monitor_already_running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="portfolio-monitor",
            daemon=True,
        )
        self._thread.start()
        logger.info("portfolio_monitor_started", update_interval=self._update_interval)

    def stop(self, timeout: float = 10.0) -> None:
        """停止监控线程"""
        if self._thread is None or not self._thread.is_alive():
            logger.info("portfolio_monitor_not_running")
            return

        self._stop_event.set()
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            logger.warning("portfolio_monitor_stop_timeout", timeout=timeout)
        else:
            logger.info("portfolio_monitor_stopped")

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """主循环：持续刷新持仓数据"""
        logger.info("portfolio_monitor_loop_started")
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception:
                logger.error("portfolio_monitor_tick_error", exc_info=True)

            self._stop_event.wait(timeout=self._update_interval)

        logger.info("portfolio_monitor_loop_exited")

    def _tick(self) -> None:
        """单次刷新周期"""
        with self._session_factory() as session:
            positions = self._fetch_open_positions(session)
            if not positions:
                return

            updated = 0
            for position in positions:
                try:
                    changed = self._refresh_position(session, position)
                    if changed:
                        updated += 1
                except Exception:
                    logger.error(
                        "position_refresh_error",
                        position_id=position.id,
                        symbol=position.symbol,
                        exc_info=True,
                    )

            session.commit()

            if updated > 0:
                logger.info("portfolio_positions_updated", count=updated, total=len(positions))

    # ------------------------------------------------------------------
    # 数据获取
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_open_positions(session: Session) -> list[StrategyPosition]:
        """查询所有 size > 0 的持仓"""
        stmt = select(StrategyPosition).where(StrategyPosition.size > 0)
        return list(session.execute(stmt).scalars().all())

    # ------------------------------------------------------------------
    # 持仓刷新
    # ------------------------------------------------------------------

    def _refresh_position(self, session: Session, position: StrategyPosition) -> bool:
        """刷新单个持仓的价格和盈亏，返回是否有变化"""
        latest_price = self._fetch_latest_price(position.symbol)
        if latest_price is None:
            return False

        changed = False

        # 更新最高/最低价
        if latest_price > (position.highest_price or 0.0):
            position.highest_price = latest_price
            changed = True
        if position.lowest_price <= 0.0 or latest_price < position.lowest_price:
            position.lowest_price = latest_price
            changed = True

        # 计算未实现盈亏
        new_pnl = self._calculate_unrealized_pnl(position, latest_price)
        if abs(new_pnl - (position.unrealized_pnl or 0.0)) > 0.001:
            position.unrealized_pnl = new_pnl
            changed = True

        if changed:
            position.updated_at = datetime.now(timezone.utc)

        return changed

    def _fetch_latest_price(self, symbol: str) -> float | None:
        """通过回调获取最新价格"""
        if self._price_fetcher is None:
            return None
        try:
            return self._price_fetcher(symbol)
        except Exception:
            logger.warning("price_fetch_failed", symbol=symbol, exc_info=True)
            return None

    @staticmethod
    def _calculate_unrealized_pnl(
        position: StrategyPosition,
        current_price: float,
    ) -> float:
        """计算未实现盈亏

        多头: pnl = (current_price - entry_price) * size
        空头: pnl = (entry_price - current_price) * size
        """
        entry_price = position.entry_price or 0.0
        size = position.size or 0.0

        if entry_price <= 0.0 or size <= 0.0:
            return 0.0

        if position.side == "long":
            return (current_price - entry_price) * size
        if position.side == "short":
            return (entry_price - current_price) * size

        return 0.0

    # ------------------------------------------------------------------
    # 查询接口（供外部同步调用）
    # ------------------------------------------------------------------

    def get_all_positions(self) -> list[dict[str, Any]]:
        """获取所有持仓快照（同步调用，供 API 使用）"""
        with self._session_factory() as session:
            positions = self._fetch_open_positions(session)
            return [
                {
                    "id": p.id,
                    "strategy_id": p.strategy_id,
                    "symbol": p.symbol,
                    "side": p.side,
                    "size": p.size,
                    "entry_price": p.entry_price,
                    "highest_price": p.highest_price,
                    "lowest_price": p.lowest_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                }
                for p in positions
            ]

    def get_strategy_summary(self, strategy_id: str) -> dict[str, Any]:
        """获取单个策略的持仓汇总"""
        with self._session_factory() as session:
            stmt = select(StrategyPosition).where(
                StrategyPosition.strategy_id == strategy_id,
                StrategyPosition.size > 0,
            )
            positions = list(session.execute(stmt).scalars().all())

            total_pnl = sum(p.unrealized_pnl or 0.0 for p in positions)
            total_value = sum((p.amount or 0.0) for p in positions)

            return {
                "strategy_id": strategy_id,
                "position_count": len(positions),
                "total_unrealized_pnl": round(total_pnl, 4),
                "total_value": round(total_value, 4),
                "positions": [
                    {
                        "symbol": p.symbol,
                        "side": p.side,
                        "size": p.size,
                        "entry_price": p.entry_price,
                        "unrealized_pnl": p.unrealized_pnl,
                    }
                    for p in positions
                ],
            }
