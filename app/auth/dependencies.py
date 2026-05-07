"""
UF Stock Assistant — FastAPI 认证依赖
提供 Bearer token 提取、角色检查、权限检查等依赖函数
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.auth.jwt_auth import verify_token, verify_token_version
from app.core.logging import get_logger

logger = get_logger("app.auth.dependencies")
security = HTTPBearer(auto_error=False)

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "viewer": ["dashboard", "view"],
    "user": ["dashboard", "view", "indicator", "backtest", "strategy", "portfolio"],
    "manager": ["dashboard", "view", "indicator", "backtest", "strategy", "portfolio", "settings"],
    "admin": [
        "dashboard", "view", "indicator", "backtest", "strategy",
        "portfolio", "settings", "user_manage", "credentials",
    ],
}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """Extract current user from Bearer token. Returns {user_id, username, role}."""
    if not credentials:
        raise HTTPException(status_code=401, detail="未提供认证令牌")
    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    if not verify_token_version(payload):
        logger.warning("token_version_mismatch", payload_sub=payload.get("sub"))
        raise HTTPException(status_code=401, detail="令牌已被新登录失效")
    return {
        "user_id": payload["user_id"],
        "username": payload["sub"],
        "role": payload["role"],
    }


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict | None:
    """Like get_current_user but returns None instead of raising."""
    if not credentials:
        return None
    payload = verify_token(credentials.credentials)
    if not payload or not verify_token_version(payload):
        return None
    return {
        "user_id": payload["user_id"],
        "username": payload["sub"],
        "role": payload["role"],
    }


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Require admin role."""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


async def require_manager(user: dict = Depends(get_current_user)) -> dict:
    """Require admin or manager role."""
    if user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="需要管理员或经理权限")
    return user


def require_permission(permission: str):
    """Return a dependency that checks whether the current user has *permission*."""

    async def checker(user: dict = Depends(get_current_user)) -> dict:
        role = user["role"]
        perms = ROLE_PERMISSIONS.get(role, [])
        if permission not in perms:
            raise HTTPException(status_code=403, detail=f"缺少权限: {permission}")
        return user

    return checker


def get_client_ip(request: Request) -> str:
    """Extract the real client IP, respecting X-Forwarded-For."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
