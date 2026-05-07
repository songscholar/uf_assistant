"""
UF Stock Assistant — 策略模块

支持双范式：
- evaluate 模式：传统 4 个内置策略（MA/MACD/RSI/Bollinger）
- IndicatorStrategy 模式：QuantDinger 风格指标代码
- ScriptStrategy 模式：事件驱动脚本
"""

from .base import (
    BaseStrategy,
    Signal,
    SignalType,
    StrategyParameter,
    StrategyResult,
    TradeDirection,
)
from .builtin.bollinger import BollingerStrategy
from .builtin.ma_crossover import MACrossoverStrategy
from .builtin.macd import MACDStrategy
from .builtin.rsi import RSIStrategy
from .custom import CustomStrategyManager
from .registry import (
    IndicatorCodeRegistry,
    create_strategy,
    get_indicator_registry,
    get_registry,
    list_all_strategies,
)

__all__ = [
    # base
    "BaseStrategy",
    "Signal",
    "SignalType",
    "StrategyParameter",
    "StrategyResult",
    "TradeDirection",
    # builtin
    "MACrossoverStrategy",
    "MACDStrategy",
    "RSIStrategy",
    "BollingerStrategy",
    # registry
    "get_registry",
    "create_strategy",
    "list_all_strategies",
    "get_indicator_registry",
    "IndicatorCodeRegistry",
    # custom
    "CustomStrategyManager",
]

# Lazy imports for heavy modules (backtest, trading_executor, etc.)
# to avoid circular imports and slow startup.
# Import directly where needed:
#   from app.strategies.backtest import BacktestService
#   from app.strategies.trading_executor import TradingExecutor
#   from app.strategies.exchange_client import ExchangeClient, create_exchange_client
#   from app.strategies.notifier import NotifierManager
#   from app.strategies.pending_order_worker import PendingOrderWorker
#   from app.strategies.portfolio_monitor import PortfolioMonitor
