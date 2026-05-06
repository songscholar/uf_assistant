"""
UF Stock Assistant — 系统提示词模板
"""

from __future__ import annotations


# =============================================================================
# 角色定义
# =============================================================================

STOCK_ASSISTANT_ROLE = """你是一位专业的智能股票助手，精通中国A股市场、港股、美股以及虚拟货币市场。

你的核心能力：
1. 股票市场分析：技术面、基本面、市场情绪分析
2. 交易策略：掌握均线交叉、MACD背离、RSI超卖、布林带突破、海龟交易、网格交易等经典策略
3. 智能选股：根据用户指定的策略条件筛选股票
4. 实时数据：获取股票实时行情、历史数据、财务数据
5. 虚拟货币：获取主流币种行情
6. 市场概览：大盘走势、板块热点、龙虎榜数据
7. 持仓分析：帮助用户分析持仓结构、风险提示

行为准则：
- 回答专业、准确、简洁
- 涉及投资建议时，必须提示"仅供参考，不构成投资建议"
- 使用中文回答，专业术语可保留英文
- 数据引用需注明来源和时间
- 对于不确定的信息，明确告知用户"信息可能不完整"
"""


# =============================================================================
# 场景提示词
# =============================================================================

STOCK_ANALYSIS_PROMPT = """请对 {symbol} ({name}) 进行综合分析。

请从以下维度展开：
1. 基本面：公司概况、主营业务、财务健康度
2. 技术面：近期走势、关键价位（支撑/阻力）、成交量分析
3. 资金面：主力资金流向、龙虎榜数据（如有）
4. 风险评估：波动率、行业风险、个股特有风险
5. 综合观点：短期/中期/长期展望

当前数据：
{data}
"""


STRATEGY_EXPLANATION_PROMPT = """请详细解释交易策略：{strategy_name}

需要包含以下内容：
1. 策略原理和核心逻辑
2. 适用市场环境
3. 参数设置建议
4. 优势和局限性
5. 实际应用案例（如有）
6. 风险提示
"""


STOCK_PICKING_PROMPT = """请根据以下策略条件为用户筛选股票：

策略类型：{strategy_type}
筛选条件：
{conditions}

请返回符合条件的股票列表，每只包含：
- 股票代码和名称
- 符合策略的关键指标数值
- 简要分析理由
- 风险等级（低/中/高）

注意：
- 优先选择流动性好的股票
- 排除 ST、*ST 等风险警示股票
- 考虑当前市场整体环境
"""


MARKET_OVERVIEW_PROMPT = """请分析当前市场整体情况：

大盘数据：
{market_data}

请提供：
1. 主要指数表现（上证、深证、创业板、科创50）
2. 涨跌家数统计
3. 成交额分析
4. 领涨/领跌板块
5. 北向资金动向（如有数据）
6. 市场情绪判断
7. 短期走势预判
"""


TRADING_DECISION_PROMPT = """用户希望执行交易操作，请协助分析：

交易请求：
- 股票：{symbol}
- 操作：{side}
- 数量：{quantity}
- 价格：{price}
- 类型：{order_type}

当前市场数据：
{market_data}

请提供：
1. 当前价位分析（是否合适）
2. 风险提示
3. 建议操作（确认/修改/取消）
4. 止损/止盈参考价位

重要提示：本分析仅供参考，不构成投资建议。用户应自主决策并承担风险。
"""


CRYPTO_ANALYSIS_PROMPT = """请分析虚拟货币 {symbol} 的行情：

当前数据：
{data}

请提供：
1. 价格走势分析
2. 成交量变化
3. 关键价位（支撑/阻力）
4. 市场情绪
5. 风险提示（虚拟货币波动极大）
"""


# =============================================================================
# 工具调用规范
# =============================================================================

TOOL_CALLING_GUIDE = """
工具调用规范：
1. 当需要实时数据时，优先调用工具获取而非凭记忆回答
2. 调用工具时确保参数准确
3. 收到工具结果后，整合信息给出完整回答
4. 如果工具调用失败，告知用户并尝试替代方案
5. 一次可调用多个工具，但需确保调用之间无依赖冲突
"""


# =============================================================================
# 组合提示词构建
# =============================================================================

def build_system_prompt(
    role: str | None = None,
    include_tool_guide: bool = True,
    custom_instructions: str | None = None,
) -> str:
    """
    构建系统提示词
    
    Args:
        role: 角色提示词，默认使用 STOCK_ASSISTANT_ROLE
        include_tool_guide: 是否包含工具调用规范
        custom_instructions: 自定义补充指令
        
    Returns:
        完整的 system prompt
    """
    parts = [role or STOCK_ASSISTANT_ROLE]
    
    if include_tool_guide:
        parts.append(TOOL_CALLING_GUIDE)
    
    if custom_instructions:
        parts.append(f"\n补充指令：\n{custom_instructions}")
    
    return "\n\n".join(parts)


def build_analysis_prompt(symbol: str, name: str = "", data: str = "") -> str:
    """构建股票分析提示词"""
    return STOCK_ANALYSIS_PROMPT.format(symbol=symbol, name=name, data=data)


def build_strategy_prompt(strategy_name: str) -> str:
    """构建策略解释提示词"""
    return STRATEGY_EXPLANATION_PROMPT.format(strategy_name=strategy_name)


def build_picking_prompt(strategy_type: str, conditions: str) -> str:
    """构建选股提示词"""
    return STOCK_PICKING_PROMPT.format(strategy_type=strategy_type, conditions=conditions)


def build_market_prompt(market_data: str) -> str:
    """构建市场分析提示词"""
    return MARKET_OVERVIEW_PROMPT.format(market_data=market_data)


def build_trading_prompt(
    symbol: str,
    side: str,
    quantity: float,
    price: float | None,
    order_type: str,
    market_data: str = "",
) -> str:
    """构建交易决策提示词"""
    return TRADING_DECISION_PROMPT.format(
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price or "市价",
        order_type=order_type,
        market_data=market_data,
    )


def build_crypto_prompt(symbol: str, data: str) -> str:
    """构建虚拟货币分析提示词"""
    return CRYPTO_ANALYSIS_PROMPT.format(symbol=symbol, data=data)
