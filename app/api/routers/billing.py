"""
UF Stock Assistant — 计费与商业化 API
积分查询、会员套餐、USDT-TRC20 支付
"""

from __future__ import annotations

from typing import Any

import asyncio
import json

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.core.config import get_settings
from app.core.exceptions import BillingError
from app.core.logging import get_logger
from app.services.billing import get_billing_service
from app.services.usdt_payment import get_usdt_payment_service

logger = get_logger("app.api.routers.billing")

router = APIRouter(prefix="/billing", tags=["计费"])


# ------------------------------------------------------------------
# Admin auth dependency
# ------------------------------------------------------------------

def require_admin(x_admin_key: str = Header(default="")) -> None:
    """管理接口认证：校验 X-Admin-Key Header"""
    expected = (get_settings().billing.admin_api_key or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin_api_key_not_configured",
        )
    if x_admin_key.strip() != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_admin_key",
        )


# ------------------------------------------------------------------
# Pydantic schemas
# ------------------------------------------------------------------

class UsdtCreateOrderRequest(BaseModel):
    plan: str = Field(..., description="套餐类型: monthly/yearly/lifetime")


class CreditsAdjustRequest(BaseModel):
    user_id: str = Field(..., description="用户 ID")
    amount: int = Field(..., ge=0, description="积分数量")
    remark: str = Field(default="", description="备注")


class VipSetRequest(BaseModel):
    user_id: str = Field(..., description="用户 ID")
    expires_at: str | None = Field(default=None, description="VIP 过期时间 ISO 格式，null 表示取消")
    remark: str = Field(default="", description="备注")


# ------------------------------------------------------------------
# 查询接口
# ------------------------------------------------------------------

