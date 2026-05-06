"""
UF Stock Assistant — 自定义策略接口
支持用户通过自然语言描述创建策略
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.llm_adapter import LlmService
from app.core.logging import get_logger

from .base import BaseStrategy, Signal, StrategyParameter, StrategyResult

logger = get_logger("app.strategies.custom")


STRATEGY_GENERATION_PROMPT = """你是一个专业的量化交易策略生成器。请根据用户的描述，生成一个 Python 策略类的代码。

要求：
1. 类必须继承自 BaseStrategy
2. 实现 name、description、parameters 属性和 evaluate 方法
3. 使用 pandas 进行数据计算
4. evaluate 方法返回 StrategyResult
5. 代码必须完整、可运行
6. 只输出 Python 代码，不要输出任何解释文字

可用的导入：
```python
from __future__ import annotations
from typing import Any
import pandas as pd
from app.core.constants import TrendDirection
from app.strategies.base import BaseStrategy, Signal, StrategyParameter, StrategyResult
```

StrategyResult 结构：
```python
StrategyResult(
    strategy_name=self.name,
    symbol=symbol,
    signal=Signal(
        symbol=symbol,
        direction=TrendDirection.UP/DOWN/FLAT,
        confidence=0.0-1.0,
        reason="信号原因",
    ),
    data={"关键指标": 数值},
)
```

用户描述：{description}

请生成策略代码："""


class CustomStrategyManager:
    """
    自定义策略管理器
    
    使用 LLM 将自然语言策略描述转换为可执行代码
    """
    
    def __init__(self, llm_service: LlmService | None = None) -> None:
        self._llm = llm_service
        self._custom_strategies: dict[str, type] = {}
    
    @classmethod
    def from_env(cls) -> "CustomStrategyManager":
        """从环境变量创建"""
        service = LlmService.from_env()
        return cls(llm_service=service)
    
    def generate_strategy(self, description: str) -> dict[str, Any]:
        """
        根据自然语言描述生成策略
        
        Args:
            description: 策略描述
            
        Returns:
            {
                "success": bool,
                "code": str | None,
                "strategy_key": str | None,
                "error": str | None,
            }
        """
        if not self._llm or not self._llm.is_configured():
            return {
                "success": False,
                "error": "LLM 未配置，无法生成策略",
            }
        
        try:
            result = self._llm.chat([
                {"role": "system", "content": "你是一个量化交易策略生成器。"},
                {"role": "user", "content": STRATEGY_GENERATION_PROMPT.format(description=description)},
            ])
            
            code = result.get("content", "").strip()
            
            # 提取代码块
            if "```python" in code:
                code = code.split("```python")[1].split("```")[0].strip()
            elif "```" in code:
                code = code.split("```")[1].split("```")[0].strip()
            
            # 生成策略 key
            strategy_key = self._generate_key(description)
            
            logger.info("strategy_generated", key=strategy_key, description=description[:50])
            
            return {
                "success": True,
                "code": code,
                "strategy_key": strategy_key,
            }
            
        except Exception as exc:
            logger.error("strategy_generation_failed", error=str(exc))
            return {
                "success": False,
                "error": f"策略生成失败: {exc}",
            }
    
    def compile_strategy(self, key: str, code: str) -> type | None:
        """
        编译策略代码
        
        Args:
            key: 策略标识
            code: Python 代码
            
        Returns:
            策略类或 None
        """
        try:
            # 安全检查：禁止危险操作
            dangerous = ["import os", "import sys", "__import__", "eval(", "exec(", "open(", "subprocess"]
            for d in dangerous:
                if d in code:
                    logger.error("dangerous_code_detected", keyword=d)
                    return None
            
            # 创建安全的命名空间
            namespace: dict[str, Any] = {
                "__builtins__": {
                    "abs": abs, "round": round, "min": min, "max": max,
                    "sum": sum, "len": len, "str": str, "int": int, "float": float,
                    "bool": bool, "list": list, "dict": dict, "tuple": tuple,
                    "range": range, "enumerate": enumerate, "zip": zip,
                    "print": print,
                }
            }
            
            # 导入必要的模块到命名空间
            exec("from __future__ import annotations", namespace)
            exec("from typing import Any", namespace)
            exec("import pandas as pd", namespace)
            exec("from app.core.constants import TrendDirection", namespace)
            exec("from app.strategies.base import BaseStrategy, Signal, StrategyParameter, StrategyResult", namespace)
            
            # 执行策略代码
            exec(code, namespace)
            
            # 查找策略类
            strategy_class = None
            for name, obj in namespace.items():
                if (isinstance(obj, type) and 
                    issubclass(obj, BaseStrategy) and 
                    obj is not BaseStrategy):
                    strategy_class = obj
                    break
            
            if strategy_class:
                self._custom_strategies[key] = strategy_class
                logger.info("strategy_compiled", key=key, class_name=strategy_class.__name__)
            
            return strategy_class
            
        except Exception as exc:
            logger.error("strategy_compilation_failed", key=key, error=str(exc))
            return None
    
    def _generate_key(self, description: str) -> str:
        """从描述生成策略 key"""
        # 提取中文和字母数字
        clean = re.sub(r'[^\w\u4e00-\u9fff]', '_', description[:20])
        clean = re.sub(r'_+', '_', clean).strip('_')
        return f"custom_{clean}" if clean else "custom_strategy"
    
    def get_strategy_class(self, key: str) -> type | None:
        """获取已编译的策略类"""
        return self._custom_strategies.get(key)
    
    def list_custom_strategies(self) -> list[dict[str, Any]]:
        """列出所有自定义策略"""
        result = []
        for key, cls in self._custom_strategies.items():
            try:
                instance = cls()
                result.append({
                    "key": key,
                    "name": instance.name,
                    "description": instance.description,
                })
            except Exception:
                result.append({
                    "key": key,
                    "name": key,
                    "description": "",
                })
        return result
