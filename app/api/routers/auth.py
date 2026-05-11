"""
UF Stock Assistant — 认证接口
"""

from __future__ import annotations

import secrets
import smtplib
import threading
import time
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from typing import Any
from urllib.parse import urlencode

import bcrypt
import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.auth.dependencies import get_client_ip, get_current_user
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("app.api.auth")
router = APIRouter()

# ── in-memory stores ────────────────────────────────────────────────────────

_lock = threading.Lock()
_ip_att: dict[str, list[float]] = {}
_ip_blk: dict[str, float] = {}
_ac_att: dict[str, list[float]] = {}
_ac_lck: dict[str, float] = {}
_codes: dict[tuple[str, str], dict[str, Any]] = {}
_oauth: dict[str, dict[str, Any]] = {}

_IP_L, _IP_W, _IP_B = 10, 300.0, 900.0
_AC_L, _AC_W, _AC_B = 5, 3600.0, 1800.0


# ── helpers ──────────────────────────────────────────────────────────────────

def _hpw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _cpw(pw: str, h: str) -> bool:
    return bcrypt.checkpw(pw.encode(), h.encode())


def _jwt(uid: str, name: str, role: str = "user", token_version: int = 0) -> str:
    s = get_settings().auth
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": name, "user_id": int(uid), "role": role, "token_version": token_version, "iat": now, "exp": now + timedelta(days=s.jwt_expire_days)}, s.secret_key, algorithm=s.jwt_algorithm)


def _rip(ip: str) -> None:
    now = time.time()
    with _lock:
        if _ip_blk.get(ip, 0) > now:
            raise HTTPException(429, detail="访问过于频繁，请稍后重试", headers={"Retry-After": str(int(_ip_blk[ip] - now))})
        a = [t for t in _ip_att.get(ip, []) if now - t < _IP_W]
        if len(a) >= _IP_L:
            _ip_blk[ip] = now + _IP_B; _ip_att[ip] = []
            raise HTTPException(429, detail="访问过于频繁，请稍后重试", headers={"Retry-After": str(int(_IP_B))})


def _wip(ip: str) -> None:
    now = time.time()
    with _lock:
        a = [t for t in _ip_att.get(ip, []) if now - t < _IP_W]; a.append(now); _ip_att[ip] = a


def _rac(u: str) -> None:
    now = time.time(); k = u.lower()
    with _lock:
        if _ac_lck.get(k, 0) > now:
            raise HTTPException(423, detail="账户已被锁定，请稍后重试", headers={"Retry-After": str(int(_ac_lck[k] - now))})
        a = [t for t in _ac_att.get(k, []) if now - t < _AC_W]
        if len(a) >= _AC_L:
            _ac_lck[k] = now + _AC_B; _ac_att[k] = []
            raise HTTPException(423, detail="账户已被锁定，请稍后重试", headers={"Retry-After": str(int(_AC_B))})


def _wac(u: str) -> None:
    now = time.time(); k = u.lower()
    with _lock:
        a = [t for t in _ac_att.get(k, []) if now - t < _AC_W]; a.append(now); _ac_att[k] = a


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


_UC = "id, username, email, password_hash, role, nickname, avatar, is_active, token_version"


def _ur(r: Any) -> dict[str, Any]:
    return dict(zip(("id", "username", "email", "password_hash", "role", "nickname", "avatar", "is_active", "token_version"), r[:9]))


def _fu(where: str, p: dict[str, Any]) -> dict[str, Any] | None:
    rows = _q(f"SELECT {_UC} FROM users WHERE {where}", p)
    return _ur(rows[0]) if rows else None


def _ensure() -> None:
    _e("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username VARCHAR(50) UNIQUE NOT NULL, email VARCHAR(255) UNIQUE, password_hash TEXT NOT NULL, role VARCHAR(20) DEFAULT 'user', nickname VARCHAR(100) DEFAULT '', avatar TEXT DEFAULT '', timezone VARCHAR(50) DEFAULT 'Asia/Shanghai', is_active BOOLEAN DEFAULT 1, token_version INTEGER DEFAULT 1, mock_initial_capital REAL DEFAULT 5000000, mock_available_cash REAL DEFAULT 5000000, created_at DATETIME, updated_at DATETIME, metadata TEXT)", {})


