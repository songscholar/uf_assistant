"""
UF Stock Assistant — IndicatorCaller
指标调用器：允许一个指标调用另一个指标

迁移自 QuantDinger，适配：
- user_id: int → str
- qd_indicator_codes → IndicatorModel ORM
- raw SQL → SQLAlchemy ORM query
- 返回 pd.DataFrame → 返回 dict[str, Any]（与 UF _execute_indicator 一致）
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.core.logging import get_logger
from app.core.safe_exec import build_safe_builtins, safe_exec_with_validation, validate_code_safety
from app.strategies.indicator_params import IndicatorParamsParser
from app.strategies.models import IndicatorModel
from app.strategies.trading_executor import get_strategy_db_session

logger = get_logger("app.strategies.indicator_caller")


class IndicatorCaller:
    """
    指标调用器 - 允许一个指标调用另一个指标

    使用方式（在指标代码中）：
        # 按名称调用（内置或用户自定义指标）
        rsi_df = call_indicator('RSI', df, period=14)

        # 按ID调用
        result = call_indicator('some-indicator-id', df)
    """

    # 最大调用深度，防止循环依赖
    MAX_CALL_DEPTH = 5

    def __init__(self, user_id: str, current_indicator_id: str | None = None, session=None):
        self.user_id = user_id
        self.current_indicator_id = current_indicator_id
        self._call_stack: list[str] = []  # 调用栈，用于检测循环依赖
        self._session = session

    def call_indicator(
        self,
        indicator_ref: Any,  # str (名称或ID)
        df: pd.DataFrame,
        params: dict[str, Any] | None = None,
        _depth: int = 0,
    ) -> dict[str, Any]:
        """
        调用另一个指标并返回结果

        Args:
            indicator_ref: 指标名称或ID
            df: 输入的K线数据
            params: 传递给被调用指标的参数
            _depth: 内部使用，跟踪调用深度

        Returns:
            dict with 'buy'/'sell' boolean Series, or 'error' key on failure
        """
        # 检查调用深度
        if _depth >= self.MAX_CALL_DEPTH:
            logger.error(f"Indicator call depth exceeded {self.MAX_CALL_DEPTH}")
            return {"error": f"指标调用深度超过限制（最大 {self.MAX_CALL_DEPTH} 层）"}

        # 获取指标代码
        indicator_code, indicator_id = self._get_indicator_code(indicator_ref)
        if not indicator_code:
            logger.warning(f"Indicator not found: {indicator_ref}")
            return {"error": f"指标不存在: {indicator_ref}"}

        # 检查循环依赖
        if indicator_id in self._call_stack:
            logger.error(f"Circular dependency detected: {self._call_stack} -> {indicator_id}")
            return {"error": f"检测到循环依赖: {self._call_stack} -> {indicator_id}"}

        self._call_stack.append(indicator_id)

        try:
            # 安全校验
            is_safe, err = validate_code_safety(indicator_code)
            if not is_safe:
                logger.error(f"Indicator {indicator_ref} unsafe: {err}")
                return {"error": f"指标代码包含不安全操作: {err}"}

            # 解析并合并参数
            declared_params = IndicatorParamsParser.parse_params(indicator_code)
            merged_params = IndicatorParamsParser.merge_params(declared_params, params or {})
            # 补充用户传入的未声明参数（兼容无 @param 注解的指标）
            for k, v in (params or {}).items():
                if k not in merged_params:
                    merged_params[k] = v

            # 准备执行环境
            df_copy = df.copy()
            local_vars: dict[str, Any] = {
                "df": df_copy,
                "open": df_copy["open"].astype("float64") if "open" in df_copy.columns else pd.Series(dtype="float64"),
                "high": df_copy["high"].astype("float64") if "high" in df_copy.columns else pd.Series(dtype="float64"),
                "low": df_copy["low"].astype("float64") if "low" in df_copy.columns else pd.Series(dtype="float64"),
                "close": df_copy["close"].astype("float64") if "close" in df_copy.columns else pd.Series(dtype="float64"),
                "volume": df_copy["volume"].astype("float64") if "volume" in df_copy.columns else pd.Series(dtype="float64"),
                "signals": pd.Series(0, index=df_copy.index, dtype="float64"),
                "np": np,
                "pd": pd,
                "params": merged_params,
                # 递归调用支持：注入带深度递增的 lambda
                "call_indicator": lambda ref, d, p=None: self.call_indicator(ref, d, p, _depth + 1),
            }

            exec_env = local_vars.copy()
            exec_env["__builtins__"] = build_safe_builtins()

            exec_result = safe_exec_with_validation(
                code=indicator_code,
                exec_globals=exec_env,
                exec_locals=exec_env,
                timeout=30,
            )
            if not exec_result["success"]:
                logger.error(f"Indicator {indicator_ref} rejected: {exec_result.get('error')}")
                return {"error": f"指标执行失败: {exec_result.get('error')}"}

            # 提取 buy/sell 信号（与 UF _execute_indicator 一致）
            output = exec_env.get("output", {})
            buy_series = None
            sell_series = None

            if isinstance(output, dict):
                buy_series = output.get("buy")
                sell_series = output.get("sell")

            if buy_series is None and "buy" in df_copy.columns:
                buy_series = df_copy["buy"]
            if sell_series is None and "sell" in df_copy.columns:
                sell_series = df_copy["sell"]

            if buy_series is None or sell_series is None:
                return {"error": "指标代码未产生买入/卖出信号"}

            buy_arr = pd.Series(buy_series, index=df.index).fillna(False).astype(bool)
            sell_arr = pd.Series(sell_series, index=df.index).fillna(False).astype(bool)

            return {"buy": buy_arr, "sell": sell_arr}

        except Exception as e:
            logger.error(f"Error calling indicator {indicator_ref}: {e}")
            return {"error": f"指标执行出错: {e}"}
        finally:
            self._call_stack.pop()

    def _get_indicator_code(self, indicator_ref: Any) -> tuple[str | None, str | None]:
        """获取指标代码。支持按名称或ID查询。"""
        try:
            session = self._session or get_strategy_db_session()
            _owns_session = self._session is None
            try:
                query = session.query(IndicatorModel)

                if isinstance(indicator_ref, str) and len(indicator_ref) == 36:
                    # 可能是 UUID 格式的 ID
                    row = query.filter(
                        (IndicatorModel.id == indicator_ref)
                        & (
                            (IndicatorModel.user_id == self.user_id)
                            | (IndicatorModel.is_builtin == True)  # noqa: E712
                        )
                    ).first()
                else:
                    # 按名称查询：优先用户自己的，然后是内置的
                    row = (
                        query.filter(
                            (IndicatorModel.name == str(indicator_ref))
                            & (IndicatorModel.user_id == self.user_id)
                        ).first()
                        or query.filter(
                            (IndicatorModel.name == str(indicator_ref))
                            & (IndicatorModel.is_builtin == True)  # noqa: E712
                        ).first()
                    )

                if row:
                    return row.code, str(row.id)
                return None, None
            finally:
                if _owns_session:
                    session.close()
        except Exception as e:
            logger.error(f"Error fetching indicator code: {e}")
            return None, None
