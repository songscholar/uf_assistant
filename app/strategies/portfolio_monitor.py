"""
UF Stock Assistant — 持仓监控器 (增强版)

后台线程持续更新所有活跃持仓的最新价格和未实现盈亏。
增强功能:
- AI 分析集成 (FastAnalysisService)
- 持仓告警 (价格/盈亏阈值)
- 批量通知 (NotifierManager)
- ThreadPoolExecutor 并行分析
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.logging import get_logger
from app.strategies.models import StrategyPosition

logger = get_logger("app.strategies.portfolio_monitor")


# ── Alert Types ──────────────────────────────────────────────────────────


@dataclass
class PositionAlert:
    """持仓告警配置"""
    alert_type: str  # price_above, price_below, pnl_above, pnl_below
    threshold: float
    current_value: float = 0.0
    triggered: bool = False


@dataclass
class AlertConfig:
    """告警配置集合"""
    alerts: list[PositionAlert] = field(default_factory=list)
    cooldown_seconds: float = 300.0  # 5 分钟冷却
    last_triggered: float = 0.0


# ── Portfolio Monitor ────────────────────────────────────────────────────


class PortfolioMonitor:
    """监控所有运行中策略的持仓，支持 AI 分析和告警"""

    def __init__(
        self,
        db_url: str,
        update_interval: float = 30.0,
        ai_analysis_interval: float = 300.0,
        max_ai_workers: int = 4,
    ) -> None:
        self._update_interval = update_interval
        self._ai_analysis_interval = ai_analysis_interval
        self._max_ai_workers = max_ai_workers
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_ai_analysis: float = 0.0

        # 独立数据库连接池
        self._engine = create_engine(db_url, pool_size=2, max_overflow=2)
        self._session_factory = sessionmaker(bind=self._engine)

        # 价格获取回调（由外部注入，签名: (symbol: str) -> float | None）
        self._price_fetcher: Any = None

        # 告警配置（key: position_id）
        self._alert_configs: dict[int, AlertConfig] = {}

        # 通知管理器（由外部注入）
        self._notifier: Any = None

        # AI 分析服务（延迟初始化）
        self._ai_service: Any = None

    # ── Configuration ────────────────────────────────────────────────────

    def set_price_fetcher(self, fetcher: Any) -> None:
        """注入实时价格获取回调

        Args:
            fetcher: callable(symbol) -> float | None
        """
        self._price_fetcher = fetcher
        logger.info("price_fetcher_set")

    def set_notifier(self, notifier: Any) -> None:
        """注入通知管理器

        Args:
            notifier: NotifierManager instance
        """
        self._notifier = notifier
        logger.info("notifier_set")

    def set_alert(self, position_id: int, alert: PositionAlert) -> None:
        """为指定持仓设置告警"""
        if position_id not in self._alert_configs:
            self._alert_configs[position_id] = AlertConfig()
        self._alert_configs[position_id].alerts.append(alert)
        logger.info("alert_set", position_id=position_id, alert_type=alert.alert_type, threshold=alert.threshold)

    def remove_alerts(self, position_id: int) -> None:
        """移除指定持仓的所有告警"""
        self._alert_configs.pop(position_id, None)

    # ── Lifecycle ────────────────────────────────────────────────────────

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

    # ── Main Loop ────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """主循环：持续刷新持仓数据 + AI 分析 + 告警检查"""
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

            # 1. 更新价格和未实现盈亏
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

        # 2. AI 分析（按间隔触发）
        now = time.time()
        if now - self._last_ai_analysis >= self._ai_analysis_interval:
            self._last_ai_analysis = now
            try:
                self._run_ai_analysis(positions)
            except Exception:
                logger.error("ai_analysis_error", exc_info=True)

        # 3. 检查告警
        try:
            self._check_alerts(positions)
        except Exception:
            logger.error("alert_check_error", exc_info=True)

    # ── Price & PnL Refresh ──────────────────────────────────────────────

    @staticmethod
    def _fetch_open_positions(session: Session) -> list[StrategyPosition]:
        """查询所有 size > 0 的持仓"""
        stmt = select(StrategyPosition).where(StrategyPosition.size > 0)
        return list(session.execute(stmt).scalars().all())

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

    # ── AI Analysis ──────────────────────────────────────────────────────

    def _get_ai_service(self) -> Any:
        """延迟初始化 AI 分析服务"""
        if self._ai_service is None:
            try:
                from app.strategies.fast_analysis import get_fast_analysis_service
                self._ai_service = get_fast_analysis_service()
            except Exception as exc:
                logger.warning("ai_service_init_failed", error=str(exc))
        return self._ai_service

    def _run_ai_analysis(self, positions: list[StrategyPosition]) -> None:
        """并行分析所有持仓"""
        ai_service = self._get_ai_service()
        if ai_service is None or not positions:
            return

        # 按 symbol 去重
        unique_symbols: dict[str, str] = {}
        for p in positions:
            if p.symbol not in unique_symbols:
                # 推断 market_type from symbol
                market_type = "stock" if not ("/" in p.symbol) else "crypto"
                unique_symbols[p.symbol] = market_type

        results: dict[str, dict[str, Any]] = {}

        with ThreadPoolExecutor(max_workers=self._max_ai_workers) as pool:
            futures = {
                pool.submit(ai_service.analyze, symbol, market_type): symbol
                for symbol, market_type in unique_symbols.items()
            }
            try:
                for future in as_completed(futures, timeout=60):
                    symbol = futures[future]
                    try:
                        result = future.result(timeout=10)
                        results[symbol] = result
                    except Exception as exc:
                        logger.warning("ai_analysis_failed", symbol=symbol, error=str(exc))
            except Exception:
                logger.warning("ai_analysis_timeout")

        if results:
            logger.info("ai_analysis_completed", analyzed=len(results), total=len(unique_symbols))

        # 缓存 AI 分析结果到持仓
        try:
            with self._session_factory() as session:
                for position in positions:
                    if position.symbol in results:
                        # Store as JSON in a field if available
                        pass
                session.commit()
        except Exception:
            logger.warning("ai_cache_store_failed", exc_info=True)

    # ── Alert Checking ───────────────────────────────────────────────────

    def _check_alerts(self, positions: list[StrategyPosition]) -> None:
        """检查所有持仓的告警条件"""
        if not self._alert_configs or not self._notifier:
            return

        now = time.time()
        triggered_alerts: list[tuple[StrategyPosition, PositionAlert]] = []

        for position in positions:
            config = self._alert_configs.get(position.id)
            if not config:
                continue

            # 冷却期检查
            if now - config.last_triggered < config.cooldown_seconds:
                continue

            current_price = self._fetch_latest_price(position.symbol)
            if current_price is None:
                continue

            for alert in config.alerts:
                alert.current_value = current_price if "price" in alert.alert_type else (position.unrealized_pnl or 0.0)

                should_trigger = False
                if alert.alert_type == "price_above" and current_price >= alert.threshold:
                    should_trigger = True
                elif alert.alert_type == "price_below" and current_price <= alert.threshold:
                    should_trigger = True
                elif alert.alert_type == "pnl_above" and (position.unrealized_pnl or 0) >= alert.threshold:
                    should_trigger = True
                elif alert.alert_type == "pnl_below" and (position.unrealized_pnl or 0) <= alert.threshold:
                    should_trigger = True

                if should_trigger and not alert.triggered:
                    alert.triggered = True
                    triggered_alerts.append((position, alert))
                    config.last_triggered = now

        # 发送通知
        for position, alert in triggered_alerts:
            self._send_alert_notification(position, alert)

    def _send_alert_notification(self, position: StrategyPosition, alert: PositionAlert) -> None:
        """发送告警通知"""
        try:
            from app.strategies.notifier import render_template

            if "price" in alert.alert_type:
                condition = f"{'>' if 'above' in alert.alert_type else '<'} {alert.threshold:.4f}"
                message_text = render_template(
                    "alert_price",
                    language="zh",
                    symbol=position.symbol,
                    current_price=f"{alert.current_value:.4f}",
                    condition=condition,
                )
            else:
                message_text = render_template(
                    "alert_pnl",
                    language="zh",
                    strategy_name=f"Strategy_{position.strategy_id}",
                    symbol=position.symbol,
                    pnl=f"{alert.current_value:.4f}",
                )

            from app.strategies.notifier import SignalMessage

            signal = SignalMessage(
                strategy_id=int(position.strategy_id) if position.strategy_id else 0,
                strategy_name=f"Strategy_{position.strategy_id}",
                symbol=position.symbol,
                signal_type=f"alert_{alert.alert_type}",
                price=alert.current_value,
                confidence=0.0,
                reason=message_text,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            self._notifier.notify(signal)
            logger.info("alert_triggered", position_id=position.id, alert_type=alert.alert_type)

        except Exception:
            logger.error("alert_notification_failed", position_id=position.id, exc_info=True)

    # ── Query Interface ──────────────────────────────────────────────────

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

    def get_alerts(self) -> dict[str, list[dict[str, Any]]]:
        """获取所有活跃告警"""
        result: dict[str, list[dict[str, Any]]] = {}
        for pos_id, config in self._alert_configs.items():
            result[str(pos_id)] = [
                {
                    "alert_type": a.alert_type,
                    "threshold": a.threshold,
                    "current_value": a.current_value,
                    "triggered": a.triggered,
                }
                for a in config.alerts
            ]
        return result
