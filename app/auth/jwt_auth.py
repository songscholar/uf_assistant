"""
UF Stock Assistant — JWT 认证
令牌生成、验证、版本校验
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("app.auth.jwt")


def generate_token(user_id: int, username: str, role: str, token_version: int) -> str:
    """Generate JWT token."""
    settings = get_settings()
    payload = {
        "exp": datetime.now(UTC) + timedelta(days=settings.auth.jwt_expire_days),
        "iat": datetime.now(UTC),
        "sub": username,
        "user_id": user_id,
        "role": role,
        "token_version": token_version,
    }
    return jwt.encode(payload, settings.auth.secret_key, algorithm=settings.auth.jwt_algorithm)


def verify_token(token: str) -> dict | None:
    """Decode and verify JWT token. Returns payload or None if invalid."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.auth.secret_key, algorithms=[settings.auth.jwt_algorithm])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("token_expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("token_invalid", error=str(e))
        return None


def verify_token_version(payload: dict) -> bool:
    """Check that token_version in payload matches the database.
    In single_user_mode, always returns True."""
    settings = get_settings()
    if settings.auth.single_user_mode:
        return True

    user_id = payload.get("user_id")
    token_version = payload.get("token_version")
    if user_id is None or token_version is None:
        return False

    # 先查询 uf_users（SQLAlchemy ORM 表）
    from app.auth.models import User, get_auth_db_session

    session = get_auth_db_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            return user.token_version == token_version
    finally:
        session.close()

    # fallback: 查询 users 表（auth.py 直接 SQL 操作）
    try:
        import sqlite3
        db_path = str(settings.database.url).replace("sqlite:///", "")
        conn = sqlite3.connect(db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT token_version FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            return row["token_version"] == token_version
    except Exception:
        pass

    return False
