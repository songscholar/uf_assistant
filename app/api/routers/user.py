"""
UF Stock Assistant — 用户管理接口
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user, require_admin, require_permission
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("app.api.user")
router = APIRouter()

# ── models ───────────────────────────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5)
    password: str = Field(..., min_length=8)
    role: str = Field(default="user", description="user / admin / vip")
    nickname: str | None = None
    credits: float = Field(default=0, ge=0)

class UpdateUserRequest(BaseModel):
    user_id: int
    username: str | None = Field(None, min_length=3, max_length=50)
    email: str | None = None
    role: str | None = None
    nickname: str | None = None
    is_active: bool | None = None

class AdminResetPasswordRequest(BaseModel):
    user_id: int
    new_password: str = Field(..., min_length=8)

class SetCreditsRequest(BaseModel):
    user_id: int
    amount: float = Field(..., ge=0)
    remark: str = ""

class SetVipRequest(BaseModel):
    user_id: int
    expires_at: str | None = Field(None, description="ISO datetime or 'lifetime'")
    remark: str = ""

class UpdateProfileRequest(BaseModel):
    nickname: str | None = Field(None, max_length=100)
    avatar: str | None = None
    timezone: str | None = Field(None, max_length=50)

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8)


# ── DB helpers ───────────────────────────────────────────────────────────────

def _db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    return sessionmaker(bind=create_engine(get_settings().database.url, echo=False))()


def _q(sql: str, p: dict[str, Any] | None = None) -> list[Any]:
    from sqlalchemy import text
    s = _db()
    try:
        return s.execute(text(sql), p or {}).fetchall()
    finally:
        s.close()


def _e(sql: str, p: dict[str, Any]) -> int | None:
    from sqlalchemy import text
    s = _db()
    try:
        r = s.execute(text(sql), p); s.commit(); return r.lastrowid
    except Exception:
        s.rollback(); raise
    finally:
        s.close()


def _hpw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _cpw(pw: str, h: str) -> bool:
    return bcrypt.checkpw(pw.encode(), h.encode())


_UC = "id, username, email, password_hash, role, nickname, avatar, timezone, is_active, created_at, updated_at"


def _ur(r: Any) -> dict[str, Any]:
    return {
        "id": r[0], "username": r[1], "email": r[2], "role": r[4],
        "nickname": r[5] or "", "avatar": r[6] or "", "timezone": r[7] or "Asia/Shanghai",
        "is_active": bool(r[8]),
        "created_at": r[9].isoformat() if r[9] else "",
        "updated_at": r[10].isoformat() if r[10] else "",
    }


def _get_meta(uid: int) -> dict[str, Any]:
    """Load user metadata JSON."""
    rows = _q("SELECT metadata FROM users WHERE id = :id", {"id": uid})
    if not rows:
        return {}
    raw = rows[0][0]
    if not raw:
        return {}
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return {}


def _save_meta(uid: int, meta: dict[str, Any]) -> None:
    """Save user metadata JSON."""
    _e("UPDATE users SET metadata = :m, updated_at = :now WHERE id = :id", {"m": json.dumps(meta, ensure_ascii=False), "id": uid, "now": datetime.now(timezone.utc)})


# ── Admin Endpoints ──────────────────────────────────────────────────────────

@router.get("/users/list")
async def list_users(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    search: str = Query(""), _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    """List all users (paginated, searchable)."""
    offset = (page - 1) * page_size
    if search:
        like = f"%{search}%"
        rows = _q(f"SELECT {_UC} FROM users WHERE username LIKE :s OR email LIKE :s OR nickname LIKE :s ORDER BY id DESC LIMIT :l OFFSET :o", {"s": like, "l": page_size, "o": offset})
        total = _q("SELECT COUNT(*) FROM users WHERE username LIKE :s OR email LIKE :s OR nickname LIKE :s", {"s": like})[0][0]
    else:
        rows = _q(f"SELECT {_UC} FROM users ORDER BY id DESC LIMIT :l OFFSET :o", {"l": page_size, "o": offset})
        total = _q("SELECT COUNT(*) FROM users")[0][0]
    return {"users": [_ur(r) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/users/export")
async def export_users_csv(_admin: dict[str, Any] = Depends(require_admin)) -> StreamingResponse:
    """Export users as CSV."""
    rows = _q("SELECT id, username, email, role, nickname, is_active, created_at FROM users ORDER BY id")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID", "Username", "Email", "Role", "Nickname", "Active", "Created At"])
    for r in rows:
        w.writerow([r[0], r[1], r[2], r[3], r[4], "Yes" if r[5] else "No", r[6].isoformat() if r[6] else ""])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=users.csv"})


@router.get("/users/detail")
async def get_user_detail(user_id: int, _admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    """Get user detail by ID."""
    rows = _q(f"SELECT {_UC} FROM users WHERE id = :id", {"id": user_id})
    if not rows:
        raise HTTPException(404, detail="user_not_found")
    u = _ur(rows[0]); u.pop("password_hash", None)
    return {"user": u}


@router.post("/users/create")
async def create_user(request: CreateUserRequest, _admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    """Create a new user."""
    if _q("SELECT id FROM users WHERE username = :u", {"u": request.username}):
        raise HTTPException(409, detail="username_taken")
    if _q("SELECT id FROM users WHERE email = :e", {"e": request.email}):
        raise HTTPException(409, detail="email_already_registered")
    now = datetime.now(timezone.utc)
    uid = _e("INSERT INTO users (username,email,password_hash,role,nickname,is_active,created_at,updated_at) VALUES (:u,:e,:p,:r,:n,1,:t,:t)", {"u": request.username, "e": request.email, "p": _hpw(request.password), "r": request.role, "n": request.nickname or request.username, "t": now})
    if request.credits > 0 and get_settings().billing.enabled:
        _e("INSERT OR REPLACE INTO user_credits (user_id,credits,created_at,updated_at) VALUES (:uid,:c,:t,:t)", {"uid": str(uid), "c": request.credits, "t": now})
    logger.info("admin_create_user", uid=uid)
    return {"user": {"id": uid, "username": request.username, "email": request.email, "role": request.role, "nickname": request.nickname or request.username}}


@router.put("/users/update")
async def update_user(request: UpdateUserRequest, _admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    """Update user info."""
    if not _q("SELECT id FROM users WHERE id = :id", {"id": request.user_id}):
        raise HTTPException(404, detail="user_not_found")
    sets: list[str] = []; p: dict[str, Any] = {"id": request.user_id, "now": datetime.now(timezone.utc)}
    if request.username is not None:
        if _q("SELECT id FROM users WHERE username = :u AND id != :id", {"u": request.username, "id": request.user_id}):
            raise HTTPException(409, detail="username_taken")
        sets.append("username = :u"); p["u"] = request.username
    if request.email is not None:
        if _q("SELECT id FROM users WHERE email = :e AND id != :id", {"e": request.email, "id": request.user_id}):
            raise HTTPException(409, detail="email_already_registered")
        sets.append("email = :e"); p["e"] = request.email
    if request.role is not None:
        sets.append("role = :r"); p["r"] = request.role
    if request.nickname is not None:
        sets.append("nickname = :n"); p["n"] = request.nickname
    if request.is_active is not None:
        sets.append("is_active = :a"); p["a"] = 1 if request.is_active else 0
    if not sets:
        raise HTTPException(400, detail="no_fields_to_update")
    sets.append("updated_at = :now")
    _e(f"UPDATE users SET {', '.join(sets)} WHERE id = :id", p)
    logger.info("admin_update_user", uid=request.user_id)
    return {"message": "user_updated", "user_id": request.user_id}


@router.delete("/users/delete")
async def delete_user(user_id: int, admin: dict[str, Any] = Depends(require_admin)) -> dict[str, str]:
    """Delete a user (cannot delete self)."""
    if admin.get("id") == user_id:
        raise HTTPException(400, detail="cannot_delete_self")
    if not _q("SELECT id FROM users WHERE id = :id", {"id": user_id}):
        raise HTTPException(404, detail="user_not_found")
    _e("DELETE FROM users WHERE id = :id", {"id": user_id})
    logger.info("admin_delete_user", uid=user_id)
    return {"message": "user_deleted"}


@router.post("/users/reset-password")
async def admin_reset_password(request: AdminResetPasswordRequest, _admin: dict[str, Any] = Depends(require_admin)) -> dict[str, str]:
    """Admin reset any user's password."""
    if not _q("SELECT id FROM users WHERE id = :id", {"id": request.user_id}):
        raise HTTPException(404, detail="user_not_found")
    _e("UPDATE users SET password_hash = :p, updated_at = :now WHERE id = :id", {"p": _hpw(request.new_password), "id": request.user_id, "now": datetime.now(timezone.utc)})
    return {"message": "password_reset_success"}


