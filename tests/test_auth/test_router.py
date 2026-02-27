"""Tests for auth router endpoints: login, refresh, me."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from httpx import AsyncClient

_FAKE_USER = {
    "id": UUID("00000000-0000-0000-0000-000000000001"),
    "email": "admin@nexus.dev",
    "password_hash": "$2b$12$fake",
    "full_name": "Admin User",
    "role": "admin",
    "is_active": True,
    "api_key_hash": None,
    "created_at": "2025-01-01T00:00:00+00:00",
    "updated_at": "2025-01-01T00:00:00+00:00",
}


@pytest.mark.asyncio
async def test_login_success(unauthed_client: AsyncClient):
    """POST /auth/login with valid credentials returns tokens."""
    with (
        patch("app.auth.router.AuthService.authenticate_user", new_callable=AsyncMock, return_value=_FAKE_USER),
        patch("app.auth.router.AuthService.create_access_token", return_value="test-access"),
        patch("app.auth.router.AuthService.create_refresh_token", return_value="test-refresh"),
    ):
        resp = await unauthed_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nexus.dev", "password": "changeme123!"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"] == "test-access"
    assert data["refresh_token"] == "test-refresh"
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_credentials(unauthed_client: AsyncClient):
    """POST /auth/login with bad credentials returns 401."""
    with patch("app.auth.router.AuthService.authenticate_user", new_callable=AsyncMock, return_value=None):
        resp = await unauthed_client.post(
            "/api/v1/auth/login",
            json={"email": "bad@nexus.dev", "password": "wrong"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_returns_new_tokens(unauthed_client: AsyncClient):
    """POST /auth/refresh with a valid refresh token returns new tokens."""
    with (
        patch(
            "app.auth.router.AuthService.decode_token",
            return_value={"sub": str(_FAKE_USER["id"]), "type": "refresh", "exp": 9999999999},
        ),
        patch("app.auth.router.AuthService.get_user_by_id", new_callable=AsyncMock, return_value=_FAKE_USER),
        patch("app.auth.router.AuthService.create_access_token", return_value="new-access"),
        patch("app.auth.router.AuthService.create_refresh_token", return_value="new-refresh"),
    ):
        resp = await unauthed_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "valid-refresh-token"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"] == "new-access"


@pytest.mark.asyncio
async def test_me_returns_current_user(client: AsyncClient):
    """GET /auth/me returns the current user (auth overridden in conftest)."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "test@nexus.dev"
    assert data["role"] == "admin"
