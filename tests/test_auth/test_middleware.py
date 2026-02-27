"""Tests for auth middleware: get_current_user, require_role, get_matter_id."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID

import jwt
import pytest
from httpx import AsyncClient

from app.config import Settings

_SETTINGS = Settings(
    jwt_secret_key="test-middleware-secret",
    jwt_algorithm="HS256",
    jwt_access_token_expire_minutes=30,
    jwt_refresh_token_expire_days=7,
)

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

_REVIEWER_USER = {**_FAKE_USER, "role": "reviewer", "email": "reviewer@nexus.dev"}


def _make_token(user_id: str, role: str = "admin", token_type: str = "access", expired: bool = False) -> str:
    """Create a test JWT."""
    from datetime import UTC, datetime, timedelta

    if expired:
        exp = datetime.now(UTC) - timedelta(hours=1)
    else:
        exp = datetime.now(UTC) + timedelta(hours=1)

    return jwt.encode(
        {"sub": user_id, "role": role, "type": token_type, "exp": exp},
        _SETTINGS.jwt_secret_key,
        algorithm=_SETTINGS.jwt_algorithm,
    )


@pytest.mark.asyncio
async def test_unauthenticated_request(unauthed_client: AsyncClient):
    """Request without auth headers returns 401."""
    resp = await unauthed_client.get("/api/v1/documents")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_valid_jwt_passes(unauthed_client: AsyncClient):
    """Request with a valid JWT passes auth."""
    token = _make_token(str(_FAKE_USER["id"]))

    with (
        patch("app.auth.middleware.get_settings", return_value=_SETTINGS),
        patch("app.auth.middleware.AuthService.get_user_by_id", new_callable=AsyncMock, return_value=_FAKE_USER),
        patch("app.auth.middleware.AuthService.matter_exists", new_callable=AsyncMock, return_value=True),
        patch("app.auth.middleware.AuthService.check_user_matter_access", new_callable=AsyncMock, return_value=True),
    ):
        resp = await unauthed_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_expired_jwt_returns_401(unauthed_client: AsyncClient):
    """Request with an expired JWT returns 401."""
    token = _make_token(str(_FAKE_USER["id"]), expired=True)

    with patch("app.auth.middleware.get_settings", return_value=_SETTINGS):
        resp = await unauthed_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_key_auth_passes(unauthed_client: AsyncClient):
    """Request with a valid X-API-Key passes auth."""
    with (
        patch("app.auth.middleware.get_settings", return_value=_SETTINGS),
        patch("app.auth.middleware.AuthService.get_user_by_api_key", new_callable=AsyncMock, return_value=_FAKE_USER),
        patch("app.auth.middleware.AuthService.matter_exists", new_callable=AsyncMock, return_value=True),
        patch("app.auth.middleware.AuthService.check_user_matter_access", new_callable=AsyncMock, return_value=True),
    ):
        resp = await unauthed_client.get(
            "/api/v1/auth/me",
            headers={"X-API-Key": "test-api-key-123"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_missing_matter_header_returns_400(unauthed_client: AsyncClient):
    """Request with valid auth but missing X-Matter-ID returns 400."""
    token = _make_token(str(_FAKE_USER["id"]))

    with (
        patch("app.auth.middleware.get_settings", return_value=_SETTINGS),
        patch("app.auth.middleware.AuthService.get_user_by_id", new_callable=AsyncMock, return_value=_FAKE_USER),
    ):
        # GET /documents requires both auth AND matter_id
        resp = await unauthed_client.get(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 400
    assert "X-Matter-ID" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_user_not_assigned_to_matter_returns_403(unauthed_client: AsyncClient):
    """User without access to the requested matter gets 403."""
    token = _make_token(str(_REVIEWER_USER["id"]), role="reviewer")

    with (
        patch("app.auth.middleware.get_settings", return_value=_SETTINGS),
        patch("app.auth.middleware.AuthService.get_user_by_id", new_callable=AsyncMock, return_value=_REVIEWER_USER),
        patch("app.auth.middleware.AuthService.matter_exists", new_callable=AsyncMock, return_value=True),
        patch("app.auth.middleware.AuthService.check_user_matter_access", new_callable=AsyncMock, return_value=False),
    ):
        resp = await unauthed_client.get(
            "/api/v1/documents",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Matter-ID": "00000000-0000-0000-0000-000000000099",
            },
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_health_endpoint_no_auth_required(unauthed_client: AsyncClient):
    """GET /health does NOT require auth."""
    resp = await unauthed_client.get("/api/v1/health")
    # May return 503 if services are down, but NOT 401
    assert resp.status_code != 401
