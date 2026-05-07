"""
UF Stock Assistant — MCP Tools 定义

每个 tool 对应 Agent Gateway 的一个端点，AI 可以直接调用。
"""

from __future__ import annotations

from typing import Any

from .client import AgentGatewayClient


# 全局客户端实例（由 server.py 初始化）
_client: AgentGatewayClient | None = None


def set_client(client: AgentGatewayClient) -> None:
    """设置全局客户端"""
    global _client
    _client = client


def _get_client() -> AgentGatewayClient:
    if _client is None:
        raise RuntimeError("AgentGatewayClient not initialized")
    return _client


# =============================================================================
# 市场数据 Tools
# =============================================================================

def uf_search_stocks(q: str, limit: int = 10) -> str:
    """
    搜索 A 股股票。根据关键词（股票代码或名称）搜索匹配的股票。
    
    Args:
        q: 搜索关键词，如 "平安" 或 "000001"
        limit: 返回数量上限，默认 10
    
    Returns:
        JSON 字符串，包含匹配的股票列表
    """
    result = _get_client().get("/markets/stocks/search", params={"q": q, "limit": limit})
    return str(result)


def uf_get_stock_realtime(symbol: str) -> str:
    """
    获取单只股票的实时行情数据。
    
    Args:
        symbol: 股票代码，如 "000001"
    
    Returns:
        JSON 字符串，包含最新价、开盘价、最高价、最低价、涨跌幅等
    """
    result = _get_client().get(f"/markets/stocks/{symbol}/realtime")
    return str(result)


def uf_get_stock_history(symbol: str, period: str = "daily", limit: int = 100) -> str:
    """
    获取股票历史 K 线数据，用于技术分析。
    
    Args:
        symbol: 股票代码，如 "000001"
        period: 周期，可选 daily / weekly / monthly
        limit: 返回条数，默认 100
    
    Returns:
        JSON 字符串，包含 open/high/low/close/volume 的 K 线列表
    """
    result = _get_client().get(
        f"/markets/stocks/{symbol}/history",
        params={"period": period, "limit": limit},
    )
    return str(result)


def uf_get_market_overview() -> str:
    """
    获取市场整体概况，包括涨跌家数统计、涨停/跌停数量、大盘指数等。
    
    Returns:
        JSON 字符串，包含市场 summary 和主要指数
    """
    result = _get_client().get("/markets/overview")
    return str(result)


def uf_get_market_indices() -> str:
    """
    获取主要大盘指数实时行情（上证、深证、创业板、科创50等）。
    
    Returns:
        JSON 字符串，包含指数列表及最新价、涨跌幅
    """
    result = _get_client().get("/markets/indices")
    return str(result)


def uf_get_sectors() -> str:
    """
    获取板块热点排行，了解当前市场领涨/领跌的行业板块。
    
    Returns:
        JSON 字符串，包含板块名称和涨跌幅
    """
    result = _get_client().get("/markets/sectors")
    return str(result)


def uf_get_crypto_price(symbol: str) -> str:
    """
    获取加密货币最新价格。
    
    Args:
        symbol: 币种，如 "BTC" 或 "ETH/USDT"
    
    Returns:
        JSON 字符串，包含最新价、24h 涨跌、成交量等
    """
    result = _get_client().get("/markets/crypto/price", params={"symbol": symbol})
    return str(result)


# =============================================================================
# 对话 Tool
# =============================================================================

def uf_chat(message: str, conversation_id: str | None = None) -> str:
    """
    与 UF 股票助手进行对话，获取 AI 分析结果。
    
    Args:
        message: 用户消息，如 "分析贵州茅台的基本面" 或 "推荐几只低估值股票"
        conversation_id: 可选，继续已有会话的 ID
    
    Returns:
        JSON 字符串，包含 AI 的回答和使用的工具列表
    """
    payload: dict[str, Any] = {"message": message}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    result = _get_client().post("/chat", json=payload)
    return str(result)


# =============================================================================
# 策略 Tools
# =============================================================================

def uf_run_strategy(strategy_key: str, symbol: str, params: str = "{}") -> str:
    """
    对指定股票执行策略分析，获取交易信号。
    
    Args:
        strategy_key: 策略标识，如 "ma_crossover", "rsi", "macd", "bollinger"
        symbol: 股票代码，如 "000001"
        params: 策略参数 JSON 字符串，如 '{"short_window": 5, "long_window": 20}'
    
    Returns:
        JSON 字符串，包含信号方向（up/down/flat）、置信度和分析数据
    """
    import json
    result = _get_client().post(
        f"/strategies/{strategy_key}/evaluate",
        json={"symbol": symbol, "params": json.loads(params)},
    )
    return str(result)


def uf_pick_stocks(strategy_key: str, symbols: str, params: str = "{}", min_confidence: float = 0.3) -> str:
    """
    基于策略条件从候选股票列表中筛选符合条件的股票。
    
    Args:
        strategy_key: 策略标识，如 "rsi"
        symbols: 逗号分隔的股票代码列表，如 "000001,000002,600000"
        params: 策略参数 JSON 字符串
        min_confidence: 最小置信度（0-1），默认 0.3
    
    Returns:
        JSON 字符串，包含筛选结果和每只股票的信号详情
    """
    import json
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    result = _get_client().post(
        "/strategies/pick",
        json={
            "strategy_key": strategy_key,
            "symbols": symbol_list,
            "params": json.loads(params),
            "min_confidence": min_confidence,
        },
    )
    return str(result)


# =============================================================================
# Tools 注册表
# =============================================================================
# 注：MCP Server 只暴露 R（Read）和 B（Backtest）类工具。
# 交易工具（T scope）不通过 MCP 暴露，需直接使用 REST API。
# 参考 QuantDinger 设计：MCP 是窄接口，安全边界在 Gateway。
# =============================================================================

ALL_TOOLS = [
    uf_search_stocks,
    uf_get_stock_realtime,
    uf_get_stock_history,
    uf_get_market_overview,
    uf_get_market_indices,
    uf_get_sectors,
    uf_get_crypto_price,
    uf_chat,
    uf_run_strategy,
    uf_pick_stocks,
]
