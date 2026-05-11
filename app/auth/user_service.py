"""
UF Stock Assistant — 用户服务
用户 CRUD、认证、积分管理、VIP 会员、密码管理
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.auth.models import User, get_auth_db_session
from app.auth.password import hash_password, verify_password, validate_password_strength
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("app.auth.user_service")

# 不允许通过 update_user 修改的字段
_PROTECTED_FIELDS = frozenset({
    "id", "password_hash", "token_version", "created_at",
})


class UserService:
    """用户全生命周期管理：注册、认证、资料、积分、VIP"""

    # ---------- 注册 ----------

    def create_user(
        self,
        username: str,
        password: str,
        email: str,
        role: str = "user",
        nickname: str = "",
        referred_by: int | None = None,
    ) -> User:
        """
        创建用户并赠送注册积分。

        Raises:
            ValueError: 用户名/邮箱已存在或密码强度不足
        """
        ok, msg = validate_password_strength(password)
        if not ok:
            raise ValueError(msg)

        session = get_auth_db_session()
        try:
            # 唯一性检查
            if session.query(User).filter(User.username == username).first():
                raise ValueError("用户名已存在")
            if session.query(User).filter(User.email == email).first():
                raise ValueError("邮箱已被注册")

            settings = get_settings()
            now = datetime.now(timezone.utc)
            from decimal import Decimal
            user = User(
                username=username,
                password_hash=hash_password(password),
                email=email,
                nickname=nickname or username,
                role=role,
                status="active",
                credits=settings.auth.credits_register_bonus,
                mock_initial_capital=Decimal("5000000"),
                mock_available_cash=Decimal("5000000"),
                referred_by=referred_by,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            session.commit()
            session.refresh(user)

            logger.info(
                "user_created",
                user_id=user.id,
                username=username,
                role=role,
                credits=user.credits,
            )

            # 推荐人奖励
            if referred_by:
                referrer = session.query(User).filter(User.id == referred_by).first()
                if referrer:
                    referrer.credits = (referrer.credits or 0) + settings.auth.credits_referral_bonus
                    session.commit()
                    logger.info("referral_bonus", referrer_id=referred_by, bonus=settings.auth.credits_referral_bonus)

            return user

        except ValueError:
            raise
        except Exception as exc:
            session.rollback()
            logger.error("create_user_error", username=username, error=str(exc))
            raise ValueError("创建用户时出现内部错误") from exc
        finally:
            session.close()

    # ---------- 认证 ----------

    def authenticate(self, username_or_email: str, password: str) -> User | None:
        """
        通过用户名或邮箱 + 密码认证。

        Returns:
            User 对象或 None
        """
        session = get_auth_db_session()
        try:
            user = (
                session.query(User)
                .filter(
                    (User.username == username_or_email) | (User.email == username_or_email)
                )
                .first()
            )
            if not user:
                return None
            if not user.is_active:
                return None
            if not verify_password(password, user.password_hash):
                return None
            return user
        finally:
            session.close()

    # ---------- 查询 ----------

    def get_user_by_id(self, user_id: int) -> User | None:
        session = get_auth_db_session()
        try:
            return session.query(User).filter(User.id == user_id).first()
        finally:
            session.close()

    def get_user_by_username(self, username: str) -> User | None:
        session = get_auth_db_session()
        try:
            return session.query(User).filter(User.username == username).first()
        finally:
            session.close()

    def get_user_by_email(self, email: str) -> User | None:
        session = get_auth_db_session()
        try:
            return session.query(User).filter(User.email == email).first()
        finally:
            session.close()

    # ---------- 更新 ----------

    def update_user(self, user_id: int, **kwargs) -> User:
        """
        更新用户字段。仅允许安全字段，忽略受保护字段。

        Raises:
            ValueError: 用户不存在或更新失败
        """
        session = get_auth_db_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                raise ValueError("用户不存在")

            for key, value in kwargs.items():
                if key in _PROTECTED_FIELDS:
                    logger.warning("skipped_protected_field", field=key, user_id=user_id)
                    continue
                if hasattr(user, key):
                    setattr(user, key, value)

            user.updated_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(user)

            logger.info("user_updated", user_id=user_id, fields=list(kwargs.keys()))
            return user

        except ValueError:
            raise
        except Exception as exc:
            session.rollback()
            logger.error("update_user_error", user_id=user_id, error=str(exc))
            raise ValueError("更新用户信息失败") from exc
        finally:
            session.close()

    # ---------- 删除 ----------

    def delete_user(self, user_id: int) -> bool:
        """软删除用户（标记 is_active=False）。"""
        session = get_auth_db_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return False
            user.is_active = False
            user.updated_at = datetime.now(timezone.utc)
            session.commit()
            logger.info("user_deleted", user_id=user_id)
            return True
        except Exception as exc:
            session.rollback()
            logger.error("delete_user_error", user_id=user_id, error=str(exc))
            return False
        finally:
            session.close()

    # ---------- 列表 ----------

    def list_users(
        self, page: int = 1, page_size: int = 20, search: str = "",
    ) -> tuple[list[User], int]:
        """
        分页查询用户列表。

        Returns:
            (users, total_count)
        """
        session = get_auth_db_session()
        try:
            query = session.query(User)
            if search:
                like_pattern = f"%{search}%"
                query = query.filter(
                    (User.username.ilike(like_pattern))
                    | (User.email.ilike(like_pattern))
                    | (User.nickname.ilike(like_pattern))
                )

            total = query.count()
            users = (
                query.order_by(User.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            return users, total
        finally:
            session.close()

    # ---------- 密码管理 ----------

    def change_password(
        self, user_id: int, old_password: str, new_password: str,
    ) -> tuple[bool, str]:
        """
        修改密码（需要旧密码验证）。

        Returns:
            (success, message)
        """
        ok, msg = validate_password_strength(new_password)
        if not ok:
            return False, msg

        session = get_auth_db_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return False, "用户不存在"
            if not verify_password(old_password, user.password_hash):
                return False, "旧密码不正确"

            user.password_hash = hash_password(new_password)
            user.token_version = (user.token_version or 0) + 1
            user.updated_at = datetime.now(timezone.utc)
            session.commit()

            logger.info("password_changed", user_id=user_id)
            return True, "密码修改成功"

        except Exception as exc:
            session.rollback()
            logger.error("change_password_error", user_id=user_id, error=str(exc))
            return False, "修改密码时出现内部错误"
        finally:
            session.close()

    def reset_password(self, user_id: int, new_password: str) -> bool:
        """
        管理员重置密码（无需旧密码）。

        Returns:
            success
        """
        ok, msg = validate_password_strength(new_password)
        if not ok:
            logger.warning("reset_password_weak", user_id=user_id, reason=msg)
            return False

        session = get_auth_db_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return False

            user.password_hash = hash_password(new_password)
            user.token_version = (user.token_version or 0) + 1
            user.updated_at = datetime.now(timezone.utc)
            session.commit()

            logger.info("password_reset_by_admin", user_id=user_id)
            return True

        except Exception as exc:
            session.rollback()
            logger.error("reset_password_error", user_id=user_id, error=str(exc))
            return False
        finally:
            session.close()

    # ---------- Token 版本管理 ----------

    def increment_token_version(self, user_id: int) -> int:
        """
        递增 token_version，使所有已签发的 JWT 失效。

        Returns:
            新的 token_version
        """
        session = get_auth_db_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                raise ValueError("用户不存在")
            user.token_version = (user.token_version or 0) + 1
            user.updated_at = datetime.now(timezone.utc)
            session.commit()
            logger.info("token_version_incremented", user_id=user_id, new_version=user.token_version)
            return user.token_version
        except ValueError:
            raise
        except Exception as exc:
            session.rollback()
            logger.error("increment_token_version_error", user_id=user_id, error=str(exc))
            raise ValueError("更新 token 版本失败") from exc
        finally:
            session.close()

    # ---------- 积分管理 ----------

    def set_credits(self, user_id: int, amount: float, reason: str = "") -> None:
        """设置绝对积分值。"""
        session = get_auth_db_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                raise ValueError("用户不存在")
            old = user.credits or 0
            user.credits = amount
            user.updated_at = datetime.now(timezone.utc)
            session.commit()
            logger.info("credits_set", user_id=user_id, old=old, new=amount, reason=reason)
        except ValueError:
            raise
        except Exception as exc:
            session.rollback()
            logger.error("set_credits_error", user_id=user_id, error=str(exc))
            raise ValueError("设置积分失败") from exc
        finally:
            session.close()

    def add_credits(self, user_id: int, amount: float, reason: str = "") -> None:
        """增加积分（可传负数扣减）。"""
        session = get_auth_db_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                raise ValueError("用户不存在")
            old = user.credits or 0
            user.credits = old + amount
            user.updated_at = datetime.now(timezone.utc)
            session.commit()
            logger.info("credits_added", user_id=user_id, amount=amount, old=old, new=user.credits, reason=reason)
        except ValueError:
            raise
        except Exception as exc:
            session.rollback()
            logger.error("add_credits_error", user_id=user_id, error=str(exc))
            raise ValueError("更新积分失败") from exc
        finally:
            session.close()

    # ---------- VIP 会员 ----------

    def set_vip(
        self,
        user_id: int,
        plan: str,
        expires_at: datetime | None = None,
        is_lifetime: bool = False,
    ) -> None:
        """设置 VIP 套餐。"""
        session = get_auth_db_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                raise ValueError("用户不存在")

            user.vip_plan = plan
            user.vip_expires_at = None if is_lifetime else expires_at
            user.vip_is_lifetime = is_lifetime
            user.updated_at = datetime.now(timezone.utc)
            session.commit()

            logger.info(
                "vip_set",
                user_id=user_id,
                plan=plan,
                expires_at=str(expires_at),
                is_lifetime=is_lifetime,
            )
        except ValueError:
            raise
        except Exception as exc:
            session.rollback()
            logger.error("set_vip_error", user_id=user_id, error=str(exc))
            raise ValueError("设置 VIP 失败") from exc
        finally:
            session.close()

    # ---------- 初始化默认管理员 ----------

    def ensure_admin_user(self) -> None:
        """如果用户表为空，创建默认管理员账户。"""
        session = get_auth_db_session()
        try:
            count = session.query(User).count()
            if count > 0:
                return

            settings = get_settings()
            admin_user = settings.auth.admin_user
            admin_password = settings.auth.admin_password

            now = datetime.now(timezone.utc)
            user = User(
                username=admin_user,
                password_hash=hash_password(admin_password),
                email=f"{admin_user}@uf-assistant.local",
                nickname="管理员",
                role="admin",
                is_active=True,
                token_version=0,
                credits=99999.0,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            session.commit()
            logger.info("default_admin_created", username=admin_user)

        except Exception as exc:
            session.rollback()
            logger.error("ensure_admin_user_error", error=str(exc))
        finally:
            session.close()
