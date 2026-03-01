"""E2E tests for auth endpoints.

Covers:
  POST /api/v1/auth/login
  POST /api/v1/auth/refresh
  GET  /api/v1/auth/me

No matter header is required for login or refresh. The seed admin user
(admin@nexus.dev / changeme123!) is created by Alembic migration 002.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
ME_URL = "/api/v1/auth/me"

ADMIN_EMAIL = "admin@nexus.dev"
ADMIN_PASSWORD = "changeme123!"
ADMIN_ROLE = "admin"


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_login_valid_credentials(e2e_client: AsyncClient) -> None:
    """Login with valid seed admin credentials returns 200 with both tokens."""
    resp = await e2e_client.post(
        LOGIN_URL,
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data, "Response missing 'access_token'"
    assert "refresh_token" in data, "Response missing 'refresh_token'"
    assert "expires_in" in data, "Response missing 'expires_in'"
    assert isinstance(data["access_token"], str) and data["access_token"]
    assert isinstance(data["refresh_token"], str) and data["refresh_token"]
    assert isinstance(data["expires_in"], int) and data["expires_in"] > 0


@pytest.mark.e2e
async def test_login_invalid_credentials(e2e_client: AsyncClient) -> None:
    """Login with wrong password returns 401."""
    resp = await e2e_client.post(
        LOGIN_URL,
        json={"email": ADMIN_EMAIL, "password": "wrong-password!"},
    )

    assert resp.status_code == 401


@pytest.mark.e2e
async def test_login_nonexistent_user(e2e_client: AsyncClient) -> None:
    """Login with an unknown email address returns 401."""
    resp = await e2e_client.post(
        LOGIN_URL,
        json={"email": "nobody@nexus.dev", "password": ADMIN_PASSWORD},
    )

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_refresh_token(e2e_client: AsyncClient) -> None:
    """Using a valid refresh token returns a new pair of tokens."""
    login_resp = await e2e_client.post(
        LOGIN_URL,
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    refresh_token = login_resp.json()["refresh_token"]

    resp = await e2e_client.post(
        REFRESH_URL,
        json={"refresh_token": refresh_token},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data, "Refresh response missing 'access_token'"
    assert "refresh_token" in data, "Refresh response missing 'refresh_token'"
    assert "expires_in" in data, "Refresh response missing 'expires_in'"
    assert isinstance(data["access_token"], str) and data["access_token"]
    assert isinstance(data["expires_in"], int) and data["expires_in"] > 0


@pytest.mark.e2e
async def test_refresh_invalid_token(e2e_client: AsyncClient) -> None:
    """Submitting a malformed or expired refresh token returns 401."""
    resp = await e2e_client.post(
        REFRESH_URL,
        json={"refresh_token": "not-a-valid-token"},
    )

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_me_with_valid_token(e2e_client: AsyncClient) -> None:
    """GET /me with a valid bearer token returns the correct email and role."""
    login_resp = await e2e_client.post(
        LOGIN_URL,
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    access_token = login_resp.json()["access_token"]

    resp = await e2e_client.get(
        ME_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == ADMIN_EMAIL, f"Expected email '{ADMIN_EMAIL}', got '{data.get('email')}'"
    assert data["role"] == ADMIN_ROLE, f"Expected role '{ADMIN_ROLE}', got '{data.get('role')}'"


@pytest.mark.e2e
async def test_me_without_auth(e2e_client: AsyncClient) -> None:
    """GET /me with no Authorization header returns 401."""
    resp = await e2e_client.get(ME_URL)

    assert resp.status_code == 401
