"""
Indicator Parameters Parser and Helper Functions

支持两个核心功能：
1. 指标参数外部传递 - 解析指标代码中的 @param 声明
2. 策略配置解析 - 解析 @strategy 注解

参数声明格式：
# @param param_name type default_value 描述
# @param ma_fast int 5 短期均线周期
# @param ma_slow int 20 长期均线周期
# @param threshold float 0.5 阈值

支持的类型：int, float, bool, str
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger

logger = get_logger("app.strategies.indicator_params")


class StrategyConfigParser:
    """
    解析指标代码中的 @strategy 注解，提取策略配置（止盈止损、仓位等）。

    支持的注解格式:
        # @strategy stopLossPct 0.02 止损比例
        # @strategy takeProfitPct 0.05 止盈比例
        # @strategy entryPct 0.5 仓位比例 (0-1)
        # 杠杆倍数由指标 IDE 回测面板单独设置，不再使用 @strategy leverage
        # @strategy trailingEnabled true 启用追踪止损
        # @strategy trailingStopPct 0.02 追踪止损比例
        # @strategy trailingActivationPct 0.03 追踪激活比例
        # @strategy tradeDirection long 交易方向
    """

    # 允许 key 与数值之间使用可选冒号，与指标 IDE 前端解析一致
    STRATEGY_PATTERN = re.compile(
        r'#\s*@strategy\s+(\w+)\s*:?\s*(\S+)\s*(.*)',
        re.IGNORECASE
    )

    VALID_KEYS = {
        'stopLossPct':          {'type': 'float', 'min': 0, 'max': 1},
        'takeProfitPct':        {'type': 'float', 'min': 0, 'max': 5},
        'entryPct':             {'type': 'float', 'min': 0.01, 'max': 1},
        'trailingEnabled':      {'type': 'bool'},
        'trailingStopPct':      {'type': 'float', 'min': 0, 'max': 1},
        'trailingActivationPct':{'type': 'float', 'min': 0, 'max': 1},
        'tradeDirection':       {'type': 'str',   'enum': ['long', 'short', 'both']},
    }

    @classmethod
    def parse(cls, code: str) -> dict[str, Any]:
        """
        解析代码中的 @strategy 注解，返回策略配置字典。
        只包含代码中声明的键，未声明的不包含。
        """
        config: dict[str, Any] = {}
        if not code:
            return config
        for line in code.split('\n'):
            line = line.strip()
            m = cls.STRATEGY_PATTERN.match(line)
            if not m:
                continue
            key = m.group(1)
            raw_val = m.group(2)
            if key not in cls.VALID_KEYS:
                continue
            spec = cls.VALID_KEYS[key]
            val = cls._convert(raw_val, spec)
            if val is not None:
                config[key] = val
        return config

    @classmethod
    def _convert(cls, raw: str, spec: dict) -> Any:
        t = spec['type']
        try:
            if t == 'float':
                v = float(raw)
                v = max(spec.get('min', v), min(spec.get('max', v), v))
                return round(v, 6)
            elif t == 'int':
                v = int(raw)
                v = max(spec.get('min', v), min(spec.get('max', v), v))
                return v
            elif t == 'bool':
                return raw.lower() in ('true', '1', 'yes', 'on')
            elif t == 'str':
                if 'enum' in spec and raw not in spec['enum']:
                    return spec['enum'][0]
                return raw
        except (ValueError, TypeError):
            return None
        return None

    @classmethod
    def generate_annotations(cls, config: dict[str, Any]) -> str:
        """
        从策略配置字典生成 @strategy 注解行。
        用于AI生成代码时自动附加。
        """
        lines = []
        for key, spec in cls.VALID_KEYS.items():
            if key in config:
                val = config[key]
                if spec['type'] == 'bool':
                    val = 'true' if val else 'false'
                lines.append(f'# @strategy {key} {val}')
        return '\n'.join(lines)


class IndicatorParamsParser:
    """解析指标代码中的参数声明"""

    # 参数声明正则：# @param name type default description
    PARAM_PATTERN = re.compile(
        r'#\s*@param\s+(\w+)\s+(int|float|bool|str|string)\s+(\S+)\s*(.*)',
        re.IGNORECASE
    )

    @classmethod
    def parse_params(cls, indicator_code: str) -> list[dict[str, Any]]:
        """
        解析指标代码中的参数声明

        Returns:
            List of param definitions:
            [
                {
                    "name": "ma_fast",
                    "type": "int",
                    "default": 5,
                    "description": "短期均线周期"
                },
                ...
            ]
        """
        params: list[dict[str, Any]] = []
        if not indicator_code:
            return params

        for line in indicator_code.split('\n'):
            line = line.strip()
            match = cls.PARAM_PATTERN.match(line)
            if match:
                name = match.group(1)
                param_type = match.group(2).lower()
                default_str = match.group(3)
                description = match.group(4).strip() if match.group(4) else ''

                # 转换默认值类型
                default = cls._convert_value(default_str, param_type)

                # 规范化类型名
                if param_type == 'string':
                    param_type = 'str'

                params.append({
                    "name": name,
                    "type": param_type,
                    "default": default,
                    "description": description
                })

        return params

    @classmethod
    def _convert_value(cls, value_str: str, param_type: str) -> Any:
        """转换字符串值为对应类型"""
        try:
            param_type = param_type.lower()
            if param_type == 'int':
                return int(value_str)
            elif param_type == 'float':
                return float(value_str)
            elif param_type == 'bool':
                return value_str.lower() in ('true', '1', 'yes', 'on')
            else:  # str/string
                return value_str
        except (ValueError, TypeError):
            return value_str

    @classmethod
    def merge_params(cls, declared_params: list[dict], user_params: dict[str, Any]) -> dict[str, Any]:
        """
        合并声明的参数和用户提供的参数

        Args:
            declared_params: 从代码中解析的参数声明
            user_params: 用户提供的参数值

        Returns:
            合并后的参数字典（使用用户值或默认值）
        """
        result: dict[str, Any] = {}
        for param in declared_params:
            name = param['name']
            param_type = param['type']
            default = param['default']

            if name in user_params:
                # 用户提供了值，转换为正确类型
                result[name] = cls._convert_value(str(user_params[name]), param_type)
            else:
                # 使用默认值
                result[name] = default

        return result
