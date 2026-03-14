"""Tests for OIDC SSO flow: provider logic and router endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from httpx import AsyncClient

from app.auth.oidc import OIDCProvider
from app.auth.schemas import UserRecord
from app.config import Settings

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_SSO_USER = UserRecord(
    id=UUID("00000000-0000-0000-0000-000000000042"),
    email="sso@example.com",
    password_hash="",
    full_name="SSO User",
    role="reviewer",
    is_active=True,
    api_key_hash=None,
    created_at=datetime(2025, 1, 1, tzinfo=UTC),
    updated_at=datetime(2025, 1, 1, tzinfo=UTC),
)

_USERINFO = {
    "sub": "google-oauth2|12345",
    "email": "sso@example.com",
    "name": "SSO User",
    "groups": ["admin_group"],
}


@pytest.fixture()
def sso_settings() -> Settings:
    """Settings with SSO enabled."""
    return Settings(
        enable_sso=True,
        oidc_provider_name="TestIDP",
        oidc_client_id="test-client-id",
        oidc_client_secret="test-client-secret",
        oidc_issuer_url="https://idp.example.com",
        oidc_redirect_uri="http://localhost:5173/auth/oidc/callback",
        oidc_role_mapping='{"admin_group": "admin", "attorney_group": "attorney"}',
        oidc_default_role="reviewer",
        anthropic_api_key="test-key",
        openai_api_key="test-key",
    )


@pytest.fixture()
def provider(sso_settings: Settings) -> OIDCProvider:
    """OIDCProvider with test settings."""
    return OIDCProvider(sso_settings)


# ---------------------------------------------------------------------------
# Unit tests: OIDCProvider
# ---------------------------------------------------------------------------


class TestMapRole:
    """Test group-to-role mapping."""

    def test_matching_group(self, provider: OIDCProvider) -> None:
        assert provider.map_role(["admin_group"]) == "admin"

    def test_multiple_groups_first_match(self, provider: OIDCProvider) -> None:
        assert provider.map_role(["unknown", "attorney_group"]) == "attorney"

    def test_no_matching_group_returns_default(self, provider: OIDCProvider) -> None:
        assert provider.map_role(["other_group"]) == "reviewer"

    def test_empty_groups_returns_default(self, provider: OIDCProvider) -> None:
        assert provider.map_role([]) == "reviewer"


class TestGetOrCreateUser:
    """Test JIT user provisioning."""

    @pytest.mark.asyncio
    async def test_creates_new_user(self, provider: OIDCProvider) -> None:
        """First SSO login creates a new user."""
        mock_db = AsyncMock()
        # First query: no existing SSO user
        mock_result_sso = MagicMock()
        mock_result_sso.first.return_value = None
        # Second query (get_user_by_email): no existing email user
        mock_result_email = MagicMock()
        mock_result_email.first.return_value = None

        mock_db.execute = AsyncMock(side_effect=[mock_result_sso, mock_result_email, MagicMock()])

        user, is_new = await provider.get_or_create_user(mock_db, _USERINFO)

        assert is_new is True
        assert user.email == "sso@example.com"
        assert user.full_name == "SSO User"
        assert user.role == "admin"  # admin_group maps to admin
        assert user.password_hash == ""
        assert mock_db.flush.await_count == 1

    @pytest.mark.asyncio
    async def test_finds_existing_sso_user(self, provider: OIDCProvider) -> None:
        """Returning SSO user is found by subject ID."""
        mock_db = AsyncMock()
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": _SSO_USER.id,
            "email": _SSO_USER.email,
            "password_hash": "",
            "full_name": _SSO_USER.full_name,
            "role": _SSO_USER.role,
            "api_key_hash": None,
            "is_active": True,
            "created_at": _SSO_USER.created_at,
            "updated_at": _SSO_USER.updated_at,
        }
        mock_result = MagicMock()
        mock_result.first.return_value = mock_row

        mock_db.execute = AsyncMock(return_value=mock_result)

        user, is_new = await provider.get_or_create_user(mock_db, _USERINFO)

        assert is_new is False
        assert user.id == _SSO_USER.id

    @pytest.mark.asyncio
    async def test_links_existing_email_account(self, provider: OIDCProvider) -> None:
        """Existing user with matching email gets SSO linked."""
        mock_db = AsyncMock()
        # First query: no SSO match
        mock_result_sso = MagicMock()
        mock_result_sso.first.return_value = None
        # Second query (get_user_by_email): existing email user
        mock_result_email = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": _SSO_USER.id,
            "email": _SSO_USER.email,
            "password_hash": "$2b$12$existing",
            "full_name": _SSO_USER.full_name,
            "role": _SSO_USER.role,
            "api_key_hash": None,
            "is_active": True,
            "created_at": _SSO_USER.created_at,
            "updated_at": _SSO_USER.updated_at,
        }
        mock_result_email.first.return_value = mock_row

        mock_db.execute = AsyncMock(side_effect=[mock_result_sso, mock_result_email, MagicMock()])

        user, is_new = await provider.get_or_create_user(mock_db, _USERINFO)

        assert is_new is False
        assert user.id == _SSO_USER.id
        assert mock_db.flush.await_count == 1


# ---------------------------------------------------------------------------
# Router endpoint tests
# ---------------------------------------------------------------------------


class TestOIDCInfoEndpoint:
    """Test GET /auth/oidc/info."""

    @pytest.mark.asyncio
    async def test_info_when_sso_disabled(self, client: AsyncClient) -> None:
        """Returns enabled=False when SSO is off (default test settings)."""
        resp = await client.get("/api/v1/auth/oidc/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False

    @pytest.mark.asyncio
    async def test_info_when_sso_enabled(self, client: AsyncClient, sso_settings: Settings) -> None:
        """Returns provider info when SSO is enabled."""
        mock_provider = MagicMock()
        mock_provider.provider_name = "TestIDP"
        mock_provider.get_authorize_url = AsyncMock(return_value="https://idp.example.com/authorize?client_id=test")

        with (
            patch("app.auth.oidc_router.get_settings", return_value=sso_settings),
            patch("app.auth.oidc_router.get_oidc_provider", return_value=mock_provider),
        ):
            resp = await client.get("/api/v1/auth/oidc/info")

        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["provider_name"] == "TestIDP"


class TestOIDCCallbackEndpoint:
    """Test GET /auth/oidc/callback."""

    @pytest.mark.asyncio
    async def test_callback_returns_tokens(self, client: AsyncClient, sso_settings: Settings) -> None:
        """Successful OIDC callback issues JWT tokens."""
        mock_provider = MagicMock()
        mock_provider.exchange_code = AsyncMock(return_value=_USERINFO)
        mock_provider.get_or_create_user = AsyncMock(return_value=(_SSO_USER, True))

        with (
            patch("app.auth.oidc_router.get_settings", return_value=sso_settings),
            patch("app.auth.oidc_router.get_oidc_provider", return_value=mock_provider),
            patch("app.auth.oidc_router.AuthService.create_access_token", return_value="test-access"),
            patch("app.auth.oidc_router.AuthService.create_refresh_token", return_value="test-refresh"),
        ):
            resp = await client.get(
                "/api/v1/auth/oidc/callback",
                params={"code": "auth-code-123", "state": "random-state"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] == "test-access"
        assert data["refresh_token"] == "test-refresh"
        assert data["is_new_user"] is True
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_callback_rejects_when_disabled(self, client: AsyncClient) -> None:
        """Callback returns 404 when SSO is disabled."""
        disabled_settings = Settings(
            enable_sso=False,
            anthropic_api_key="test-key",
            openai_api_key="test-key",
        )
        with patch("app.auth.oidc_router.get_settings", return_value=disabled_settings):
            resp = await client.get(
                "/api/v1/auth/oidc/callback",
                params={"code": "auth-code-123"},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_callback_rejects_missing_email(self, client: AsyncClient, sso_settings: Settings) -> None:
        """Callback returns 401 when provider doesn't return email."""
        mock_provider = MagicMock()
        mock_provider.exchange_code = AsyncMock(return_value={"sub": "123"})

        with (
            patch("app.auth.oidc_router.get_settings", return_value=sso_settings),
            patch("app.auth.oidc_router.get_oidc_provider", return_value=mock_provider),
        ):
            resp = await client.get(
                "/api/v1/auth/oidc/callback",
                params={"code": "auth-code-123"},
            )

        assert resp.status_code == 401
        assert "email" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_callback_rejects_on_exchange_failure(self, client: AsyncClient, sso_settings: Settings) -> None:
        """Callback returns 401 when token exchange fails."""
        mock_provider = MagicMock()
        mock_provider.exchange_code = AsyncMock(side_effect=Exception("connection refused"))

        with (
            patch("app.auth.oidc_router.get_settings", return_value=sso_settings),
            patch("app.auth.oidc_router.get_oidc_provider", return_value=mock_provider),
        ):
            resp = await client.get(
                "/api/v1/auth/oidc/callback",
                params={"code": "auth-code-123"},
            )

        assert resp.status_code == 401
        assert "OIDC authentication failed" in resp.json()["detail"]


class TestOIDCProviderInit:
    """Test OIDCProvider initialization."""

    def test_invalid_role_mapping_json(self) -> None:
        """Invalid JSON in role mapping logs warning but doesn't crash."""
        settings = Settings(
            enable_sso=True,
            oidc_role_mapping="not-json",
            anthropic_api_key="test-key",
            openai_api_key="test-key",
        )
        provider = OIDCProvider(settings)
        assert provider._role_mapping == {}

    def test_empty_role_mapping(self) -> None:
        """Empty role mapping string produces empty dict."""
        settings = Settings(
            enable_sso=True,
            oidc_role_mapping="",
            anthropic_api_key="test-key",
            openai_api_key="test-key",
        )
        provider = OIDCProvider(settings)
        assert provider._role_mapping == {}

    def test_valid_role_mapping(self) -> None:
        """Valid JSON role mapping is parsed correctly."""
        settings = Settings(
            enable_sso=True,
            oidc_role_mapping='{"admins": "admin"}',
            anthropic_api_key="test-key",
            openai_api_key="test-key",
        )
        provider = OIDCProvider(settings)
        assert provider._role_mapping == {"admins": "admin"}
