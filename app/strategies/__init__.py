"""
UF Stock Assistant — 策略模块
"""

from .base import BaseStrategy, Signal, StrategyParameter, StrategyResult
from .builtin.bollinger import BollingerStrategy
from .builtin.ma_crossover import MACrossoverStrategy
from .builtin.macd import MACDStrategy
from .builtin.rsi import RSIStrategy
from .custom import CustomStrategyManager
from .registry import create_strategy, get_registry, list_all_strategies

__all__ = [
    # base
    "BaseStrategy",
    "Signal",
    "StrategyParameter",
    "StrategyResult",
    # builtin
    "MACrossoverStrategy",
    "MACDStrategy",
    "RSIStrategy",
    "BollingerStrategy",
    # registry
    "get_registry",
    "create_strategy",
    "list_all_strategies",
    # custom
    "CustomStrategyManager",
]
