"""
Tests for app.auth.jwt_auth module.

Covers:
- JWT token generation
- JWT token verification
- Expired token handling
- Invalid token handling
- Token version verification
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt
import pytest

from app.auth.jwt_auth import generate_token, verify_token, verify_token_version


@pytest.fixture(autouse=True)
def mock_settings():
    """Provide consistent JWT settings for all tests."""
    with patch("app.auth.jwt_auth.get_settings") as mock:
        settings = MagicMock()
        settings.auth.secret_key = "test-secret-key-for-jwt"
        settings.auth.jwt_algorithm = "HS256"
        settings.auth.jwt_expire_days = 7
        settings.auth.single_user_mode = False
        mock.return_value = settings
        yield mock


class TestGenerateToken:
    def test_returns_string(self):
        token = generate_token(1, "testuser", "user", 1)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_claims(self):
        token = generate_token(42, "alice", "admin", 3)
        payload = jwt.decode(token, "test-secret-key-for-jwt", algorithms=["HS256"])
        assert payload["user_id"] == 42
        assert payload["sub"] == "alice"
        assert payload["role"] == "admin"
        assert payload["token_version"] == 3
        assert "exp" in payload
        assert "iat" in payload


class TestVerifyToken:
    def test_valid_token(self):
        token = generate_token(1, "testuser", "user", 1)
        payload = verify_token(token)
        assert payload is not None
        assert payload["user_id"] == 1

    def test_expired_token(self):
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "test",
            "user_id": 1,
            "role": "user",
            "token_version": 1,
            "iat": now - timedelta(days=30),
            "exp": now - timedelta(days=1),
        }
        token = jwt.encode(payload, "test-secret-key-for-jwt", algorithm="HS256")
        assert verify_token(token) is None

    def test_invalid_token_string(self):
        assert verify_token("not.a.valid.token") is None

    def test_wrong_secret(self):
        token = jwt.encode(
            {"sub": "x", "user_id": 1, "role": "user", "token_version": 1,
             "iat": datetime.now(timezone.utc),
             "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            "wrong-secret",
            algorithm="HS256",
        )
        assert verify_token(token) is None


class TestVerifyTokenVersion:
    def test_single_user_mode_always_true(self):
        with patch("app.auth.jwt_auth.get_settings") as mock:
            settings = MagicMock()
            settings.auth.single_user_mode = True
            mock.return_value = settings
            assert verify_token_version({"user_id": 1, "token_version": 999}) is True

    def test_matching_version(self):
        mock_user = MagicMock()
        mock_user.token_version = 5

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_user

        with patch("app.auth.models.get_auth_db_session", return_value=mock_session):
            result = verify_token_version({"user_id": 1, "token_version": 5})
            assert result is True

    def test_mismatched_version(self):
        mock_user = MagicMock()
        mock_user.token_version = 5

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_user

        with patch("app.auth.models.get_auth_db_session", return_value=mock_session):
            result = verify_token_version({"user_id": 1, "token_version": 3})
            assert result is False

    def test_user_not_found(self):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        with patch("app.auth.models.get_auth_db_session", return_value=mock_session):
            result = verify_token_version({"user_id": 999, "token_version": 1})
            assert result is False

    def test_missing_claims(self):
        assert verify_token_version({"user_id": 1}) is False
        assert verify_token_version({"token_version": 1}) is False
        assert verify_token_version({}) is False