@router.get("/users/roles")
async def get_roles(_admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    """Get available roles and permissions."""
    return {"roles": [
        {"name": "user", "label": "普通用户", "permissions": ["chat", "market_view", "strategy_view"]},
        {"name": "vip", "label": "VIP 用户", "permissions": ["chat", "market_view", "strategy_view", "ai_analysis", "advanced_charts"]},
        {"name": "admin", "label": "管理员", "permissions": ["chat", "market_view", "strategy_view", "ai_analysis", "advanced_charts", "user_management", "billing_management", "system_config"]},
    ]}


@router.post("/users/set-credits")
async def set_credits(request: SetCreditsRequest, _admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    """Set user credits (admin)."""
    if not get_settings().billing.enabled:
        raise HTTPException(503, detail="billing_not_enabled")
    now = datetime.now(timezone.utc)
    _e("INSERT INTO user_credits (user_id,credits,created_at,updated_at) VALUES (:uid,:c,:t,:t) ON CONFLICT(user_id) DO UPDATE SET credits = :c, updated_at = :t", {"uid": str(request.user_id), "c": request.amount, "t": now})
    logger.info("admin_set_credits", uid=request.user_id, amount=request.amount)
    return {"message": "credits_set", "user_id": request.user_id, "credits": request.amount}


@router.post("/users/set-vip")
async def set_vip(request: SetVipRequest, _admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    """Set user VIP status (admin)."""
    if not get_settings().billing.enabled:
        raise HTTPException(503, detail="billing_not_enabled")
    expires_at: datetime | None = None; is_lifetime = False
    if request.expires_at:
        s = request.expires_at.strip().lower()
        if s == "lifetime":
            is_lifetime = True
        else:
            try:
                expires_at = datetime.fromisoformat(request.expires_at.replace("Z", "+00:00"))
            except Exception as e:
                raise HTTPException(400, detail=f"invalid_expires_at: {e}")
    now = datetime.now(timezone.utc)
    _e("INSERT INTO user_credits (user_id,vip_expires_at,vip_is_lifetime,created_at,updated_at) VALUES (:uid,:exp,:lt,:t,:t) ON CONFLICT(user_id) DO UPDATE SET vip_expires_at = :exp, vip_is_lifetime = :lt, updated_at = :t", {"uid": str(request.user_id), "exp": expires_at, "lt": 1 if is_lifetime else 0, "t": now})
    logger.info("admin_set_vip", uid=request.user_id, lifetime=is_lifetime)
    return {"message": "vip_set", "user_id": request.user_id, "vip_expires_at": request.expires_at, "is_lifetime": is_lifetime}


@router.get("/users/credits-log")
async def get_credits_log(user_id: int, _admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    """Get user credits log (admin)."""
    rows = _q("SELECT id,user_id,action,amount,balance_after,feature,remark,created_at FROM credits_log WHERE user_id = :uid ORDER BY id DESC LIMIT 100", {"uid": str(user_id)})
    return {"logs": [{"id": r[0], "user_id": r[1], "action": r[2], "amount": float(r[3]), "balance_after": float(r[4]), "feature": r[5], "remark": r[6], "created_at": r[7].isoformat() if r[7] else ""} for r in rows]}


# ── Self-Service Endpoints ───────────────────────────────────────────────────

@router.get("/users/profile")
async def get_profile(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Get own profile with billing info."""
    rows = _q(f"SELECT {_UC} FROM users WHERE id = :id", {"id": user["id"]})
    if not rows:
        raise HTTPException(404, detail="user_not_found")
    profile = _ur(rows[0])
    if get_settings().billing.enabled:
        br = _q("SELECT credits,vip_expires_at,vip_is_lifetime,vip_plan FROM user_credits WHERE user_id = :uid", {"uid": str(user["id"])})
        if br:
            b = br[0]
            profile["billing"] = {"credits": float(b[0]), "vip_expires_at": b[1].isoformat() if b[1] else None, "vip_is_lifetime": bool(b[2]), "vip_plan": b[3] or ""}
        else:
            profile["billing"] = {"credits": 0, "vip_expires_at": None, "vip_is_lifetime": False, "vip_plan": ""}
    return {"user": profile}


@router.put("/users/profile/update")
async def update_profile(request: UpdateProfileRequest, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    """Update own profile (nickname, avatar, timezone)."""
    sets: list[str] = []; p: dict[str, Any] = {"id": user["id"], "now": datetime.now(timezone.utc)}
    if request.nickname is not None:
        sets.append("nickname = :n"); p["n"] = request.nickname
    if request.avatar is not None:
        sets.append("avatar = :a"); p["a"] = request.avatar
    if request.timezone is not None:
        sets.append("timezone = :tz"); p["tz"] = request.timezone
    if not sets:
        raise HTTPException(400, detail="no_fields_to_update")
    sets.append("updated_at = :now")
    _e(f"UPDATE users SET {', '.join(sets)} WHERE id = :id", p)
    logger.info("profile_updated", uid=user["id"])
    return {"message": "profile_updated"}


@router.post("/users/change-password")
async def change_password(request: ChangePasswordRequest, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    """Change own password."""
    rows = _q("SELECT password_hash FROM users WHERE id = :id", {"id": user["id"]})
    if not rows or not _cpw(request.old_password, rows[0][0]):
        raise HTTPException(400, detail="old_password_incorrect")
    _e("UPDATE users SET password_hash = :p, updated_at = :now WHERE id = :id", {"p": _hpw(request.new_password), "id": user["id"], "now": datetime.now(timezone.utc)})
    return {"message": "password_changed"}


# ── Notification Settings ────────────────────────────────────────────────────

@router.get("/users/notification-settings")
async def get_notification_settings(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Get notification settings for current user."""
    meta = _get_meta(user["id"])
    defaults = {"email_on_login": True, "email_on_credits_change": True, "email_on_vip_change": True, "push_enabled": False}
    return {"notifications": {**defaults, **meta.get("notifications", {})}}


@router.put("/users/notification-settings")
async def update_notification_settings(request: dict[str, Any], user: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    """Update notification settings for current user."""
    meta = _get_meta(user["id"])
    meta["notifications"] = request
    _save_meta(user["id"], meta)
    logger.info("notification_settings_updated", uid=user["id"])
    return {"message": "notification_settings_updated"}


# ── Chart Templates ──────────────────────────────────────────────────────────

@router.get("/users/chart-templates")
async def get_chart_templates(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Get chart templates for current user."""
    return {"templates": _get_meta(user["id"]).get("chart_templates", [])}


@router.post("/users/chart-templates")
async def save_chart_template(request: dict[str, Any], user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Save a chart template."""
    meta = _get_meta(user["id"])
    templates: list[dict[str, Any]] = meta.get("chart_templates", [])
    tid = request.get("id")
    if tid:
        for i, t in enumerate(templates):
            if t.get("id") == tid:
                templates[i] = request; break
        else:
            templates.append(request)
    else:
        request["id"] = max((t.get("id", 0) for t in templates), default=0) + 1
        templates.append(request)
    meta["chart_templates"] = templates
    _save_meta(user["id"], meta)
    logger.info("chart_template_saved", uid=user["id"], tid=request.get("id"))
    return {"message": "template_saved", "id": request.get("id")}


@router.delete("/users/chart-templates")
async def delete_chart_template(template_id: int, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    """Delete a chart template."""
    meta = _get_meta(user["id"])
    meta["chart_templates"] = [t for t in meta.get("chart_templates", []) if t.get("id") != template_id]
    _save_meta(user["id"], meta)
    logger.info("chart_template_deleted", uid=user["id"], tid=template_id)
    return {"message": "template_deleted"}
