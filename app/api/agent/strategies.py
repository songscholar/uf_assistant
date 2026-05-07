"""
UF Stock Assistant — Agent Gateway 策略端点
提供策略列表、执行、选股、回测接口
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.core.agent_auth import AgentAuthManager, AgentTokenRecord
from app.core.constants import AgentScope
from app.core.logging import get_logger
from app.services.stock_picker import StockPicker
from app.strategies.base import BaseStrategy
from app.strategies.registry import StrategyRegistry

from . import require_scope

logger = get_logger("app.api.agent.strategies")

router = APIRouter()

AKSHARE_TIMEOUT = 20.0


async def _call_with_timeout(func, *args, **kwargs):
    try:
        return await asyncio.wait_for(
            run_in_threadpool(func, *args, **kwargs),
            timeout=AKSHARE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="数据服务响应超时，请稍后重试")


# =============================================================================
# 策略列表
# =============================================================================

@router.get("/list")
async def agent_strategy_list(
    _record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取可用策略列表"""
    try:
        registry = StrategyRegistry()
        strategies = registry.list_strategies()
        return {
            "strategies": [
                {
                    "key": s["key"],
                    "name": s["name"],
                    "description": s.get("description", ""),
                    "parameters": s.get("parameters", []),
                }
                for s in strategies
            ]
        }
    except Exception as exc:
        logger.error("agent_strategy_list_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# 策略执行
# =============================================================================

class StrategyEvaluateRequest(BaseModel):
    """策略执行请求"""
    symbol: str = Field(..., description="股票代码")
    params: dict[str, Any] = Field(default_factory=dict, description="策略参数")


@router.post("/{strategy_key}/evaluate")
async def agent_strategy_evaluate(
    strategy_key: str,
    request: StrategyEvaluateRequest,
    _record: AgentTokenRecord = Depends(require_scope(AgentScope.BACKTEST)),
):
    """执行策略分析"""
    try:
        registry = StrategyRegistry()
        strategy_cls = registry.get(strategy_key)
        if not strategy_cls:
            raise HTTPException(status_code=404, detail=f"策略不存在: {strategy_key}")
        
        strategy = strategy_cls(**request.params)
        
        # 获取历史数据
        from app.tools.stock_data import get_stock_history
        history_json = await _call_with_timeout(get_stock_history, request.symbol, limit=100)
        import json
        history_data = json.loads(history_json).get("data", [])
        
        result = strategy.evaluate(request.symbol, history_data)
        
        return {
            "strategy": strategy.name,
            "symbol": request.symbol,
            "signal": {
                "direction": result.signal.direction if result.signal else None,
                "confidence": result.signal.confidence if result.signal else 0,
                "reason": result.signal.reason if result.signal else "",
            } if result.signal else None,
            "data": result.data,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("agent_strategy_evaluate_error", strategy=strategy_key, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# 智能选股
# =============================================================================

class StockPickRequest(BaseModel):
    """选股请求"""
    strategy_key: str = Field(..., description="策略标识")
    symbols: list[str] = Field(..., description="候选股票列表")
    params: dict[str, Any] = Field(default_factory=dict, description="策略参数")
    min_confidence: float = Field(0.3, ge=0, le=1, description="最小置信度")


@router.post("/pick")
async def agent_stock_pick(
    request: StockPickRequest,
    _record: AgentTokenRecord = Depends(require_scope(AgentScope.BACKTEST)),
):
    """基于策略条件筛选股票"""
    try:
        picker = StockPicker()
        results = picker.pick(
            strategy_key=request.strategy_key,
            symbols=request.symbols,
            params=request.params,
            min_confidence=request.min_confidence,
        )
        return {"results": results}
    except Exception as exc:
        logger.error("agent_stock_pick_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# 快速筛选
# =============================================================================

class StockScreenRequest(BaseModel):
    """快速筛选请求"""
    min_price: float | None = None
    max_price: float | None = None
    min_change_pct: float | None = None
    max_change_pct: float | None = None
    limit: int = Field(20, ge=1, le=100)


@router.post("/screen")
async def agent_stock_screen(
    request: StockScreenRequest,
    _record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """根据条件快速筛选股票"""
    try:
        picker = StockPicker()
        results = picker.screen(
            min_price=request.min_price,
            max_price=request.max_price,
            min_change_pct=request.min_change_pct,
            max_change_pct=request.max_change_pct,
            limit=request.limit,
        )
        return {"results": results}
    except Exception as exc:
        logger.error("agent_stock_screen_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
