"""
UF Stock Assistant — Agent 模块
"""

from .prompts import (
    STOCK_ASSISTANT_ROLE,
    build_analysis_prompt,
    build_crypto_prompt,
    build_market_prompt,
    build_picking_prompt,
    build_strategy_prompt,
    build_system_prompt,
    build_trading_prompt,
)
from .stock_assistant import AgentState, StockAssistantAgent, create_stock_assistant_graph

__all__ = [
    # prompts
    "STOCK_ASSISTANT_ROLE",
    "build_system_prompt",
    "build_analysis_prompt",
    "build_strategy_prompt",
    "build_picking_prompt",
    "build_market_prompt",
    "build_trading_prompt",
    "build_crypto_prompt",
    # agent
    "AgentState",
    "StockAssistantAgent",
    "create_stock_assistant_graph",
]
