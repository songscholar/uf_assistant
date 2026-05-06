"""
UF Stock Assistant — RSI 策略
RSI < 30 超卖（买入），RSI > 70 超买（卖出）
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.core.constants import TrendDirection
from app.core.logging import get_logger

from ..base import BaseStrategy, Signal, StrategyParameter, StrategyResult

logger = get_logger("app.strategies.rsi")


class RSIStrategy(BaseStrategy):
    """
    RSI 策略 (Relative Strength Index)
    
    原理：
    - RSI < 30 → 超卖 → 潜在的买入机会
    - RSI > 70 → 超买 → 潜在的卖出机会
    - RSI 从超卖区回升 → 买入信号
    - RSI 从超买区回落 → 卖出信号
    
    参数：
    - period: RSI 计算周期
    - oversold: 超卖阈值
    - overbought: 超买阈值
    """

    @property
    def name(self) -> str:
        return "RSI超卖策略"

    @property
    def description(self) -> str:
        return "基于 RSI 指标的超买超卖判断产生交易信号"

    @property
    def parameters(self) -> list[StrategyParameter]:
        return [
            StrategyParameter("period", "int", 14, 5, 60, "RSI 计算周期"),
            StrategyParameter("oversold", "int", 30, 10, 40, "超卖阈值"),
            StrategyParameter("overbought", "int", 70, 60, 90, "超买阈值"),
        ]

    def evaluate(self, symbol: str, data: list[dict[str, Any]]) -> StrategyResult:
        """执行 RSI 分析"""
        period = self.get_param("period")
        oversold = self.get_param("oversold")
        overbought = self.get_param("overbought")
        
        min_bars = period + 5
        if not self.validate_data(data, min_bars):
            return StrategyResult(
                strategy_name=self.name,
                symbol=symbol,
                error=f"数据不足，至少需要 {min_bars} 根 K 线",
            )
        
        try:
            df = pd.DataFrame(data)
            close = df["close"]
            
            # 计算 RSI
            delta = close.diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            
            avg_gain = gain.rolling(window=period).mean()
            avg_loss = loss.rolling(window=period).mean()
            
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            # 取最近两根有效数据
            valid_rsi = rsi.dropna().tail(2)
            if len(valid_rsi) < 2:
                return StrategyResult(
                    strategy_name=self.name,
                    symbol=symbol,
                    error="有效 RSI 数据不足",
                )
            
            prev_rsi = valid_rsi.iloc[-2]
            curr_rsi = valid_rsi.iloc[-1]
            
            signal = None
            
            if prev_rsi < oversold and curr_rsi >= oversold:
                # 从超卖区回升
                signal = Signal(
                    symbol=symbol,
                    direction=TrendDirection.UP,
                    confidence=min((oversold + 20 - curr_rsi) / 20, 1.0),
                    reason=f"RSI 从超卖区回升：{prev_rsi:.1f} → {curr_rsi:.1f}，超卖阈值 {oversold}",
                )
            elif prev_rsi > overbought and curr_rsi <= overbought:
                # 从超买区回落
                signal = Signal(
                    symbol=symbol,
                    direction=TrendDirection.DOWN,
                    confidence=min((curr_rsi - overbought + 20) / 20, 1.0),
                    reason=f"RSI 从超买区回落：{prev_rsi:.1f} → {curr_rsi:.1f}，超买阈值 {overbought}",
                )
            elif curr_rsi < oversold:
                # 当前超卖
                signal = Signal(
                    symbol=symbol,
                    direction=TrendDirection.UP,
                    confidence=min((oversold - curr_rsi) / oversold, 1.0),
                    reason=f"RSI 超卖：{curr_rsi:.1f}（阈值 {oversold}），潜在的买入机会",
                )
            elif curr_rsi > overbought:
                # 当前超买
                signal = Signal(
                    symbol=symbol,
                    direction=TrendDirection.DOWN,
                    confidence=min((curr_rsi - overbought) / (100 - overbought), 1.0),
                    reason=f"RSI 超买：{curr_rsi:.1f}（阈值 {overbought}），潜在的卖出机会",
                )
            else:
                # 中性区域
                signal = Signal(
                    symbol=symbol,
                    direction=TrendDirection.FLAT,
                    confidence=0.0,
                    reason=f"RSI 中性：{curr_rsi:.1f}，处于 {oversold}-{overbought} 区间",
                )
            
            return StrategyResult(
                strategy_name=self.name,
                symbol=symbol,
                signal=signal,
                data={
                    "rsi": round(curr_rsi, 2),
                    "prev_rsi": round(prev_rsi, 2),
                    "period": period,
                    "oversold": oversold,
                    "overbought": overbought,
                },
            )
            
        except Exception as exc:
            logger.error("rsi_evaluation_failed", symbol=symbol, error=str(exc))
            return StrategyResult(
                strategy_name=self.name,
                symbol=symbol,
                error=f"分析失败: {exc}",
            )
