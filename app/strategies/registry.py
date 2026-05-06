"""
UF Stock Assistant — 策略注册表
管理所有内置策略和自定义策略
"""

from __future__ import annotations

from typing import Any, Type

from app.core.logging import get_logger

from .base import BaseStrategy
from .builtin.bollinger import BollingerStrategy
from .builtin.ma_crossover import MACrossoverStrategy
from .builtin.macd import MACDStrategy
from .builtin.rsi import RSIStrategy

logger = get_logger("app.strategies.registry")


# 内置策略映射
_BUILTIN_STRATEGIES: dict[str, Type[BaseStrategy]] = {
    "ma_crossover": MACrossoverStrategy,
    "macd": MACDStrategy,
    "rsi": RSIStrategy,
    "bollinger": BollingerStrategy,
}

# 策略名称到 key 的映射
_STRATEGY_NAME_MAP: dict[str, str] = {
    "均线交叉": "ma_crossover",
    "均线交叉策略": "ma_crossover",
    "macd": "macd",
    "MACD": "macd",
    "MACD策略": "macd",
    "rsi": "rsi",
    "RSI": "rsi",
    "RSI超卖": "rsi",
    "RSI超卖策略": "rsi",
    "布林带": "bollinger",
    "布林带突破": "bollinger",
    "布林带突破策略": "bollinger",
}


class StrategyRegistry:
    """
    策略注册表
    
    管理策略的注册、查询和实例化
    """
    
    def __init__(self) -> None:
        self._strategies: dict[str, Type[BaseStrategy]] = dict(_BUILTIN_STRATEGIES)
        self._custom_strategies: dict[str, Any] = {}
    
    def list_strategies(self) -> list[dict[str, Any]]:
        """列出所有可用策略"""
        result = []
        for key, strategy_class in self._strategies.items():
            instance = strategy_class()
            info = instance.to_dict()
            info["key"] = key
            info["type"] = "builtin" if key in _BUILTIN_STRATEGIES else "custom"
            result.append(info)
        return result
    
    def get_strategy(self, key: str) -> Type[BaseStrategy] | None:
        """根据 key 获取策略类"""
        # 直接匹配
        if key in self._strategies:
            return self._strategies[key]
        
        # 名称模糊匹配
        normalized = _STRATEGY_NAME_MAP.get(key)
        if normalized and normalized in self._strategies:
            return self._strategies[normalized]
        
        return None
    
    def create_strategy(self, key: str, **params: Any) -> BaseStrategy | None:
        """
        创建策略实例
        
        Args:
            key: 策略标识
            **params: 策略参数
            
        Returns:
            策略实例或 None
        """
        strategy_class = self.get_strategy(key)
        if not strategy_class:
            logger.warning("strategy_not_found", key=key)
            return None
        
        try:
            instance = strategy_class(**params)
            logger.info("strategy_created", key=key, params=params)
            return instance
        except Exception as exc:
            logger.error("strategy_creation_failed", key=key, error=str(exc))
            return None
    
    def register_custom(self, key: str, strategy_class: Type[BaseStrategy]) -> bool:
        """
        注册自定义策略
        
        Args:
            key: 策略标识
            strategy_class: 策略类
            
        Returns:
            是否注册成功
        """
        if key in self._strategies:
            logger.warning("strategy_already_exists", key=key)
            return False
        
        self._strategies[key] = strategy_class
        logger.info("custom_strategy_registered", key=key)
        return True
    
    def is_builtin(self, key: str) -> bool:
        """判断是否为内置策略"""
        return key in _BUILTIN_STRATEGIES


# 全局注册表实例
_registry = StrategyRegistry()


def get_registry() -> StrategyRegistry:
    """获取全局策略注册表"""
    return _registry


def list_all_strategies() -> list[dict[str, Any]]:
    """列出所有策略"""
    return _registry.list_strategies()


def create_strategy(key: str, **params: Any) -> BaseStrategy | None:
    """创建策略实例"""
    return _registry.create_strategy(key, **params)
