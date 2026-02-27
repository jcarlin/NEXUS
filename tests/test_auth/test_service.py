"""Tests for AuthService: password hashing, user auth, JWT roundtrip."""

from __future__ import annotations

from uuid import uuid4

from app.auth.service import AuthService
from app.config import Settings


def _test_settings() -> Settings:
    return Settings(
        jwt_secret_key="test-secret-key-for-jwt-testing-only",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
        jwt_refresh_token_expire_days=7,
    )


def test_hash_password_produces_bcrypt():
    hashed = AuthService.hash_password("my-secure-password")
    assert hashed.startswith("$2b$")
    assert AuthService.verify_password("my-secure-password", hashed)


def test_verify_password_wrong():
    hashed = AuthService.hash_password("correct-password")
    assert not AuthService.verify_password("wrong-password", hashed)


def test_access_token_roundtrip():
    settings = _test_settings()
    user_id = uuid4()
    token = AuthService.create_access_token(user_id, "attorney", settings)
    payload = AuthService.decode_token(token, settings)

    assert payload["sub"] == str(user_id)
    assert payload["role"] == "attorney"
    assert payload["type"] == "access"


def test_refresh_token_roundtrip():
    settings = _test_settings()
    user_id = uuid4()
    token = AuthService.create_refresh_token(user_id, settings)
    payload = AuthService.decode_token(token, settings)

    assert payload["sub"] == str(user_id)
    assert payload["type"] == "refresh"