@router.get("/plans")
async def get_membership_plans(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """获取会员套餐配置 + 当前用户计费快照"""
    try:
        svc = get_billing_service()
        plans = svc.get_membership_plans()
        billing_info = svc.get_user_billing_info(str(user["user_id"]))
        return {
            "code": "success",
            "data": {"plans": plans, "billing": billing_info},
        }
    except Exception as e:
        logger.error(f"get_membership_plans failed: {e}", exc_info=True)
        raise BillingError(str(e))


@router.get("/credits")
async def get_credits(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """获取用户积分余额与 VIP 状态"""
    svc = get_billing_service()
    info = svc.get_user_billing_info(str(user["user_id"]))
    return {
        "code": "success",
        "data": info,
    }


@router.get("/credits/log")
async def get_credits_log(
    user: dict = Depends(get_current_user),
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """获取用户积分变动日志"""
    svc = get_billing_service()
    logs = svc.get_credits_log(str(user["user_id"]), page=page, page_size=page_size)
    return {
        "code": "success",
        "data": logs,
    }


@router.get("/membership/orders")
async def get_membership_orders(
    user: dict = Depends(get_current_user),
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """获取用户会员购买订单"""
    svc = get_billing_service()
    orders = svc.get_membership_orders(str(user["user_id"]), page=page, page_size=page_size)
    return {
        "code": "success",
        "data": orders,
    }


# ------------------------------------------------------------------
# 管理接口（积分调整、VIP 设置）
# ------------------------------------------------------------------

@router.post("/credits/add", dependencies=[Depends(require_admin)])
async def add_credits(payload: CreditsAdjustRequest) -> dict[str, Any]:
    """增加用户积分（管理员）"""
    svc = get_billing_service()
    ok, msg = svc.add_credits(
        user_id=payload.user_id,
        amount=payload.amount,
        action="admin_adjust",
        remark=payload.remark,
    )
    if not ok:
        raise BillingError(msg)
    return {
        "code": "success",
        "data": {"new_balance": msg},
    }


@router.post("/credits/set", dependencies=[Depends(require_admin)])
async def set_credits(payload: CreditsAdjustRequest) -> dict[str, Any]:
    """设置用户积分（管理员直接设置）"""
    svc = get_billing_service()
    ok, msg = svc.set_credits(
        user_id=payload.user_id,
        amount=payload.amount,
        remark=payload.remark,
    )
    if not ok:
        raise BillingError(msg)
    return {
        "code": "success",
        "data": {"new_balance": msg},
    }


@router.post("/vip/set", dependencies=[Depends(require_admin)])
async def set_vip(payload: VipSetRequest) -> dict[str, Any]:
    """设置用户 VIP 状态（管理员）
    
    expires_at 支持：
      - ISO 格式字符串：设置具体过期时间
      - "lifetime"：设置为终身会员
      - null：取消 VIP
    """
    from datetime import datetime

    expires_at: datetime | None = None
    is_lifetime = False
    if payload.expires_at:
        if payload.expires_at.strip().lower() == "lifetime":
            is_lifetime = True
        else:
            try:
                expires_at = datetime.fromisoformat(payload.expires_at.replace("Z", "+00:00"))
            except Exception as exc:
                raise BillingError(f"invalid_expires_at: {exc}")

    svc = get_billing_service()
    ok, msg = svc.set_vip(
        user_id=payload.user_id,
        expires_at=expires_at,
        remark=payload.remark,
        is_lifetime=is_lifetime,
    )
    if not ok:
        raise BillingError(msg)
    return {
        "code": "success",
        "data": {"vip_expires_at": payload.expires_at, "is_lifetime": is_lifetime},
    }


class MembershipRevokeRequest(BaseModel):
    user_id: str = Field(..., description="用户 ID")
    remark: str = Field(default="", description="备注")


@router.post("/membership/revoke", dependencies=[Depends(require_admin)])
async def revoke_membership(payload: MembershipRevokeRequest) -> dict[str, Any]:
    """撤销用户 VIP 会员身份（不清除积分）"""
    svc = get_billing_service()
    ok, msg = svc.revoke_membership(
        user_id=payload.user_id,
        remark=payload.remark,
    )
    if not ok:
        raise BillingError(msg)
    return {"code": "success", "data": {"revoked": True}}


# ------------------------------------------------------------------
# 运营数据（管理员）
# ------------------------------------------------------------------

@router.get("/admin/metrics", dependencies=[Depends(require_admin)])
async def get_admin_metrics() -> dict[str, Any]:
    """获取计费系统运营指标"""
    svc = get_billing_service()
    metrics = svc.get_admin_metrics()
    return {"code": "success", "data": metrics}


# ------------------------------------------------------------------
# USDT 支付
# ------------------------------------------------------------------

@router.post("/usdt/create")
async def usdt_create_order(
    payload: UsdtCreateOrderRequest,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """创建 USDT 支付订单（每单独立地址）"""
    plan = (payload.plan or "").strip().lower()
    if not plan:
        raise BillingError("missing_plan")

    ok, msg, out = get_usdt_payment_service().create_order(str(user["user_id"]), plan)
    if ok:
        return {"code": "success", "data": out}
    raise BillingError(msg, details=out)


@router.get("/usdt/order/{order_id}")
async def usdt_get_order(
    order_id: int,
    user: dict = Depends(get_current_user),
    refresh: bool = True,
) -> dict[str, Any]:
    """获取 USDT 订单详情；默认刷新链上状态"""
    ok, msg, out = get_usdt_payment_service().get_order(str(user["user_id"]), order_id, refresh=refresh)
    if ok:
        return {"code": "success", "data": out}
    raise BillingError(msg, details=out)


# ------------------------------------------------------------------
# 实时推送（SSE）
# ------------------------------------------------------------------

@router.get("/credits/stream")
async def credits_stream(
    user: dict = Depends(get_current_user),
) -> StreamingResponse:
    """积分变动实时推送（SSE，每秒轮询）"""
    uid = str(user["user_id"])

    async def event_generator():
        last_credits: float | None = None
        while True:
            try:
                svc = get_billing_service()
                info = svc.get_user_billing_info(uid)
                current: float = info["credits"]
                if current != last_credits:
                    last_credits = current
                    yield f"event: credits_changed\ndata: {json.dumps(info)}\n\n"
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"credits_stream error: {e}")
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
                await asyncio.sleep(5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )
