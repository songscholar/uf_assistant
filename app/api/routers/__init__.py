"""
UF Stock Assistant — API 路由模块
"""

from .chat import router as chat_router
from .crypto import router as crypto_router
from .market import router as market_router
from .stock import router as stock_router
from .strategy import router as strategy_router
from .trading import router as trading_router
from .upload import router as upload_router

__all__ = [
    "chat_router",
    "stock_router",
    "market_router",
    "crypto_router",
    "trading_router",
    "strategy_router",
    "upload_router",
]
