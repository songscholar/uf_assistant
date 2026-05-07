"""
UF Stock Assistant — 安全服务
频率限制、Turnstile 人机验证、登录尝试记录、IP/账户锁定、审计日志
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.auth.models import LoginAttempt, SecurityLog, get_auth_db_session
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("app.auth.security_service")


class SecurityService:
    """安全服务：频率限制、Turnstile 校验、审计日志"""

    # ---------- 频率限制 ----------

    def check_rate_limit(
        self,
        identifier: str,
        identifier_type: str,
        max_attempts: int,
        window_seconds: int,
    ) -> bool:
        """
        检查标识符是否超出频率限制。

        Args:
            identifier: 限制标识（用户名 / IP / 邮箱）
            identifier_type: 标识类型
            max_attempts: 窗口内最大允许次数
            window_seconds: 窗口大小（秒）

        Returns:
            True 表示允许，False 表示已被限制
        """
        session = get_auth_db_session()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
            count = (
                session.query(LoginAttempt)
                .filter(
                    LoginAttempt.identifier == identifier,
                    LoginAttempt.identifier_type == identifier_type,
                    LoginAttempt.attempted_at > cutoff,
                )
                .count()
            )
            allowed = count < max_attempts
            if not allowed:
                logger.warning(
                    "rate_limit_exceeded",
                    identifier=identifier,
                    identifier_type=identifier_type,
                    count=count,
                    max_attempts=max_attempts,
                )
            return allowed
        finally:
            session.close()

    # ---------- 登录尝试记录 ----------

    def record_login_attempt(
        self,
        identifier: str,
        identifier_type: str,
        success: bool,
        ip: str,
        user_agent: str,
    ) -> None:
        """记录登录尝试到数据库。"""
        session = get_auth_db_session()
        try:
            attempt = LoginAttempt(
                identifier=identifier,
                identifier_type=identifier_type,
                success=success,
                ip=ip,
                user_agent=user_agent,
                attempted_at=datetime.now(timezone.utc),
            )
            session.add(attempt)
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.error("record_login_attempt_error", error=str(exc))
        finally:
            session.close()

    # ---------- Turnstile 人机验证 ----------

    def verify_turnstile(self, token: str, ip: str) -> bool:
        """
        通过 Cloudflare Turnstile API 校验人机 token。

        如果未配置 Turnstile 密钥则跳过校验（返回 True）。
        """
        settings = get_settings().auth
        secret = settings.turnstile_secret_key
        if not secret:
            return True

        try:
            resp = httpx.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={"secret": secret, "response": token, "remoteip": ip},
                timeout=10,
            )
            result = resp.json()
            success = result.get("success", False)
            if not success:
                logger.warning(
                    "turnstile_verify_failed",
                    ip=ip,
                    error_codes=result.get("error-codes", []),
                )
            return success
        except Exception as exc:
            logger.error("turnstile_verify_error", ip=ip, error=str(exc))
            return False

    # ---------- 审计日志 ----------

    def log_security_event(
        self,
        user_id: int | None,
        action: str,
        ip: str = "",
        user_agent: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        """写入 SecurityLog 审计表。"""
        session = get_auth_db_session()
        try:
            entry = SecurityLog(
                user_id=user_id,
                action=action,
                ip=ip,
                user_agent=user_agent,
                details=json.dumps(details, ensure_ascii=False) if details else None,
                created_at=datetime.now(timezone.utc),
            )
            session.add(entry)
            session.commit()
            logger.info("security_event", user_id=user_id, action=action, ip=ip)
        except Exception as exc:
            session.rollback()
            logger.error("log_security_event_error", action=action, error=str(exc))
        finally:
            session.close()

    # ---------- IP 封锁 ----------

    def is_ip_blocked(self, ip: str) -> bool:
        """
        检查 IP 是否被封锁。
        规则：5 分钟内 10 次失败 → 封锁 15 分钟。
        """
        session = get_auth_db_session()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
            failed_count = (
                session.query(LoginAttempt)
                .filter(
                    LoginAttempt.ip == ip,
                    LoginAttempt.success == False,  # noqa: E712
                    LoginAttempt.attempted_at > cutoff,
                )
                .count()
            )
            if failed_count < 10:
                return False

            # 检查最后一次失败时间，确认是否仍在封锁期内
            last_fail = (
                session.query(LoginAttempt)
                .filter(
                    LoginAttempt.ip == ip,
                    LoginAttempt.success == False,  # noqa: E712
                )
                .order_by(LoginAttempt.attempted_at.desc())
                .first()
            )
            if last_fail and datetime.now(timezone.utc) - last_fail.attempted_at < timedelta(minutes=15):
                logger.warning("ip_blocked", ip=ip)
                return True
            return False
        finally:
            session.close()

    # ---------- 账户锁定 ----------

    def is_account_locked(self, username: str) -> bool:
        """
        检查账户是否被锁定。
        规则：60 分钟内 5 次失败 → 锁定 30 分钟。
        """
        session = get_auth_db_session()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=60)
            failed_count = (
                session.query(LoginAttempt)
                .filter(
                    LoginAttempt.identifier == username,
                    LoginAttempt.identifier_type == "username",
                    LoginAttempt.success == False,  # noqa: E712
                    LoginAttempt.attempted_at > cutoff,
                )
                .count()
            )
            if failed_count < 5:
                return False

            last_fail = (
                session.query(LoginAttempt)
                .filter(
                    LoginAttempt.identifier == username,
                    LoginAttempt.identifier_type == "username",
                    LoginAttempt.success == False,  # noqa: E712
                )
                .order_by(LoginAttempt.attempted_at.desc())
                .first()
            )
            if last_fail and datetime.now(timezone.utc) - last_fail.attempted_at < timedelta(minutes=30):
                logger.warning("account_locked", username=username)
                return True
            return False
        finally:
            session.close()
