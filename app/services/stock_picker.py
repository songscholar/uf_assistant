"""
UF Stock Assistant — 选股服务
根据策略条件筛选股票
"""

from __future__ import annotations

import json
from typing import Any

import akshare as ak

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
    ) -> str:
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
            return json.dumps({"error": f"策略 '{strategy_key}' 不存在"}, ensure_ascii=False)
        
        results = []
        up_signals = []
        down_signals = []
        
        for symbol in symbols[:self._max_stocks]:
            try:
                # 获取历史数据
                history_json = get_stock_history(symbol, period="daily", limit=120)
                history_data = json.loads(history_json)
                
                if "error" in history_data or not history_data.get("data"):
                    continue
                
                # 执行策略
                result = strategy.evaluate(symbol, history_data["data"])
                
                if result.error:
                    continue
                
                if result.signal and result.signal.confidence >= min_confidence:
                    record = {
                        "symbol": symbol,
                        "signal": result.signal.direction.value,
                        "confidence": round(result.signal.confidence, 4),
                        "reason": result.signal.reason,
                        "data": result.data,
                    }
                    results.append(record)
                    
                    if result.signal.direction.value == "up":
                        up_signals.append(record)
                    elif result.signal.direction.value == "down":
                        down_signals.append(record)
                        
            except Exception as exc:
                logger.warning("stock_evaluation_skipped", symbol=symbol, error=str(exc))
                continue
        
        # 排序：按置信度降序
        up_signals.sort(key=lambda x: x["confidence"], reverse=True)
        down_signals.sort(key=lambda x: x["confidence"], reverse=True)
        
        output = {
            "strategy": strategy.name,
            "strategy_key": strategy_key,
            "total_analyzed": len(symbols),
            "signals_found": len(results),
            "buy_signals": up_signals[:20],
            "sell_signals": down_signals[:20],
            "timestamp": json.loads(json.dumps(datetime.now().isoformat(), default=str)),
        }
        
        logger.info("stock_picking_completed", strategy=strategy_key, signals=len(results))
        return json.dumps(output, ensure_ascii=False, default=str)
    
    def quick_screen(
        self,
        conditions: dict[str, Any],
    ) -> str:
        """
        快速筛选（基于基本条件）
        
        Args:
            conditions: 筛选条件
                - min_price: 最低价格
                - max_price: 最高价格
                - min_change_pct: 最小涨跌幅
                - max_change_pct: 最大涨跌幅
                - min_volume: 最小成交量
                - limit: 返回数量
                
        Returns:
            JSON 格式的筛选结果
        """
        try:
            df = ak.stock_zh_a_spot_em()
            
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
            
            return json.dumps({
                "conditions": conditions,
                "count": len(stocks),
                "stocks": stocks,
            }, ensure_ascii=False, default=str)
            
        except Exception as exc:
            logger.error("quick_screen_failed", error=str(exc))
            return json.dumps({"error": f"筛选失败: {exc}"}, ensure_ascii=False)


from datetime import datetime
