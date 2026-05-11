"""
UF Stock Assistant — 项目常量定义
"""

from enum import StrEnum


class MarketCode(StrEnum):
    """市场代码"""
    SH = "sh"       # 上海证券交易所
    SZ = "sz"       # 深圳证券交易所
    BJ = "bj"       # 北京证券交易所
    HK = "hk"       # 香港交易所
    US = "us"       # 美股


class SecurityType(StrEnum):
    """证券类型"""
    STOCK = "stock"         # 股票
    ETF = "etf"             # ETF
    BOND = "bond"           # 债券
    FUND = "fund"           # 基金
    INDEX = "index"         # 指数
    FUTURES = "futures"     # 期货
    OPTIONS = "options"     # 期权


class TrendDirection(StrEnum):
    """趋势方向"""
    UP = "up"
    DOWN = "down"
    FLAT = "flat"


class OrderSide(StrEnum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    """订单类型"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(StrEnum):
    """订单状态"""
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class MarketType(StrEnum):
    """交易市场类型"""
    CRYPTO = "crypto"
    A_SHARE = "a_share"
    US_STOCK = "us_stock"


class TradingMode(StrEnum):
    """交易模式"""
    MOCK = "mock"
    LIVE = "live"


class TradeType(StrEnum):
    """业务类型（支持多品种交易）"""
    NORMAL = "normal"               # 普通委托（A股）
    BLOCK_TRADE = "block"           # 大宗交易
    STOCK_CONNECT_SH = "hk_sh"      # 沪港通
    STOCK_CONNECT_SZ = "hk_sz"      # 深港通
    ETF_CREATION = "etf_create"     # ETF认购
    ETF_REDEMPTION = "etf_redeem"   # ETF申赎


class SettlementMode(StrEnum):
    """交收模式"""
    T0 = "T+0"      # 实时交收
    T1 = "T+1"      # 次日交收
    T2 = "T+2"      # 第3日交收


class SettlementStatus(StrEnum):
    """交收状态"""
    PENDING = "pending"       # 待交收
    SETTLED = "settled"       # 已交收
    FAILED = "failed"         # 交收失败
    CANCELLED = "cancelled"   # 已取消


class BlockTradeSubtype(StrEnum):
    """大宗交易子类型"""
    INTENTION = "intention"     # 意向委托
    PRICING = "pricing"         # 定价委托（深圳）
    CLICK = "click"             # 点击成交（深圳）
    DEAL = "deal"               # 成交申报
    AFTER_CLOSE = "after_close" # 盘后定价大宗


class ExchangeCode(StrEnum):
    """交易所代码"""
    SH = "SH"       # 上海证券交易所
    SZ = "SZ"       # 深圳证券交易所
    HKEX = "HK"     # 香港交易所
    BSE = "BJ"      # 北京证券交易所


class StrategyType(StrEnum):
    """内置策略类型"""
    MA_CROSSOVER = "ma_crossover"           # 均线交叉
    MACD_DIVERGENCE = "macd_divergence"     # MACD背离
    RSI_OVERSOLD = "rsi_oversold"           # RSI超卖
    BOLLINGER_BREAKOUT = "bollinger_breakout"  # 布林带突破
    VOLUME_SPIKE = "volume_spike"           # 放量突破
    SUPPORT_RESISTANCE = "support_resistance"  # 支撑阻力
    GRID_TRADING = "grid_trading"           # 网格交易
    TURTLE_TRADING = "turtle_trading"       # 海龟交易
    DUAL_THRUST = "dual_thrust"             # 双动量
    CUSTOM = "custom"                       # 自定义


# 时间周期常量
TIME_PERIODS = {
    "1m": "1分钟",
    "5m": "5分钟",
    "15m": "15分钟",
    "30m": "30分钟",
    "1h": "1小时",
    "1d": "日线",
    "1w": "周线",
    "1M": "月线",
}

# 默认参数
DEFAULT_PAGE_SIZE = 20
DEFAULT_MAX_PAGES = 10
DEFAULT_HISTORY_LIMIT = 50

# 上下文压缩阈值
CONTEXT_COMPRESS_THRESHOLD = 20
CONTEXT_COMPRESS_TARGET = 10

# 市场状态
MARKET_OPEN_TIME = "09:30"
MARKET_CLOSE_TIME = "15:00"
MARKET_MORNING_END = "11:30"
MARKET_AFTERNOON_START = "13:00"

# Agent Gateway Scope
class AgentScope(StrEnum):
    """Agent Token 权限范围（参考 QuantDinger AI_INTEGRATION_DESIGN.md §3）"""
    READ = "R"          # 读取市场数据
    WRITE = "W"         # 创建/修改策略
    BACKTEST = "B"      # 运行回测/模拟
    NOTIFY = "N"        # 通知 & 杂项副作用
    CREDENTIALS = "C"   # 凭证管理（admin only）
    TRADE = "T"         # 交易（下单/撤单）


class AgentTokenStatus(StrEnum):
    """Agent Token 状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    REVOKED = "revoked"

# Agent Token 默认前缀
AGENT_TOKEN_PREFIX = "uf_agent_"

# 用户代理标识
DEFAULT_USER_AGENT = "UF-Stock-Assistant/0.1.0"
