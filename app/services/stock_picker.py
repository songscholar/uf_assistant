"""
UF Stock Assistant — 选股服务
根据策略条件筛选股票
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.core.cache import ensure_cache
from app.core.logging import get_logger
from app.strategies.base import BaseStrategy, StrategyResult
from app.strategies.registry import create_strategy
from app.tools.stock_data import get_stock_history

logger = get_logger("app.services.stock_picker")


class StockPicker:
    """
    选股器
    
    根据策略对多只股票进行分析，筛选出符合条件的股票
    """
    
    def __init__(self, max_stocks: int = 100) -> None:
        self._max_stocks = max_stocks
    
    def pick_by_strategy(
        self,
        strategy_key: str,
        symbols: list[str],
        strategy_params: dict[str, Any] | None = None,
        min_confidence: float = 0.3,
    ) -> dict[str, Any]:
        """
        根据策略选股
        
        Args:
            strategy_key: 策略标识
            symbols: 股票代码列表
            strategy_params: 策略参数
            min_confidence: 最小置信度阈值
            
        Returns:
            JSON 格式的选股结果
        """
        strategy = create_strategy(strategy_key, **(strategy_params or {}))
        if not strategy:
            return {"error": f"策略 '{strategy_key}' 不存在"}
        
        # 预加载股票名称映射（缓存为空时触发加载，首次约 25~30s）
        name_map: dict[str, str] = {}
        try:
            from app.core.cache import ensure_cache
            df = ensure_cache("market:spot")
            if df is not None and not df.empty:
                name_map = dict(zip(df["代码"].astype(str), df["名称"]))
        except Exception:
            pass

        up_signals = []
        down_signals = []
        hold_signals = []
        failed_symbols = []

        for symbol in symbols[:self._max_stocks]:
            try:
                # 获取历史数据
                history_json = get_stock_history(symbol, period="daily", limit=120)
                history_data = json.loads(history_json)

                if "error" in history_data or not history_data.get("data"):
                    failed_symbols.append(symbol)
                    continue

                # 执行策略
                result = strategy.evaluate(symbol, history_data["data"])

                if result.error:
                    failed_symbols.append(symbol)
                    continue

                direction = result.signal.direction.value if result.signal else None
                record: dict[str, Any] = {
                    "symbol": symbol,
                    "name": name_map.get(symbol, ""),
                    "direction": direction,
                    "confidence": round(result.signal.confidence, 4) if result.signal else 0,
                    "reason": result.signal.reason if result.signal else "无信号",
                    "data": result.data,
                }

                if direction == "up":
                    up_signals.append(record)
                elif direction == "down":
                    down_signals.append(record)
                else:
                    hold_signals.append(record)

            except Exception as exc:
                logger.warning("stock_evaluation_skipped", symbol=symbol, error=str(exc))
                failed_symbols.append(symbol)
                continue

        # 排序：买入/卖出按置信度降序
        up_signals.sort(key=lambda x: x["confidence"], reverse=True)
        down_signals.sort(key=lambda x: x["confidence"], reverse=True)

        output: dict[str, Any] = {
            "strategy": strategy.name,
            "strategy_key": strategy_key,
            "total_analyzed": len(symbols),
            "buy_count": len(up_signals),
            "sell_count": len(down_signals),
            "hold_count": len(hold_signals),
            "failed_count": len(failed_symbols),
            "buy_signals": up_signals[:20],
            "sell_signals": down_signals[:20],
            "hold_signals": hold_signals[:20],
            "failed_symbols": failed_symbols[:20],
            "timestamp": datetime.now().isoformat(),
        }

        logger.info("stock_picking_completed", strategy=strategy_key,
                    buy=len(up_signals), sell=len(down_signals), hold=len(hold_signals))
        return output
    
    def quick_screen(
        self,
        conditions: dict[str, Any],
    ) -> dict[str, Any]:
        """
        快速筛选（基于基本条件）

        Args:
            conditions: 筛选条件
                - min_price: 最低价格
                - max_price: 最高价格
                - min_change_pct: 最小涨跌幅（百分比数值，如 5 表示 ≥5%）
                - max_change_pct: 最大涨跌幅（百分比数值，如 -3 表示 ≤-3%）
                - min_volume: 最小成交量
                - limit: 返回数量

        Returns:
            dict 格式的筛选结果
        """
        # ── 从缓存获取（只读，不触发刷新——stock_zh_a_spot 获取全市场需 ~30s）──
        try:
            from app.core.cache import get_cached_df
            df = get_cached_df("market:spot")
        except Exception as exc:
            logger.warning("quick_screen_cache_failed", error=str(exc))

        if df is None or df.empty:
            # 缓存未就绪时触发后台刷新（不阻塞）
            try:
                from app.core.cache import refresh_cache
                import threading
                threading.Thread(target=refresh_cache, args=("market:spot",), daemon=True).start()
                logger.info("quick_screen_trigger_background_refresh")
            except Exception:
                pass
            return {"error": "全市场数据正在初始化，请 30 秒后重试"}

        try:
            total_all = len(df)

            # 应用条件过滤
            if "min_price" in conditions:
                df = df[df["最新价"] >= conditions["min_price"]]
            if "max_price" in conditions:
                df = df[df["最新价"] <= conditions["max_price"]]
            if "min_change_pct" in conditions:
                df = df[df["涨跌幅"] >= conditions["min_change_pct"]]
            if "max_change_pct" in conditions:
                df = df[df["涨跌幅"] <= conditions["max_change_pct"]]
            if "min_volume" in conditions:
                df = df[df["成交量"] >= conditions["min_volume"]]

            # 排除 ST
            df = df[~df["名称"].str.contains("ST|退", na=False)]

            total_matched = len(df)
            limit = conditions.get("limit", 20)
            df = df.head(limit)

            stocks = []
            for _, row in df.iterrows():
                stocks.append({
                    "symbol": row["代码"],
                    "name": row["名称"],
                    "price": row.get("最新价"),
                    "change_pct": row.get("涨跌幅"),
                    "volume": row.get("成交量"),
                    "amount": row.get("成交额"),
                    "pe": row.get("市盈率-动态"),
                    "pb": row.get("市净率"),
                })

            # 构建自然语言条件描述
            cond_texts = []
            if "min_price" in conditions or "max_price" in conditions:
                cond_texts.append(f"价格 {conditions.get('min_price', '')}~{conditions.get('max_price', '')} 元")
            if "min_change_pct" in conditions or "max_change_pct" in conditions:
                cond_texts.append(f"涨跌幅 {conditions.get('min_change_pct', '')}%~{conditions.get('max_change_pct', '')}%")
            if "min_volume" in conditions:
                cond_texts.append(f"成交量 ≥ {conditions['min_volume']}")
            conditions_text = "、".join(cond_texts) if cond_texts else "无特殊条件"

            return {
                "conditions": conditions,
                "conditions_text": conditions_text,
                "total_all": total_all,
                "total_matched": total_matched,
                "count": len(stocks),
                "stocks": stocks,
            }

        except Exception as exc:
            logger.error("quick_screen_failed", error=str(exc))
            return {"error": "筛选失败，请稍后重试"}
