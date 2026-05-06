"""
UF Stock Assistant — 工具模块
"""

from .crypto_data import get_crypto_ohlcv, get_crypto_price, get_crypto_ticker, list_top_cryptos
from .file_parser import detect_file_type, parse_file, parse_files
from .market import get_longhu_bang, get_market_index, get_market_overview, get_northbound_flow, get_sector_hot
from .stock_data import get_capital_flow, get_stock_financial, get_stock_history, get_stock_info, get_stock_realtime, search_stocks
from .trading import cancel_order, get_orders, get_portfolio, get_position, get_positions, submit_order

# LangChain 工具注册表
ALL_TOOLS = [
    # 股票数据
    search_stocks,
    get_stock_info,
    get_stock_realtime,
    get_stock_history,
    get_stock_financial,
    get_capital_flow,
    # 虚拟货币
    get_crypto_price,
    get_crypto_ticker,
    list_top_cryptos,
    get_crypto_ohlcv,
    # 市场数据
    get_market_index,
    get_sector_hot,
    get_longhu_bang,
    get_market_overview,
    get_northbound_flow,
    # 文件解析
    parse_file,
    # 交易
    submit_order,
    get_positions,
    get_position,
    get_orders,
    cancel_order,
    get_portfolio,
]

__all__ = [
    # stock
    "search_stocks",
    "get_stock_info",
    "get_stock_realtime",
    "get_stock_history",
    "get_stock_financial",
    "get_capital_flow",
    # crypto
    "get_crypto_price",
    "get_crypto_ticker",
    "list_top_cryptos",
    "get_crypto_ohlcv",
    # market
    "get_market_index",
    "get_sector_hot",
    "get_longhu_bang",
    "get_market_overview",
    "get_northbound_flow",
    # file
    "parse_file",
    "parse_files",
    "detect_file_type",
    # trading
    "submit_order",
    "get_positions",
    "get_position",
    "get_orders",
    "cancel_order",
    "get_portfolio",
    # registry
    "ALL_TOOLS",
]
