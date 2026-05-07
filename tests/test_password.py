"""
Tests for app.auth.password module.

Covers:
- bcrypt password hashing
- SHA-256 fallback verification
- Password strength validation
- Random password generation
"""

from __future__ import annotations

import pytest

from app.auth.password import (
    generate_random_password,
    hash_password,
    validate_password_strength,
    verify_password,
)


class TestHashPassword:
    def test_hash_returns_bcrypt_string(self):
        result = hash_password("Test1234")
        assert result.startswith("$2b$")
        assert len(result) == 60

    def test_hash_different_each_time(self):
        h1 = hash_password("Test1234")
        h2 = hash_password("Test1234")
        assert h1 != h2

    def test_hash_unicode_password(self):
        result = hash_password("密码测试123Aa")
        assert result.startswith("$2b$")


class TestVerifyPassword:
    def test_verify_bcrypt_correct(self):
        pw = "MySecure1Pass"
        h = hash_password(pw)
        assert verify_password(pw, h) is True

    def test_verify_bcrypt_wrong(self):
        h = hash_password("Correct1Pass")
        assert verify_password("Wrong1Pass", h) is False

    def test_verify_sha256_fallback(self):
        import hashlib
        import hmac as _hmac

        salt = "testsalt"
        pw = "TestPass1"
        computed = hashlib.sha256((salt + pw).encode()).hexdigest()
        h = f"sha256${salt}${computed}"
        assert verify_password(pw, h) is True

    def test_verify_sha256_wrong(self):
        import hashlib

        salt = "testsalt"
        computed = hashlib.sha256((salt + "Correct1").encode()).hexdigest()
        h = f"sha256${salt}${computed}"
        assert verify_password("Wrong1Pass", h) is False

    def test_verify_empty_hash(self):
        assert verify_password("anything", "") is False

    def test_verify_none_hash(self):
        assert verify_password("anything", None) is False

    def test_verify_unknown_format(self):
        assert verify_password("anything", "md5$abc") is False

    def test_verify_sha256_malformed(self):
        assert verify_password("anything", "sha256$only_one_part") is False


class TestValidatePasswordStrength:
    def test_valid_password(self):
        ok, msg = validate_password_strength("MyPass123")
        assert ok is True
        assert msg == ""

    def test_too_short(self):
        ok, msg = validate_password_strength("Ab1")
        assert ok is False
        assert "8" in msg

    def test_no_uppercase(self):
        ok, msg = validate_password_strength("mypass123")
        assert ok is False
        assert "大写" in msg

    def test_no_lowercase(self):
        ok, msg = validate_password_strength("MYPASS123")
        assert ok is False
        assert "小写" in msg

    def test_no_digit(self):
        ok, msg = validate_password_strength("MyPassWord")
        assert ok is False
        assert "数字" in msg

    def test_exactly_8_chars_valid(self):
        ok, _ = validate_password_strength("Abcdef1g")
        assert ok is True


class TestGenerateRandomPassword:
    def test_default_length(self):
        pw = generate_random_password()
        assert len(pw) > 0

    def test_custom_length(self):
        pw = generate_random_password(length=32)
        assert len(pw) > 20

    def test_unique_each_call(self):
        p1 = generate_random_password()
        p2 = generate_random_password()
        assert p1 != p2
