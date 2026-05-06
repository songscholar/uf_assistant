"""
UF Stock Assistant — 策略基类
定义所有交易策略的接口和公共行为
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.constants import TrendDirection
from app.core.logging import get_logger

logger = get_logger("app.strategies.base")


@dataclass
class Signal:
    """交易信号"""
    symbol: str
    direction: TrendDirection  # up, down, flat
    confidence: float  # 0.0 - 1.0
    reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyResult:
    """策略执行结果"""
    strategy_name: str
    symbol: str
    signal: Signal | None = None
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class StrategyParameter:
    """策略参数定义"""
    name: str
    type: str  # int, float, str, bool
    default: Any
    min_value: Any = None
    max_value: Any = None
    description: str = ""


class BaseStrategy(ABC):
    """
    策略基类
    
    所有交易策略必须继承此类并实现以下方法：
    - name: 策略名称
    - description: 策略描述
    - parameters: 参数定义列表
    - evaluate: 执行策略分析
    """

    def __init__(self, **kwargs: Any) -> None:
        """初始化策略，使用传入的参数覆盖默认值"""
        self._params = self._build_params(kwargs)
        logger.info("strategy_initialized", strategy=self.name, params=self._params)

    @property
    @abstractmethod
    def name(self) -> str:
        """策略名称"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """策略描述"""
        ...

    @property
    @abstractmethod
    def parameters(self) -> list[StrategyParameter]:
        """策略参数定义"""
        ...

    def _build_params(self, overrides: dict[str, Any]) -> dict[str, Any]:
        """构建参数字典（默认值 + 覆盖值）"""
        params = {}
        for p in self.parameters:
            params[p.name] = overrides.get(p.name, p.default)
        return params

    def get_param(self, name: str) -> Any:
        """获取参数值"""
        return self._params.get(name)

    @abstractmethod
    def evaluate(self, symbol: str, data: list[dict[str, Any]]) -> StrategyResult:
        """
        执行策略分析
        
        Args:
            symbol: 股票代码
            data: K 线数据列表，每项包含 open/high/low/close/volume
            
        Returns:
            StrategyResult 分析结果
        """
        ...

    def validate_data(self, data: list[dict[str, Any]], min_bars: int = 1) -> bool:
        """验证数据是否足够"""
        if not data or len(data) < min_bars:
            logger.warning("insufficient_data", strategy=self.name, bars=len(data) if data else 0, min_required=min_bars)
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        """导出策略信息"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "default": p.default,
                    "min": p.min_value,
                    "max": p.max_value,
                    "description": p.description,
                }
                for p in self.parameters
            ],
            "current_params": self._params,
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name}, params={self._params})"
