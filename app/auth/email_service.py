"""
UF Stock Assistant — 邮箱验证码服务
支持发送验证码、校验验证码、频率限制、防暴力破解
"""

from __future__ import annotations

import random
import smtplib
import string
import time
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.auth.models import VerificationCode, get_auth_db_session
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("app.auth.email_service")


class EmailService:
    """邮箱验证码服务：发送、校验、频率限制"""

    # ---------- 发送验证码 ----------

    def send_verification_code(self, email: str, code_type: str, ip: str = "") -> tuple[bool, str]:
        """
        生成 6 位验证码，存入数据库，通过 SMTP 发送邮件。

        Args:
            email: 目标邮箱
            code_type: 验证码用途 (register / reset_password / bind_email)
            ip: 请求来源 IP（用于频率限制）

        Returns:
            (success, message)
        """
        settings = get_settings().auth
        session = get_auth_db_session()
        try:
            # 频率限制：同一邮箱 60 秒内只能发一次
            cutoff_email = datetime.now(timezone.utc) - timedelta(seconds=60)
            recent = (
                session.query(VerificationCode)
                .filter(
                    VerificationCode.email == email,
                    VerificationCode.code_type == code_type,
                    VerificationCode.created_at > cutoff_email,
                )
                .first()
            )
            if recent:
                return False, "验证码发送过于频繁，请 60 秒后再试"

            # 频率限制：同一 IP 每小时最多 10 次
            if ip:
                cutoff_ip = datetime.now(timezone.utc) - timedelta(hours=1)
                ip_count = (
                    session.query(VerificationCode)
                    .filter(
                        VerificationCode.ip == ip,
                        VerificationCode.created_at > cutoff_ip,
                    )
                    .count()
                )
                if ip_count >= 10:
                    logger.warning("email_rate_limit_ip", ip=ip)
                    return False, "当前 IP 发送验证码次数过多，请稍后再试"

            # 生成 6 位数字验证码
            code = "".join(random.choices(string.digits, k=6))

            # 存入数据库
            record = VerificationCode(
                email=email,
                code=code,
                code_type=code_type,
                ip=ip,
                attempts=0,
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc)
                + timedelta(minutes=settings.email_code_expire_minutes),
            )
            session.add(record)
            session.commit()

            # 发送邮件
            subject = _build_subject(code_type)
            body = _build_body(code, settings.email_code_expire_minutes)
            sent = self._send_email(email, subject, body)

            if sent:
                logger.info("verification_code_sent", email=email, code_type=code_type)
                return True, "验证码已发送"
            else:
                logger.error("verification_code_send_failed", email=email)
                return False, "邮件发送失败，请稍后再试"

        except Exception as exc:
            session.rollback()
            logger.error("send_verification_code_error", email=email, error=str(exc))
            return False, "发送验证码时出现内部错误"
        finally:
            session.close()

    # ---------- 校验验证码 ----------

    def verify_code(self, email: str, code: str, code_type: str) -> tuple[bool, str]:
        """
        校验验证码。防暴力破解：5 次失败后锁定 30 分钟。

        Returns:
            (success, message)
        """
        session = get_auth_db_session()
        try:
            record = (
                session.query(VerificationCode)
                .filter(
                    VerificationCode.email == email,
                    VerificationCode.code_type == code_type,
                    VerificationCode.used == False,  # noqa: E712
                )
                .order_by(VerificationCode.created_at.desc())
                .first()
            )

            if not record:
                return False, "验证码不存在或已使用"

            # 检查是否过期
            if record.expires_at and datetime.now(timezone.utc) > record.expires_at:
                return False, "验证码已过期，请重新获取"

            # 检查是否被锁定（5 次失败 → 30 分钟锁定）
            if record.attempts >= 5:
                lockout_until = record.created_at + timedelta(minutes=30)
                if datetime.now(timezone.utc) < lockout_until:
                    return False, "验证码输入错误次数过多，请 30 分钟后再试"
                # 锁定期已过，重置尝试次数
                record.attempts = 0
                session.commit()

            # 校验
            if record.code != code:
                record.attempts += 1
                session.commit()
                remaining = 5 - record.attempts
                if remaining > 0:
                    return False, f"验证码错误，还可尝试 {remaining} 次"
                return False, "验证码输入错误次数过多，请 30 分钟后再试"

            # 标记已使用
            record.used = True
            session.commit()

            logger.info("verification_code_verified", email=email, code_type=code_type)
            return True, "验证成功"

        except Exception as exc:
            session.rollback()
            logger.error("verify_code_error", email=email, error=str(exc))
            return False, "验证码校验时出现内部错误"
        finally:
            session.close()

    # ---------- SMTP 发送 ----------

    def _send_email(self, to: str, subject: str, body: str) -> bool:
        """通过 SMTP + STARTTLS 发送邮件。"""
        settings = get_settings().auth
        if not settings.smtp_host:
            logger.warning("smtp_not_configured")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = settings.smtp_from or settings.smtp_user
            msg["To"] = to
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "html", "utf-8"))

            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                if settings.smtp_use_tls:
                    server.starttls()
                if settings.smtp_user and settings.smtp_password:
                    server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)

            return True

        except Exception as exc:
            logger.error("smtp_send_error", to=to, error=str(exc))
            return False


# ---------- 邮件内容模板 ----------


def _build_subject(code_type: str) -> str:
    subjects = {
        "register": "【UF Stock Assistant】注册验证码",
        "reset_password": "【UF Stock Assistant】密码重置验证码",
        "bind_email": "【UF Stock Assistant】邮箱绑定验证码",
    }
    return subjects.get(code_type, "【UF Stock Assistant】验证码")


def _build_body(code: str, expire_minutes: int) -> str:
    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 24px;">
        <h2 style="color: #1a1a2e; margin-bottom: 16px;">UF Stock Assistant</h2>
        <p style="color: #333; font-size: 15px; line-height: 1.6;">您的验证码为：</p>
        <div style="background: #f4f4f8; border-radius: 8px; padding: 16px; text-align: center; margin: 20px 0;">
            <span style="font-size: 32px; font-weight: 700; letter-spacing: 6px; color: #1a1a2e;">{code}</span>
        </div>
        <p style="color: #666; font-size: 13px;">验证码 {expire_minutes} 分钟内有效，请勿泄露给他人。</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;" />
        <p style="color: #999; font-size: 12px;">如非本人操作，请忽略此邮件。</p>
    </div>
    """
