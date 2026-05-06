"""
UF Stock Assistant — 均线交叉策略
短期均线上穿长期均线 → 买入信号
短期均线下穿长期均线 → 卖出信号
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.core.constants import TrendDirection
from app.core.logging import get_logger

from ..base import BaseStrategy, Signal, StrategyParameter, StrategyResult

logger = get_logger("app.strategies.ma_crossover")


class MACrossoverStrategy(BaseStrategy):
    """
    均线交叉策略 (Moving Average Crossover)
    
    原理：
    - 短期均线（如 5 日）上穿长期均线（如 20 日）→ 金叉 → 买入信号
    - 短期均线下穿长期均线（如 20 日）→ 死叉 → 卖出信号
    
    参数：
    - short_window: 短期均线周期
    - long_window: 长期均线周期
    """

    @property
    def name(self) -> str:
        return "均线交叉策略"

    @property
    def description(self) -> str:
        return "短期均线上穿长期均线产生买入信号，下穿产生卖出信号"

    @property
    def parameters(self) -> list[StrategyParameter]:
        return [
            StrategyParameter("short_window", "int", 5, 2, 60, "短期均线周期"),
            StrategyParameter("long_window", "int", 20, 5, 250, "长期均线周期"),
        ]

    def evaluate(self, symbol: str, data: list[dict[str, Any]]) -> StrategyResult:
        """执行均线交叉分析"""
        short_window = self.get_param("short_window")
        long_window = self.get_param("long_window")
        
        min_bars = long_window + 2
        if not self.validate_data(data, min_bars):
            return StrategyResult(
                strategy_name=self.name,
                symbol=symbol,
                error=f"数据不足，至少需要 {min_bars} 根 K 线",
            )
        
        try:
            df = pd.DataFrame(data)
            df["ma_short"] = df["close"].rolling(window=short_window).mean()
            df["ma_long"] = df["close"].rolling(window=long_window).mean()
            
            # 取最近两根有效数据
            valid = df.dropna().tail(2)
            if len(valid) < 2:
                return StrategyResult(
                    strategy_name=self.name,
                    symbol=symbol,
                    error="有效数据不足",
                )
            
            prev = valid.iloc[-2]
            curr = valid.iloc[-1]
            
            prev_short = prev["ma_short"]
            prev_long = prev["ma_long"]
            curr_short = curr["ma_short"]
            curr_long = curr["ma_long"]
            
            # 判断交叉
            prev_diff = prev_short - prev_long
            curr_diff = curr_short - curr_long
            
            signal = None
            reason = ""
            
            if prev_diff <= 0 and curr_diff > 0:
                # 金叉
                signal = Signal(
                    symbol=symbol,
                    direction=TrendDirection.UP,
                    confidence=min(abs(curr_diff) / curr_long * 100, 1.0),
                    reason=f"短期均线({short_window}日:{curr_short:.2f})上穿长期均线({long_window}日:{curr_long:.2f})，形成金叉",
                )
            elif prev_diff >= 0 and curr_diff < 0:
                # 死叉
                signal = Signal(
                    symbol=symbol,
                    direction=TrendDirection.DOWN,
                    confidence=min(abs(curr_diff) / curr_long * 100, 1.0),
                    reason=f"短期均线({short_window}日:{curr_short:.2f})下穿长期均线({long_window}日:{curr_long:.2f})，形成死叉",
                )
            else:
                # 无交叉
                trend = "多头排列" if curr_diff > 0 else "空头排列"
                signal = Signal(
                    symbol=symbol,
                    direction=TrendDirection.FLAT,
                    confidence=0.0,
                    reason=f"暂无交叉信号，当前{trend}，短期均线:{curr_short:.2f}，长期均线:{curr_long:.2f}",
                )
            
            return StrategyResult(
                strategy_name=self.name,
                symbol=symbol,
                signal=signal,
                data={
                    "ma_short": round(curr_short, 2),
                    "ma_long": round(curr_long, 2),
                    "short_window": short_window,
                    "long_window": long_window,
                },
            )
            
        except Exception as exc:
            logger.error("ma_evaluation_failed", symbol=symbol, error=str(exc))
            return StrategyResult(
                strategy_name=self.name,
                symbol=symbol,
                error=f"分析失败: {exc}",
            )
