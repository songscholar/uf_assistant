"""
UF Stock Assistant — Agent Gateway 回测端点（class B）

参考 QuantDinger 设计：
  - POST /backtests → 提交异步回测任务，返回 job_id
  - 复用现有的 BacktestService（与人类 UI 结果一致）
  - 支持 Idempotency-Key 防止重复提交
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.core.agent_auth import AgentAuthManager, AgentTokenRecord
from app.core.constants import AgentScope
from app.core.exceptions import ValidationError
from app.core.logging import get_logger

from . import require_scope, _inject_rate_limit

logger = get_logger("app.api.agent.backtests")

router = APIRouter()


def _parse_date(s: Any) -> datetime:
    """解析日期字符串"""
    if not s:
        return None
    if hasattr(s, "year"):
        return s
    text = str(s)
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    raise ValueError(f"Invalid date: {text}")


def _run_backtest(payload: dict, user_id: int = 1) -> dict[str, Any]:
    """
    调用 BacktestService 执行回测

    Agent 合约使用小写的 snake_case 必填字段，便于记忆。
    """
    from app.strategies.backtest import BacktestService

    code = (payload.get("code") or payload.get("indicator_code") or "").strip()
    if not code:
        raise ValueError("code (indicator code) is required")

    market = payload.get("market") or "A_SHARE"
    symbol = payload.get("symbol")
    timeframe = payload.get("timeframe") or "1D"
    if not symbol:
        raise ValueError("symbol is required")

    start_date = _parse_date(payload.get("start_date") or payload.get("startDate"))
    end_date = _parse_date(payload.get("end_date") or payload.get("endDate"))
    if not start_date or not end_date:
        raise ValueError("start_date and end_date are required (YYYY-MM-DD)")

    backtest = BacktestService()
    return backtest.run(
        indicator_code=code,
        market=market,
        symbol=symbol,
        timeframe=timeframe,
        start_date=start_date,
        end_date=end_date,
        initial_capital=float(payload.get("initial_capital") or payload.get("initialCapital") or 10000),
        commission=float(payload.get("commission") or 0.001),
        slippage=float(payload.get("slippage") or 0.0),
        leverage=int(payload.get("leverage") or 1),
        trade_direction=payload.get("trade_direction") or payload.get("tradeDirection") or "long",
        strategy_config=payload.get("strategy_config") or payload.get("strategyConfig") or {},
        indicator_params=payload.get("indicator_params") or payload.get("params") or {},
        user_id=int(user_id),
    )


class BacktestSubmitRequest(dict):
    """回测提交请求（兼容 dict 以支持额外字段）"""
    pass


@router.post("/backtests")
async def agent_create_backtest(
    request: Request,
    body: dict[str, Any],
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    record: AgentTokenRecord = Depends(require_scope(AgentScope.BACKTEST)),
):
    """
    提交回测任务（异步 Job）

    返回 job_id，通过 GET /api/agent/v1/jobs/{job_id} 轮询结果。

    请求体示例：
    {
        "code": "df['buy'] = df['close'] > df['close'].shift(1)...",
        "market": "A_SHARE",
        "symbol": "000001",
        "timeframe": "1D",
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "initial_capital": 100000,
        "commission": 0.001,
        "leverage": 1,
        "trade_direction": "long"
    }
    """
    _inject_rate_limit(request, record)

    # 品种白名单检查
    symbol = body.get("symbol")
    if symbol and not AgentAuthManager.instrument_allowed(record, symbol):
        raise ValidationError(
            f"Instrument not allowed for this token: {symbol}",
            details={"code": "INSTRUMENT_NOT_ALLOWED", "instrument": symbol},
        )

    # 幂等性检查
    with AgentAuthManager.with_idempotency("backtest", idempotency_key) as existing:
        if existing:
            return {
                "duplicate": True,
                "job_id": existing["job_id"],
                "status": existing["status"],
                "previous": existing,
            }

    # 提交 Job
    job_id = AgentAuthManager.submit_job(
        kind="backtest",
        request=body,
        idempotency_key=idempotency_key,
    )

    # 立即执行（简化版：无独立 worker）
    AgentAuthManager.update_job(job_id, status="running")
    try:
        payload = dict(body)
        result = _run_backtest(payload, user_id=1)
        AgentAuthManager.update_job(job_id, status="completed", result=result)
        return {"job_id": job_id, "status": "completed", "result": result}
    except Exception as exc:
        logger.error("agent_backtest_error", error=str(exc))
        AgentAuthManager.update_job(job_id, status="failed", error=str(exc)[:500])
        raise HTTPException(status_code=500, detail=str(exc))
