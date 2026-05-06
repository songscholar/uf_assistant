"""
UF Stock Assistant — MACD 策略
MACD 金叉/死叉信号
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.core.constants import TrendDirection
from app.core.logging import get_logger

from ..base import BaseStrategy, Signal, StrategyParameter, StrategyResult

logger = get_logger("app.strategies.macd")


class MACDStrategy(BaseStrategy):
    """
    MACD 策略 (Moving Average Convergence Divergence)
    
    原理：
    - DIF 上穿 DEA → 金叉 → 买入信号
    - DIF 下穿 DEA → 死叉 → 卖出信号
    - 可结合柱状图 (MACD Histogram) 判断动量
    
    参数：
    - fast: 快速 EMA 周期
    - slow: 慢速 EMA 周期
    - signal: DEA 周期
    """

    @property
    def name(self) -> str:
        return "MACD策略"

    @property
    def description(self) -> str:
        return "基于 MACD 指标的金叉/死叉产生交易信号"

    @property
    def parameters(self) -> list[StrategyParameter]:
        return [
            StrategyParameter("fast", "int", 12, 5, 60, "快速 EMA 周期"),
            StrategyParameter("slow", "int", 26, 10, 120, "慢速 EMA 周期"),
            StrategyParameter("signal", "int", 9, 5, 60, "信号线(DEA)周期"),
        ]

    def evaluate(self, symbol: str, data: list[dict[str, Any]]) -> StrategyResult:
        """执行 MACD 分析"""
        fast = self.get_param("fast")
        slow = self.get_param("slow")
        signal_period = self.get_param("signal")
        
        min_bars = slow + signal_period + 5
        if not self.validate_data(data, min_bars):
            return StrategyResult(
                strategy_name=self.name,
                symbol=symbol,
                error=f"数据不足，至少需要 {min_bars} 根 K 线",
            )
        
        try:
            df = pd.DataFrame(data)
            close = df["close"]
            
            # 计算 EMA
            ema_fast = close.ewm(span=fast, adjust=False).mean()
            ema_slow = close.ewm(span=slow, adjust=False).mean()
            
            # DIF = EMA(fast) - EMA(slow)
            dif = ema_fast - ema_slow
            
            # DEA = EMA(DIF, signal)
            dea = dif.ewm(span=signal_period, adjust=False).mean()
            
            # MACD Histogram = 2 * (DIF - DEA)
            hist = 2 * (dif - dea)
            
            # 取最近两根有效数据
            valid_idx = hist.dropna().index[-2:]
            if len(valid_idx) < 2:
                return StrategyResult(
                    strategy_name=self.name,
                    symbol=symbol,
                    error="有效数据不足",
                )
            
            prev_dif = dif.iloc[valid_idx[-2]]
            prev_dea = dea.iloc[valid_idx[-2]]
            curr_dif = dif.iloc[valid_idx[-1]]
            curr_dea = dea.iloc[valid_idx[-1]]
            curr_hist = hist.iloc[valid_idx[-1]]
            
            # 判断交叉
            prev_diff = prev_dif - prev_dea
            curr_diff = curr_dif - curr_dea
            
            signal = None
            
            if prev_diff <= 0 and curr_diff > 0:
                # 金叉
                signal = Signal(
                    symbol=symbol,
                    direction=TrendDirection.UP,
                    confidence=min(abs(curr_hist) * 10, 1.0),
                    reason=f"MACD 金叉：DIF({curr_dif:.3f})上穿 DEA({curr_dea:.3f})，柱状图{'红柱放大' if curr_hist > prev_diff else '红柱缩小'}",
                )
            elif prev_diff >= 0 and curr_diff < 0:
                # 死叉
                signal = Signal(
                    symbol=symbol,
                    direction=TrendDirection.DOWN,
                    confidence=min(abs(curr_hist) * 10, 1.0),
                    reason=f"MACD 死叉：DIF({curr_dif:.3f})下穿 DEA({curr_dea:.3f})，柱状图{'绿柱放大' if curr_hist < prev_diff else '绿柱缩小'}",
                )
            else:
                # 无交叉
                trend = "多头" if curr_diff > 0 else "空头"
                signal = Signal(
                    symbol=symbol,
                    direction=TrendDirection.FLAT,
                    confidence=0.0,
                    reason=f"暂无 MACD 交叉信号，当前{trend}趋势，DIF:{curr_dif:.3f}，DEA:{curr_dea:.3f}，柱状图:{curr_hist:.3f}",
                )
            
            return StrategyResult(
                strategy_name=self.name,
                symbol=symbol,
                signal=signal,
                data={
                    "dif": round(curr_dif, 3),
                    "dea": round(curr_dea, 3),
                    "hist": round(curr_hist, 3),
                    "fast": fast,
                    "slow": slow,
                    "signal": signal_period,
                },
            )
            
        except Exception as exc:
            logger.error("macd_evaluation_failed", symbol=symbol, error=str(exc))
            return StrategyResult(
                strategy_name=self.name,
                symbol=symbol,
                error=f"分析失败: {exc}",
            )
