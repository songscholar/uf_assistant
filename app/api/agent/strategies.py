"""
UF Stock Assistant — Agent Gateway 策略端点
提供策略列表、执行、选股、回测接口

参考 QuantDinger 设计：
  - 策略执行返回 job_id（异步模式）
  - W/B 类端点强制要求 Idempotency-Key
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.core.agent_auth import AgentAuthManager, AgentTokenRecord
from app.core.constants import AgentScope
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.services.stock_picker import StockPicker
from app.strategies.base import BaseStrategy
from app.strategies.registry import StrategyRegistry

from . import require_scope, _inject_rate_limit

logger = get_logger("app.api.agent.strategies")

router = APIRouter()

AKSHARE_TIMEOUT = 20.0


def _check_instrument(record: AgentTokenRecord, symbol: str) -> None:
    """检查品种白名单"""
    if not AgentAuthManager.instrument_allowed(record, symbol):
        raise ValidationError(
            f"Instrument not allowed for this token: {symbol}",
            details={"code": "INSTRUMENT_NOT_ALLOWED", "instrument": symbol},
        )


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
    request: Request,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """获取可用策略列表"""
    _inject_rate_limit(request, record)
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
# 策略执行（异步 Job 模式）
# =============================================================================

class StrategyEvaluateRequest(BaseModel):
    """策略执行请求"""
    symbol: str = Field(..., description="股票代码")
    params: dict[str, Any] = Field(default_factory=dict, description="策略参数")


@router.post("/{strategy_key}/evaluate")
async def agent_strategy_evaluate(
    request: Request,
    strategy_key: str,
    body: StrategyEvaluateRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    record: AgentTokenRecord = Depends(require_scope(AgentScope.BACKTEST)),
):
    """
    执行策略分析（异步 Job）

    返回 job_id，通过 GET /api/agent/v1/jobs/{job_id} 查询结果。
    W/B 类端点建议提供 Idempotency-Key 避免重复提交。
    """
    _inject_rate_limit(request, record)
    _check_instrument(record, body.symbol)

    # 幂等性检查
    with AgentAuthManager.with_idempotency("strategy_eval", idempotency_key) as existing:
        if existing:
            return {"duplicate": True, "job_id": existing["job_id"], "previous": existing}

    # 提交 Job
    job_id = AgentAuthManager.submit_job(
        kind="strategy_eval",
        request={"strategy_key": strategy_key, "symbol": body.symbol, "params": body.params},
        idempotency_key=idempotency_key,
    )

    # 立即执行（简化版：无独立 worker，直接在当前请求中执行）
    AgentAuthManager.update_job(job_id, status="running")
    try:
        registry = StrategyRegistry()
        strategy_cls = registry.get(strategy_key)
        if not strategy_cls:
            AgentAuthManager.update_job(job_id, status="failed", error=f"策略不存在: {strategy_key}")
            raise HTTPException(status_code=404, detail=f"策略不存在: {strategy_key}")

        strategy = strategy_cls(**body.params)

        # 获取历史数据
        from app.tools.stock_data import get_stock_history
        history_json = await _call_with_timeout(get_stock_history, body.symbol, limit=100)
        import json
        history_data = json.loads(history_json).get("data", [])

        result = strategy.evaluate(body.symbol, history_data)

        result_dict = {
            "strategy": strategy.name,
            "symbol": body.symbol,
            "signal": {
                "direction": result.signal.direction if result.signal else None,
                "confidence": result.signal.confidence if result.signal else 0,
                "reason": result.signal.reason if result.signal else "",
            } if result.signal else None,
            "data": result.data,
        }

        AgentAuthManager.update_job(job_id, status="completed", result=result_dict)
        return {"job_id": job_id, "status": "completed", "result": result_dict}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("agent_strategy_evaluate_error", strategy=strategy_key, error=str(exc))
        AgentAuthManager.update_job(job_id, status="failed", error=str(exc)[:500])
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# 智能选股（异步 Job 模式）
# =============================================================================

class StockPickRequest(BaseModel):
    """选股请求"""
    strategy_key: str = Field(..., description="策略标识")
    symbols: list[str] = Field(..., description="候选股票列表")
    params: dict[str, Any] = Field(default_factory=dict, description="策略参数")
    min_confidence: float = Field(0.3, ge=0, le=1, description="最小置信度")


@router.post("/pick")
async def agent_stock_pick(
    request: Request,
    body: StockPickRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    record: AgentTokenRecord = Depends(require_scope(AgentScope.BACKTEST)),
):
    """基于策略条件筛选股票（异步 Job）"""
    _inject_rate_limit(request, record)

    # 检查所有候选品种是否在白名单内
    for sym in body.symbols:
        _check_instrument(record, sym)

    # 幂等性检查
    with AgentAuthManager.with_idempotency("stock_pick", idempotency_key) as existing:
        if existing:
            return {"duplicate": True, "job_id": existing["job_id"], "previous": existing}

    job_id = AgentAuthManager.submit_job(
        kind="stock_pick",
        request={
            "strategy_key": body.strategy_key,
            "symbols": body.symbols,
            "params": body.params,
            "min_confidence": body.min_confidence,
        },
        idempotency_key=idempotency_key,
    )

    AgentAuthManager.update_job(job_id, status="running")
    try:
        picker = StockPicker()
        results = picker.pick(
            strategy_key=body.strategy_key,
            symbols=body.symbols,
            params=body.params,
            min_confidence=body.min_confidence,
        )
        result_dict = {"results": results}
        AgentAuthManager.update_job(job_id, status="completed", result=result_dict)
        return {"job_id": job_id, "status": "completed", "result": result_dict}
    except Exception as exc:
        logger.error("agent_stock_pick_error", error=str(exc))
        AgentAuthManager.update_job(job_id, status="failed", error=str(exc)[:500])
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
    request: Request,
    body: StockScreenRequest,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """根据条件快速筛选股票"""
    _inject_rate_limit(request, record)
    try:
        picker = StockPicker()
        results = picker.screen(
            min_price=body.min_price,
            max_price=body.max_price,
            min_change_pct=body.min_change_pct,
            max_change_pct=body.max_change_pct,
            limit=body.limit,
        )
        return {"results": results}
    except Exception as exc:
        logger.error("agent_stock_screen_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
