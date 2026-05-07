"""
UF Stock Assistant — 密码管理
bcrypt 哈希、SHA-256 兼容验证、密码强度校验
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

import bcrypt

from app.core.logging import get_logger

logger = get_logger("app.auth.password")


def hash_password(password: str) -> str:
    """Hash password with bcrypt (12 rounds)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash. Supports bcrypt and SHA-256 fallback."""
    if not password_hash:
        return False
    if password_hash.startswith("$2b$") or password_hash.startswith("$2a$"):
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    if password_hash.startswith("sha256$"):
        try:
            _, salt, hash_val = password_hash.split("$", 2)
            computed = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
            return hmac.compare_digest(computed, hash_val)
        except (ValueError, IndexError):
            return False
    return False


def validate_password_strength(password: str) -> tuple[bool, str]:
    """Validate password strength. Returns (is_valid, error_message)."""
    if len(password) < 8:
        return False, "密码至少需要 8 个字符"
    if not any(c.isupper() for c in password):
        return False, "密码需要包含至少一个大写字母"
    if not any(c.islower() for c in password):
        return False, "密码需要包含至少一个小写字母"
    if not any(c.isdigit() for c in password):
        return False, "密码需要包含至少一个数字"
    return True, ""


def generate_random_password(length: int = 16) -> str:
    """Generate a random password."""
    return secrets.token_urlsafe(length)
