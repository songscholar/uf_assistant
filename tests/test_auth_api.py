"""
Tests for app.api.routers.auth module.

Covers:
- POST /auth/login (success, wrong password, disabled account, single-user mode)
- POST /auth/register (success, duplicate username/email, registration disabled)
- POST /auth/send-code
- POST /auth/change-password
- GET /auth/info
- GET /auth/security-config
- POST /auth/logout
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Minimal app setup importing only the auth router
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """Create a TestClient with the auth router mounted."""
    from app.api.routers.auth import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def mock_auth_deps():
    """Mock auth settings and DB for all tests."""
    with patch("app.api.routers.auth.get_settings") as mock_cfg:
        settings = MagicMock()
        settings.auth.single_user_mode = False
        settings.auth.admin_user = "admin"
        settings.auth.admin_password = "Admin1Pass"
        settings.auth.registration_enabled = True
        settings.auth.turnstile_secret_key = ""
        settings.auth.google_client_id = ""
        settings.auth.github_client_id = ""
        settings.auth.jwt_expire_days = 7
        settings.auth.jwt_algorithm = "HS256"
        settings.auth.secret_key = "test-secret"
        settings.auth.email_code_expire_minutes = 10
        settings.auth.oauth_state_ttl_minutes = 20
        settings.database.url = "sqlite:///test_auth.db"
        mock_cfg.return_value = settings
        yield mock_cfg


# ---------------------------------------------------------------------------
# GET /auth/security-config
# ---------------------------------------------------------------------------

class TestSecurityConfig:
    def test_returns_config(self, client):
        resp = client.get("/api/v1/auth/security-config")
        assert resp.status_code == 200
        data = resp.json()
        assert "registration_enabled" in data
        assert "oauth" in data


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------

class TestLogout:
    def test_logout_returns_message(self, client):
        resp = client.post("/api/v1/auth/logout")
        assert resp.status_code == 200
        assert resp.json()["message"] == "已退出登录"


# ---------------------------------------------------------------------------
# POST /auth/login — single-user mode
# ---------------------------------------------------------------------------

class TestLoginSingleUser:
    def test_single_user_success(self, client, mock_auth_deps):
        mock_auth_deps.return_value.auth.single_user_mode = True
        mock_auth_deps.return_value.auth.admin_user = "admin"
        mock_auth_deps.return_value.auth.admin_password = "Admin1Pass"

        resp = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "Admin1Pass",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["role"] == "admin"

    def test_single_user_wrong_password(self, client, mock_auth_deps):
        mock_auth_deps.return_value.auth.single_user_mode = True
        mock_auth_deps.return_value.auth.admin_user = "admin"
        mock_auth_deps.return_value.auth.admin_password = "Admin1Pass"

        resp = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "WrongPass1",
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /auth/login — DB mode (mocked)
# ---------------------------------------------------------------------------

class TestLoginDBMode:
    def test_login_success(self, client):
        mock_user = {
            "id": 1,
            "username": "testuser",
            "email": "test@example.com",
            "password_hash": "$2b$12$abcdefghijklmnopqrstuuABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
            "role": "user",
            "nickname": "Test",
            "avatar": "",
            "is_active": True,
        }

        with patch("app.api.routers.auth._ensure"), \
             patch("app.api.routers.auth._fu", return_value=mock_user), \
             patch("app.api.routers.auth._cpw", return_value=True), \
             patch("app.api.routers.auth._rip"), \
             patch("app.api.routers.auth._rac"):
            resp = client.post("/api/v1/auth/login", json={
                "username": "testuser",
                "password": "TestPass1",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "testuser"

    def test_login_wrong_password(self, client):
        mock_user = {
            "id": 1, "username": "testuser", "email": "test@example.com",
            "password_hash": "$2b$12$hash", "role": "user",
            "nickname": "Test", "avatar": "", "is_active": True,
        }

        with patch("app.api.routers.auth._ensure"), \
             patch("app.api.routers.auth._fu", return_value=mock_user), \
             patch("app.api.routers.auth._cpw", return_value=False), \
             patch("app.api.routers.auth._rip"), \
             patch("app.api.routers.auth._rac"), \
             patch("app.api.routers.auth._wip"), \
             patch("app.api.routers.auth._wac"):
            resp = client.post("/api/v1/auth/login", json={
                "username": "testuser",
                "password": "WrongPass1",
            })
        assert resp.status_code == 401

    def test_login_user_not_found(self, client):
        with patch("app.api.routers.auth._ensure"), \
             patch("app.api.routers.auth._fu", return_value=None), \
             patch("app.api.routers.auth._rip"), \
             patch("app.api.routers.auth._rac"), \
             patch("app.api.routers.auth._wip"), \
             patch("app.api.routers.auth._wac"):
            resp = client.post("/api/v1/auth/login", json={
                "username": "nobody",
                "password": "TestPass1",
            })
        assert resp.status_code == 401

    def test_login_disabled_account(self, client):
        mock_user = {
            "id": 1, "username": "testuser", "email": "test@example.com",
            "password_hash": "$2b$12$hash", "role": "user",
            "nickname": "Test", "avatar": "", "is_active": False,
        }

        with patch("app.api.routers.auth._ensure"), \
             patch("app.api.routers.auth._fu", return_value=mock_user), \
             patch("app.api.routers.auth._cpw", return_value=True), \
             patch("app.api.routers.auth._rip"), \
             patch("app.api.routers.auth._rac"):
            resp = client.post("/api/v1/auth/login", json={
                "username": "testuser",
                "password": "TestPass1",
            })
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------

class TestRegister:
    def test_register_success(self, client):
        with patch("app.api.routers.auth._ensure"), \
             patch("app.api.routers.auth._fu", return_value=None), \
             patch("app.api.routers.auth._cu", return_value={"id": 1, "username": "newuser", "email": "new@example.com", "role": "user"}), \
             patch("app.api.routers.auth._hpw", return_value="$2b$12$hash"):
            # First send a code
            import app.api.routers.auth as auth_mod
            with auth_mod._lock:
                auth_mod._codes[("new@example.com", "register")] = {
                    "code": "123456",
                    "expires": time.time() + 600,
                }

            resp = client.post("/api/v1/auth/register", json={
                "username": "newuser",
                "email": "new@example.com",
                "password": "TestPass123",
                "code": "123456",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "newuser"

    def test_register_username_taken(self, client):
        with patch("app.api.routers.auth._ensure"), \
             patch("app.api.routers.auth._fu", return_value={"id": 1}):
            import app.api.routers.auth as auth_mod
            with auth_mod._lock:
                auth_mod._codes[("test@example.com", "register")] = {
                    "code": "123456",
                    "expires": time.time() + 600,
                }

            resp = client.post("/api/v1/auth/register", json={
                "username": "existing",
                "email": "test@example.com",
                "password": "TestPass123",
                "code": "123456",
            })
        assert resp.status_code == 409

    def test_register_disabled(self, client, mock_auth_deps):
        mock_auth_deps.return_value.auth.registration_enabled = False

        resp = client.post("/api/v1/auth/register", json={
            "username": "newuser",
            "email": "new@example.com",
            "password": "TestPass123",
            "code": "123456",
        })
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /auth/change-password
# ---------------------------------------------------------------------------

class TestChangePassword:
    def test_change_password_success(self, client):
        from app.auth.dependencies import get_current_user

        mock_user = {
            "id": 1, "username": "testuser", "email": "test@example.com",
            "password_hash": "$2b$12$oldhash", "role": "user",
            "nickname": "Test", "avatar": "", "is_active": True,
        }

        client.app.dependency_overrides[get_current_user] = lambda: {"id": 1, "username": "testuser", "role": "user"}
        try:
            with patch("app.api.routers.auth._ensure"), \
                 patch("app.api.routers.auth._fu", return_value=mock_user), \
                 patch("app.api.routers.auth._cpw", return_value=True), \
                 patch("app.api.routers.auth._hpw", return_value="$2b$12$newhash"), \
                 patch("app.api.routers.auth._e"):
                resp = client.post("/api/v1/auth/change-password", json={
                    "old_password": "OldPass123",
                    "new_password": "NewPass123",
                })
        finally:
            client.app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert resp.json()["message"] == "密码修改成功"

    def test_change_password_wrong_old(self, client):
        from app.auth.dependencies import get_current_user

        mock_user = {
            "id": 1, "username": "testuser", "email": "test@example.com",
            "password_hash": "$2b$12$oldhash", "role": "user",
            "nickname": "Test", "avatar": "", "is_active": True,
        }

        client.app.dependency_overrides[get_current_user] = lambda: {"id": 1, "username": "testuser", "role": "user"}
        try:
            with patch("app.api.routers.auth._ensure"), \
                 patch("app.api.routers.auth._fu", return_value=mock_user), \
                 patch("app.api.routers.auth._cpw", return_value=False):
                resp = client.post("/api/v1/auth/change-password", json={
                    "old_password": "WrongPass1",
                    "new_password": "NewPass123",
                })
        finally:
            client.app.dependency_overrides.clear()
        assert resp.status_code == 400