def _cu(username: str, email: str | None, ph: str, role: str = "user", nn: str = "") -> dict[str, Any] | None:
    now = datetime.now(timezone.utc)
    uid = _e("INSERT INTO users (username,email,password_hash,role,nickname,token_version,mock_initial_capital,mock_available_cash,created_at,updated_at) VALUES (:u,:e,:p,:r,:n,0,5000000,5000000,:t,:t)", {"u": username, "e": email, "p": ph, "r": role, "n": nn or username, "t": now})
    return {"id": uid, "username": username, "email": email, "role": role, "nickname": nn or username, "token_version": 0, "mock_initial_capital": 5000000, "mock_available_cash": 5000000} if uid else None


async def _mail(to: str, subj: str, body: str) -> bool:
    s = get_settings().auth
    # 优先使用 Resend（第三方邮件服务 API）
    if getattr(s, "resend_api_key", None):
        try:
            import resend
            resend.api_key = s.resend_api_key
            resend.Emails.send({
                "from": getattr(s, "resend_from", "noreply@uf-assistant.dev"),
                "to": [to],
                "subject": subj,
                "text": body,
            })
            logger.info("email_sent_resend", to=to)
            return True
        except Exception as e:
            logger.error("resend_failed", error=str(e))
    # fallback: SMTP
    if s.smtp_host:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"], msg["From"], msg["To"] = subj, s.smtp_from, to
        try:
            srv = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10)
            if s.smtp_use_tls:
                srv.starttls()
            srv.login(s.smtp_user, s.smtp_password); srv.sendmail(s.smtp_from, [to], msg.as_string()); srv.quit()
            logger.info("email_sent_smtp", to=to)
            return True
        except Exception as e:
            logger.error("email_failed", error=str(e))
    return False


async def _turnstile(token: str, ip: str) -> bool:
    s = get_settings().auth
    if not s.turnstile_secret_key:
        return True
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post("https://challenges.cloudflare.com/turnstile/v0/siteverify", data={"secret": s.turnstile_secret_key, "response": token, "remoteip": ip})
            return bool(r.json().get("success"))
    except Exception:
        return False


