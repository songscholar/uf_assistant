"""
UF Stock Assistant — 凭证管理接口
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.core.logging import get_logger
from app.trading.credential_store import (
    delete_credential,
    list_credentials,
    save_credential,
    update_credential,
)
from app.trading.models import get_db_session

logger = get_logger("app.api.credentials")

router = APIRouter()


class CredentialRequest(BaseModel):
    """添加凭证请求"""
    market: str = Field(..., description="市场类型: crypto, a_share, us_stock")
    name: str = Field(..., description="凭证名称，如 Gate.io 主账户")
    api_key: str = Field(..., description="API Key")
    api_secret: str = Field(..., description="API Secret")
    passphrase: str | None = Field(None, description="Passphrase（部分交易所需要）")
    extra_config: dict | None = Field(None, description="额外配置，如 {\"exchange\": \"gate\"}")


class CredentialUpdateRequest(BaseModel):
    """更新凭证请求"""
    name: str | None = None
    api_key: str | None = None
    api_secret: str | None = None
    passphrase: str | None = None
    extra_config: dict | None = None
    is_active: bool | None = None


class CredentialTestRequest(BaseModel):
    """测试凭证连接"""
    market: str = Field(..., description="市场类型")
    api_key: str = Field(..., description="API Key")
    api_secret: str = Field(..., description="API Secret")
    passphrase: str | None = None
    extra_config: dict | None = None


@router.get("/credentials")
async def list_all(user: dict = Depends(get_current_user)):
    """列出所有凭证（脱敏显示）"""
    try:
        db = get_db_session()
        try:
            return {"credentials": list_credentials(db)}
        finally:
            db.close()
    except Exception as exc:
        logger.error("list_credentials_error", error=str(exc))
        raise HTTPException(status_code=500, detail="获取凭证列表失败，请稍后重试")


@router.post("/credentials")
async def add(request: CredentialRequest, user: dict = Depends(get_current_user)):
    """添加交易凭证"""
    try:
        db = get_db_session()
        try:
            cred = save_credential(
                db=db,
                market=request.market,
                name=request.name,
                api_key=request.api_key,
                api_secret=request.api_secret,
                passphrase=request.passphrase,
                extra_config=request.extra_config,
            )
            return {"id": cred.id, "market": cred.market, "name": cred.name, "message": "凭证添加成功"}
        finally:
            db.close()
    except Exception as exc:
        logger.error("add_credential_error", error=str(exc))
        raise HTTPException(status_code=500, detail="添加凭证失败，请检查输入后重试")


@router.put("/credentials/{credential_id}")
async def update(credential_id: str, request: CredentialUpdateRequest, user: dict = Depends(get_current_user)):
    """更新凭证"""
    try:
        db = get_db_session()
        try:
            cred = update_credential(
                db=db,
                credential_id=credential_id,
                name=request.name,
                api_key=request.api_key,
                api_secret=request.api_secret,
                passphrase=request.passphrase,
                extra_config=request.extra_config,
                is_active=request.is_active,
            )
            if not cred:
                raise HTTPException(status_code=404, detail="凭证不存在")
            return {"id": cred.id, "message": "凭证更新成功"}
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("update_credential_error", error=str(exc))
        raise HTTPException(status_code=500, detail="更新凭证失败，请稍后重试")


@router.delete("/credentials/{credential_id}")
async def delete(credential_id: str, user: dict = Depends(get_current_user)):
    """删除凭证"""
    try:
        db = get_db_session()
        try:
            success = delete_credential(db, credential_id)
            if not success:
                raise HTTPException(status_code=404, detail="凭证不存在")
            return {"message": "凭证已删除"}
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("delete_credential_error", error=str(exc))
        raise HTTPException(status_code=500, detail="删除凭证失败，请稍后重试")


@router.post("/credentials/test")
async def test_connection(request: CredentialTestRequest, user: dict = Depends(get_current_user)):
    """测试交易所连接（增强版：含 IP 检测、-2015 诊断、demo 检测）"""
    try:
        from app.strategies.strategy_service import test_exchange_connection

        exchange_config = {
            "exchange_id": request.extra_config.get("exchange", request.market) if request.extra_config else request.market,
            "api_key": request.api_key,
            "api_secret": request.api_secret,
            "passphrase": request.passphrase,
            **(request.extra_config or {}),
        }

        result = test_exchange_connection(exchange_config)
        return result
    except Exception as exc:
        logger.error("credential_test_failed", error=str(exc))
        return {
            "success": False,
            "message": "连接失败，请检查网络或凭证配置后重试",
            "data": None,
        }


@router.get("/credentials/desktop-brokers-policy")
async def desktop_brokers_policy(user: dict = Depends(get_current_user)):
    """Whether IBKR / MT5 may be configured on this deployment."""
    from app.utils.local_brokers import desktop_broker_cloud_reject_message, local_desktop_brokers_allowed

    allowed = local_desktop_brokers_allowed()
    return {
        "allow_local_desktop_brokers": allowed,
        "disabled_message": None if allowed else desktop_broker_cloud_reject_message(),
    }


@router.get("/credentials/egress-ip")
async def get_egress_ip(user: dict = Depends(get_current_user)):
    """获取本机出口公网 IP（用于交易所 IP 白名单配置）"""
    ipv4 = ""
    ipv6 = ""
    try:
        import urllib.request
        with urllib.request.urlopen("https://api4.ipify.org?format=json", timeout=5) as resp:
            ipv4 = resp.read().decode("utf-8").strip()
    except Exception:
        pass
    try:
        import urllib.request
        with urllib.request.urlopen("https://api6.ipify.org?format=json", timeout=5) as resp:
            ipv6 = resp.read().decode("utf-8").strip()
    except Exception:
        pass
    return {
        "ipv4": ipv4 or None,
        "ipv6": ipv6 or None,
        "ip": ipv4 or ipv6 or None,
    }
