"""
UF Stock Assistant — 业务异常体系
"""


class AssistantException(Exception):
    """业务异常基类"""
    
    def __init__(self, message: str, code: str = "UNKNOWN_ERROR", details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class ConfigError(AssistantException):
    """配置错误"""
    
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message, code="CONFIG_ERROR", details=details)


class LlmError(AssistantException):
    """LLM 调用错误"""
    
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message, code="LLM_ERROR", details=details)


class LlmConfigError(LlmError):
    """LLM 配置错误"""
    
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message, details=details)
        self.code = "LLM_CONFIG_ERROR"


class LlmRequestError(LlmError):
    """LLM 请求错误"""
    
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message, details=details)
        self.code = "LLM_REQUEST_ERROR"


class DataProviderError(AssistantException):
    """数据提供者错误"""
    
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message, code="DATA_PROVIDER_ERROR", details=details)


class StockDataError(DataProviderError):
    """股票数据错误"""
    
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message, details=details)
        self.code = "STOCK_DATA_ERROR"


class CryptoDataError(DataProviderError):
    """虚拟货币数据错误"""
    
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message, details=details)
        self.code = "CRYPTO_DATA_ERROR"


class TradingError(AssistantException):
    """交易错误"""
    
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message, code="TRADING_ERROR", details=details)


class OrderError(TradingError):
    """订单错误"""
    
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message, details=details)
        self.code = "ORDER_ERROR"


class StrategyError(AssistantException):
    """策略错误"""
    
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message, code="STRATEGY_ERROR", details=details)


class ValidationError(AssistantException):
    """参数校验错误"""
    
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message, code="VALIDATION_ERROR", details=details)


class FileParseError(AssistantException):
    """文件解析错误"""
    
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message, code="FILE_PARSE_ERROR", details=details)


class MemoryError(AssistantException):
    """记忆/历史对话错误"""
    
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message, code="MEMORY_ERROR", details=details)


class CompressionError(MemoryError):
    """上下文压缩错误"""
    
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message, details=details)
        self.code = "COMPRESSION_ERROR"