async def _oauth_exchange(provider: str, code: str) -> dict[str, Any]:
    s = get_settings().auth
    async with httpx.AsyncClient(timeout=15) as c:
        if provider == "google":
            tr = await c.post("https://oauth2.googleapis.com/token", data={"code": code, "client_id": s.google_client_id, "client_secret": s.google_client_secret, "redirect_uri": "/api/v1/auth/oauth/google/callback", "grant_type": "authorization_code"})
            ui = (await c.get("https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": f"Bearer {tr.json()['access_token']}"})).json()
            return {"email": ui.get("email", ""), "name": ui.get("name", ""), "login": ui.get("email", "").split("@")[0]}
        tr = await c.post("https://github.com/login/oauth/access_token", json={"client_id": s.github_client_id, "client_secret": s.github_client_secret, "code": code}, headers={"Accept": "application/json"})
        tok = tr.json()["access_token"]
        ui = (await c.get("https://api.github.com/user", headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"})).json()
        email = ui.get("email")
        if not email:
            ems = (await c.get("https://api.github.com/user/emails", headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"})).json()
            email = next((e["email"] for e in ems if e.get("primary")), ems[0]["email"] if ems else "")
        return {"email": email or "", "name": ui.get("name", ""), "login": ui.get("login", "")}


def _ensure_user(email: str, name: str, login: str) -> dict[str, Any]:
    _ensure()
    user = _fu("email = :e", {"e": email})
    if user:
        return user
    uname = login or email.split("@")[0]
    if _fu("username = :u", {"u": uname}):
        uname = f"{uname}_{secrets.token_hex(3)}"
    user = _cu(uname, email, _hpw(secrets.token_urlsafe(32)), nn=name or uname)
    if not user:
        raise HTTPException(500, detail="账户创建失败，请稍后重试")
    return user


# ── models ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)
    turnstile_token: str | None = None

class LoginCodeRequest(BaseModel):
    email: str = Field(..., min_length=5)
    code: str = Field(..., min_length=6, max_length=6)

class SendCodeRequest(BaseModel):
    email: str = Field(..., min_length=5)
    code_type: str = Field(..., description="register/login/reset_password/change_password")

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5)
    password: str = Field(..., min_length=8)
    code: str = Field(..., min_length=6, max_length=6)
    referral_code: str | None = None

class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    new_password: str = Field(..., min_length=8)

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8)


# ── endpoints ────────────────────────────────────────────────────────────────

@router.get("/auth/security-config")
async def get_security_config() -> dict[str, Any]:
    s = get_settings().auth
    return {"registration_enabled": s.registration_enabled, "turnstile_site_key": s.turnstile_site_key or "", "oauth": {"google": bool(s.google_client_id), "github": bool(s.github_client_id)}}


@router.post("/auth/login")
async def login(request: LoginRequest, req: Request) -> dict[str, Any]:
    s = get_settings().auth; ip = get_client_ip(req)
    if s.single_user_mode:
        if request.username == s.admin_user and request.password == s.admin_password:
            return {"token": _jwt("0", request.username, "admin", 0), "user": {"id": 0, "username": request.username, "role": "admin"}}
        raise HTTPException(401, detail="用户名或密码错误")
    if s.turnstile_secret_key and request.turnstile_token and not await _turnstile(request.turnstile_token, ip):
        raise HTTPException(400, detail="人机验证失败，请刷新页面重试")
    _rip(ip); _rac(request.username); _ensure()
    user = _fu("username = :u", {"u": request.username})
    if not user or not _cpw(request.password, user["password_hash"]):
        _wip(ip); _wac(request.username); raise HTTPException(401, detail="用户名或密码错误")
    if not user.get("is_active", True):
        raise HTTPException(403, detail="账户已被禁用")
    logger.info("login_ok", uid=user["id"])
    return {"token": _jwt(str(user["id"]), user["username"], user.get("role", "user"), user.get("token_version", 0)), "user": {k: user[k] for k in ("id", "username", "email", "role", "nickname")}}


@router.post("/auth/login-code")
async def login_with_code(request: LoginCodeRequest, req: Request) -> dict[str, Any]:
    email = request.email.lower()
    with _lock:
        entry = _codes.pop((email, "login"), None)
    if not entry or time.time() > entry["expires"] or entry["code"] != request.code:
        raise HTTPException(400, detail="验证码已过期或无效")
    _ensure()
    user = _fu("email = :e", {"e": email})
    if not user:
        uname = email.split("@")[0]
        if _fu("username = :u", {"u": uname}):
            uname = f"{uname}_{secrets.token_hex(3)}"
        user = _cu(uname, email, _hpw(secrets.token_urlsafe(16)))
        if not user:
            raise HTTPException(500, detail="账户创建失败，请稍后重试")
    if not user.get("is_active", True):
        raise HTTPException(403, detail="账户已被禁用")
    return {"token": _jwt(str(user["id"]), user["username"], user.get("role", "user"), user.get("token_version", 0)), "user": {k: user[k] for k in ("id", "username", "email", "role")}}


@router.post("/auth/send-code")
async def send_code(request: SendCodeRequest, req: Request) -> dict[str, Any]:
    email = request.email.lower(); ct = request.code_type
    if ct not in {"register", "login", "reset_password", "change_password"}:
        raise HTTPException(400, detail="验证码类型无效")
    with _lock:
        if (email, ct) in _codes and time.time() < _codes[(email, ct)]["expires"] - 540:
            raise HTTPException(429, detail="验证码发送过于频繁，请稍后再试")
    if ct == "register":
        _ensure()
        if _fu("email = :e", {"e": email}):
            raise HTTPException(409, detail="该邮箱已注册")
    code = f"{secrets.randbelow(1000000):06d}"; s = get_settings().auth
    with _lock:
        _codes[(email, ct)] = {"code": code, "expires": time.time() + s.email_code_expire_minutes * 60}
    subj = {"register": "注册", "login": "登录", "reset_password": "重置密码", "change_password": "修改密码"}
    mail_ok = await _mail(email, f"UF Stock Assistant - {subj.get(ct, '')}验证码", f"您的验证码是：{code}\n有效期 {s.email_code_expire_minutes} 分钟。")
    if not mail_ok:
        logger.info("code_generated_dev_mode", email=email, type=ct, code=code, note="SMTP 未配置，验证码已记录到日志，请查看服务器终端")
    else:
        logger.info("code_sent", email=email, type=ct)
    return {"message": "验证码已发送", "expires_in": s.email_code_expire_minutes * 60, "dev_mode": not mail_ok}


@router.post("/auth/register")
async def register(request: RegisterRequest, req: Request) -> dict[str, Any]:
    if not get_settings().auth.registration_enabled:
        raise HTTPException(403, detail="当前已关闭注册")
    email = request.email.lower()
    with _lock:
        entry = _codes.pop((email, "register"), None)
    if not entry or time.time() > entry["expires"] or entry["code"] != request.code:
        raise HTTPException(400, detail="验证码已过期或无效")
    _ensure()
    if _fu("username = :u", {"u": request.username}):
        raise HTTPException(409, detail="该用户名已被占用")
    if _fu("email = :e", {"e": email}):
        raise HTTPException(409, detail="该邮箱已注册")
    user = _cu(request.username, email, _hpw(request.password))
    if not user:
        raise HTTPException(500, detail="注册失败，请稍后重试")
    if request.referral_code:
        logger.info("referral", uid=user["id"], code=request.referral_code)
    return {"token": _jwt(str(user["id"]), user["username"], "user", user.get("token_version", 0)), "user": {"id": user["id"], "username": user["username"], "email": email, "role": "user"}}


@router.post("/auth/reset-password")
async def reset_password(request: ResetPasswordRequest) -> dict[str, Any]:
    email = request.email.lower()
    with _lock:
        entry = _codes.pop((email, "reset_password"), None)
    if not entry or time.time() > entry["expires"] or entry["code"] != request.code:
        raise HTTPException(400, detail="验证码已过期或无效")
    _ensure()
    user = _fu("email = :e", {"e": email})
    if not user:
        raise HTTPException(404, detail="用户不存在")
    _e("UPDATE users SET password_hash = :p WHERE id = :i", {"p": _hpw(request.new_password), "i": user["id"]})
    return {"message": "密码重置成功"}


@router.post("/auth/change-password")
async def change_password(request: ChangePasswordRequest, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    _ensure(); cur = _fu("id = :i", {"i": user["id"]})
    if not cur or not _cpw(request.old_password, cur["password_hash"]):
        raise HTTPException(400, detail="原密码错误")
    _e("UPDATE users SET password_hash = :p WHERE id = :i", {"p": _hpw(request.new_password), "i": user["id"]})
    return {"message": "密码修改成功"}


# ── OAuth ────────────────────────────────────────────────────────────────────

def _oauth_redirect(provider: str) -> RedirectResponse:
    s = get_settings().auth
    cid = s.google_client_id if provider == "google" else s.github_client_id
    if not cid:
        raise HTTPException(501, detail="该登录方式未配置")
    state = secrets.token_urlsafe(32)
    with _lock:
        _oauth[state] = {"redirect": "", "expires": time.time() + s.oauth_state_ttl_minutes * 60}
    if provider == "google":
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({"client_id": cid, "redirect_uri": "/api/v1/auth/oauth/google/callback", "response_type": "code", "scope": "openid email profile", "state": state, "access_type": "offline", "prompt": "consent"})
    else:
        url = "https://github.com/login/oauth/authorize?" + urlencode({"client_id": cid, "redirect_uri": "/api/v1/auth/oauth/github/callback", "scope": "user:email", "state": state})
    return RedirectResponse(url=url)


async def _oauth_cb(provider: str, code: str, state: str) -> RedirectResponse:
    with _lock:
        se = _oauth.pop(state, None)
    if not se or time.time() > se["expires"]:
        raise HTTPException(400, detail="登录状态已过期，请重新登录")
    info = await _oauth_exchange(provider, code)
    if not info["email"]:
        raise HTTPException(400, detail="无法获取邮箱信息，请尝试其他登录方式")
    _ensure()
    user = _ensure_user(info["email"], info["name"], info["login"])
    return RedirectResponse(url=f"/auth/callback?token={_jwt(str(user['id']), user['username'], user.get('role', 'user'), user.get('token_version', 0))}")


@router.get("/auth/oauth/google")
async def oauth_google(redirect: str = "") -> RedirectResponse:
    return _oauth_redirect("google")

@router.get("/auth/oauth/google/callback")
async def oauth_google_callback(code: str, state: str) -> RedirectResponse:
    return await _oauth_cb("google", code, state)

@router.get("/auth/oauth/github")
async def oauth_github(redirect: str = "") -> RedirectResponse:
    return _oauth_redirect("github")

@router.get("/auth/oauth/github/callback")
async def oauth_github_callback(code: str, state: str) -> RedirectResponse:
    return await _oauth_cb("github", code, state)


@router.post("/auth/logout")
async def logout() -> dict[str, str]:
    return {"message": "已退出登录"}


@router.get("/auth/info")
async def get_user_info(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    _ensure(); u = _fu("id = :i", {"i": user["user_id"]})
    if not u:
        raise HTTPException(404, detail="用户不存在")
    return {k: u.get(k) for k in ("id", "username", "email", "role", "nickname", "avatar")}
