"""
UF Stock Assistant — OAuth 第三方登录服务
支持 Google 和 GitHub OAuth 2.0 授权码流程
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.auth.models import OAuthLink, OAuthState, User, get_auth_db_session
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("app.auth.oauth_service")


class OAuthService:
    """OAuth 第三方登录：Google / GitHub"""

    # ==================== Google ====================

    def get_google_auth_url(self, redirect_uri: str) -> tuple[str, str]:
        """
        生成 Google OAuth 授权 URL 和 state。

        Returns:
            (authorization_url, state)
        """
        settings = get_settings().auth
        state = secrets.token_urlsafe(32)
        self._store_state("google", state, redirect_uri)

        params = urlencode({
            "client_id": settings.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        })
        url = f"https://accounts.google.com/o/oauth2/v2/auth?{params}"
        return url, state

    async def handle_google_callback(self, code: str, state: str) -> dict:
        """
        处理 Google OAuth 回调：交换 token → 获取用户信息 → 创建/关联账户。

        Returns:
            {"user": User, "is_new": bool}
        """
        settings = get_settings().auth
        redirect_uri = self._verify_state(state, "google")
        if not redirect_uri:
            return {"error": "无效或过期的 OAuth state"}

        async with httpx.AsyncClient(timeout=15) as client:
            # 交换 code 获取 token
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            if token_resp.status_code != 200:
                logger.error("google_token_exchange_failed", status=token_resp.status_code)
                return {"error": "Google token 交换失败"}

            access_token = token_resp.json().get("access_token")

            # 获取用户信息
            userinfo_resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_resp.status_code != 200:
                logger.error("google_userinfo_failed", status=userinfo_resp.status_code)
                return {"error": "获取 Google 用户信息失败"}

            info = userinfo_resp.json()

        provider_user_id = str(info.get("id", ""))
        email = info.get("email", "")
        name = info.get("name", "")
        avatar = info.get("picture", "")

        session = get_auth_db_session()
        try:
            user, is_new = self._get_or_create_user(
                session, "google", provider_user_id, email, name, avatar,
            )
            session.commit()
            logger.info("oauth_login", provider="google", user_id=user.id, is_new=is_new)
            return {"user": user, "is_new": is_new}
        except Exception as exc:
            session.rollback()
            logger.error("google_oauth_error", error=str(exc))
            return {"error": "处理 Google 登录时出现内部错误"}
        finally:
            session.close()

    # ==================== GitHub ====================

    def get_github_auth_url(self, redirect_uri: str) -> tuple[str, str]:
        """生成 GitHub OAuth 授权 URL 和 state。"""
        settings = get_settings().auth
        state = secrets.token_urlsafe(32)
        self._store_state("github", state, redirect_uri)

        params = urlencode({
            "client_id": settings.github_client_id,
            "redirect_uri": redirect_uri,
            "scope": "read:user user:email",
            "state": state,
        })
        url = f"https://github.com/login/oauth/authorize?{params}"
        return url, state

    async def handle_github_callback(self, code: str, state: str) -> dict:
        """处理 GitHub OAuth 回调。"""
        settings = get_settings().auth
        redirect_uri = self._verify_state(state, "github")
        if not redirect_uri:
            return {"error": "无效或过期的 OAuth state"}

        async with httpx.AsyncClient(timeout=15) as client:
            # 交换 code 获取 token
            token_resp = await client.post(
                "https://github.com/login/oauth/access_token",
                json={
                    "code": code,
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            if token_resp.status_code != 200:
                logger.error("github_token_exchange_failed", status=token_resp.status_code)
                return {"error": "GitHub token 交换失败"}

            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                logger.error("github_no_access_token", body=token_data)
                return {"error": "GitHub token 交换失败"}

            # 获取用户信息
            user_resp = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            if user_resp.status_code != 200:
                return {"error": "获取 GitHub 用户信息失败"}

            gh_user = user_resp.json()

            # 尝试获取邮箱（GitHub 用户可能隐藏邮箱）
            email = gh_user.get("email") or ""
            if not email:
                email_resp = await client.get(
                    "https://api.github.com/user/emails",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github+json",
                    },
                )
                if email_resp.status_code == 200:
                    for entry in email_resp.json():
                        if entry.get("primary"):
                            email = entry.get("email", "")
                            break

        provider_user_id = str(gh_user.get("id", ""))
        name = gh_user.get("name") or gh_user.get("login", "")
        avatar = gh_user.get("avatar_url", "")

        session = get_auth_db_session()
        try:
            user, is_new = self._get_or_create_user(
                session, "github", provider_user_id, email, name, avatar,
            )
            session.commit()
            logger.info("oauth_login", provider="github", user_id=user.id, is_new=is_new)
            return {"user": user, "is_new": is_new}
        except Exception as exc:
            session.rollback()
            logger.error("github_oauth_error", error=str(exc))
            return {"error": "处理 GitHub 登录时出现内部错误"}
        finally:
            session.close()

    # ==================== 内部方法 ====================

    def _store_state(self, provider: str, state: str, redirect: str) -> None:
        """将 OAuth state 存入数据库用于 CSRF 防护。"""
        settings = get_settings().auth
        session = get_auth_db_session()
        try:
            record = OAuthState(
                provider=provider,
                state=state,
                redirect_uri=redirect,
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc)
                + timedelta(minutes=settings.oauth_state_ttl_minutes),
            )
            session.add(record)
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.error("store_oauth_state_error", error=str(exc))
        finally:
            session.close()

    def _verify_state(self, state: str, provider: str) -> str | None:
        """校验 OAuth state 是否存在且未过期。返回 redirect_uri 或 None。"""
        session = get_auth_db_session()
        try:
            record = (
                session.query(OAuthState)
                .filter(
                    OAuthState.state == state,
                    OAuthState.provider == provider,
                )
                .first()
            )
            if not record:
                return None

            if record.expires_at and datetime.now(timezone.utc) > record.expires_at:
                session.delete(record)
                session.commit()
                return None

            redirect_uri = record.redirect_uri
            session.delete(record)
            session.commit()
            return redirect_uri
        finally:
            session.close()

    def _get_or_create_user(
        self,
        session,
        provider: str,
        provider_user_id: str,
        email: str,
        name: str,
        avatar: str,
    ) -> tuple:
        """
        查找或创建用户。

        优先级：
        1. 已有 OAuthLink 关联 → 直接返回
        2. 邮箱匹配已有用户 → 自动关联
        3. 都没有 → 创建新用户

        Returns:
            (User, is_new: bool)
        """
        # 1. 已有关联
        link = (
            session.query(OAuthLink)
            .filter(
                OAuthLink.provider == provider,
                OAuthLink.provider_user_id == provider_user_id,
            )
            .first()
        )
        if link:
            user = session.query(User).filter(User.id == link.user_id).first()
            if user:
                return user, False

        # 2. 邮箱匹配
        if email:
            existing = session.query(User).filter(User.email == email).first()
            if existing:
                oauth_link = OAuthLink(
                    user_id=existing.id,
                    provider=provider,
                    provider_user_id=provider_user_id,
                    email=email,
                    name=name,
                    avatar=avatar,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(oauth_link)
                return existing, False

        # 3. 创建新用户
        from app.auth.password import hash_password

        random_password = secrets.token_urlsafe(16)
        new_user = User(
            username=f"{provider}_{provider_user_id}",
            password_hash=hash_password(random_password),
            email=email,
            nickname=name,
            avatar=avatar,
            role="user",
            is_active=True,
            token_version=0,
            credits=0.0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(new_user)
        session.flush()  # 获取 new_user.id

        oauth_link = OAuthLink(
            user_id=new_user.id,
            provider=provider,
            provider_user_id=provider_user_id,
            email=email,
            name=name,
            avatar=avatar,
            created_at=datetime.now(timezone.utc),
        )
        session.add(oauth_link)
        return new_user, True
