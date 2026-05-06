"""
UF Stock Assistant — 布林带突破策略
价格上穿上轨 → 买入，下穿下轨 → 卖出
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.core.constants import TrendDirection
from app.core.logging import get_logger

from ..base import BaseStrategy, Signal, StrategyParameter, StrategyResult

logger = get_logger("app.strategies.bollinger")


class BollingerStrategy(BaseStrategy):
    """
    布林带策略 (Bollinger Bands)
    
    原理：
    - 价格上穿上轨 → 强势突破 → 买入信号
    - 价格下穿下轨 → 弱势跌破 → 卖出信号
    - 价格从下轨反弹回轨道内 → 买入信号
    - 价格从上轨回落回轨道内 → 卖出信号
    
    布林带计算公式：
    - 中轨 = N 日简单移动平均线
    - 上轨 = 中轨 + K × N 日标准差
    - 下轨 = 中轨 - K × N 日标准差
    
    参数：
    - period: 计算周期
    - std_dev: 标准差倍数
    """

    @property
    def name(self) -> str:
        return "布林带突破策略"

    @property
    def description(self) -> str:
        return "基于布林带上下轨的突破/回归产生交易信号"

    @property
    def parameters(self) -> list[StrategyParameter]:
        return [
            StrategyParameter("period", "int", 20, 5, 60, "布林带计算周期"),
            StrategyParameter("std_dev", "float", 2.0, 1.0, 4.0, "标准差倍数"),
        ]

    def evaluate(self, symbol: str, data: list[dict[str, Any]]) -> StrategyResult:
        """执行布林带分析"""
        period = self.get_param("period")
        std_dev = self.get_param("std_dev")
        
        min_bars = period + 2
        if not self.validate_data(data, min_bars):
            return StrategyResult(
                strategy_name=self.name,
                symbol=symbol,
                error=f"数据不足，至少需要 {min_bars} 根 K 线",
            )
        
        try:
            df = pd.DataFrame(data)
            close = df["close"]
            
            # 计算布林带
            middle = close.rolling(window=period).mean()
            std = close.rolling(window=period).std()
            upper = middle + std_dev * std
            lower = middle - std_dev * std
            
            # 取最近两根有效数据
            valid = df.dropna().tail(2)
            if len(valid) < 2:
                return StrategyResult(
                    strategy_name=self.name,
                    symbol=symbol,
                    error="有效数据不足",
                )
            
            idx = valid.index
            prev_close = close.iloc[idx[-2]]
            curr_close = close.iloc[idx[-1]]
            prev_upper = upper.iloc[idx[-2]]
            curr_upper = upper.iloc[idx[-1]]
            prev_lower = lower.iloc[idx[-2]]
            curr_lower = lower.iloc[idx[-1]]
            curr_middle = middle.iloc[idx[-1]]
            
            signal = None
            
            # 判断突破/回归
            if prev_close <= prev_upper and curr_close > curr_upper:
                # 上穿上轨
                signal = Signal(
                    symbol=symbol,
                    direction=TrendDirection.UP,
                    confidence=min((curr_close - curr_upper) / curr_upper * 100, 1.0),
                    reason=f"价格上穿上轨：{curr_close:.2f} > 上轨 {curr_upper:.2f}，强势突破",
                )
            elif prev_close >= prev_lower and curr_close < curr_lower:
                # 下穿下轨
                signal = Signal(
                    symbol=symbol,
                    direction=TrendDirection.DOWN,
                    confidence=min((curr_lower - curr_close) / curr_lower * 100, 1.0),
                    reason=f"价格下穿下轨：{curr_close:.2f} < 下轨 {curr_lower:.2f}，弱势跌破",
                )
            elif prev_close < prev_lower and curr_close >= curr_lower:
                # 从下轨反弹回轨道内
                signal = Signal(
                    symbol=symbol,
                    direction=TrendDirection.UP,
                    confidence=0.6,
                    reason=f"价格从下轨反弹：{prev_close:.2f} → {curr_close:.2f}，下轨 {curr_lower:.2f}",
                )
            elif prev_close > prev_upper and curr_close <= curr_upper:
                # 从上轨回落回轨道内
                signal = Signal(
                    symbol=symbol,
                    direction=TrendDirection.DOWN,
                    confidence=0.6,
                    reason=f"价格从上轨回落：{prev_close:.2f} → {curr_close:.2f}，上轨 {curr_upper:.2f}",
                )
            else:
                # 在轨道内运行
                position = (curr_close - curr_lower) / (curr_upper - curr_lower) if curr_upper != curr_lower else 0.5
                band_position = "中轨偏上" if position > 0.5 else "中轨偏下"
                signal = Signal(
                    symbol=symbol,
                    direction=TrendDirection.FLAT,
                    confidence=0.0,
                    reason=f"价格在布林带内运行：{curr_close:.2f}，{band_position}，上轨:{curr_upper:.2f} 下轨:{curr_lower:.2f}",
                )
            
            return StrategyResult(
                strategy_name=self.name,
                symbol=symbol,
                signal=signal,
                data={
                    "upper": round(curr_upper, 2),
                    "middle": round(curr_middle, 2),
                    "lower": round(curr_lower, 2),
                    "close": round(curr_close, 2),
                    "period": period,
                    "std_dev": std_dev,
                },
            )
            
        except Exception as exc:
            logger.error("bollinger_evaluation_failed", symbol=symbol, error=str(exc))
            return StrategyResult(
                strategy_name=self.name,
                symbol=symbol,
                error=f"分析失败: {exc}",
            )
