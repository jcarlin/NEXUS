"""Tests for SAML SSO router endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from httpx import AsyncClient

from app.auth.schemas import UserRecord
from app.config import Settings

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_SAML_USER = UserRecord(
    id=UUID("00000000-0000-0000-0000-000000000043"),
    email="saml@example.com",
    password_hash="",
    full_name="SAML User",
    role="viewer",
    is_active=True,
    api_key_hash=None,
    created_at=datetime(2025, 1, 1, tzinfo=UTC),
    updated_at=datetime(2025, 1, 1, tzinfo=UTC),
)

_SAML_ATTRIBUTES = {
    "email": "saml@example.com",
    "name": "SAML User",
    "groups": ["admin_group"],
    "name_id": "saml-nameid-12345",
}


@pytest.fixture()
def saml_settings() -> Settings:
    """Settings with SAML enabled."""
    return Settings(
        enable_saml=True,
        saml_entity_id="https://nexus.example.com/saml",
        saml_idp_sso_url="https://idp.example.com/saml/sso",
        saml_idp_cert="MIICdummycert==",
        saml_role_mapping='{"admin_group": "admin", "attorney_group": "attorney"}',
        saml_default_role="viewer",
        anthropic_api_key="test-key",
        openai_api_key="test-key",
    )


# ---------------------------------------------------------------------------
# GET /auth/saml/info
# ---------------------------------------------------------------------------


class TestSAMLInfoEndpoint:
    """Test GET /auth/saml/info."""

    @pytest.mark.asyncio
    async def test_info_when_saml_disabled(self, client: AsyncClient) -> None:
        """Returns enabled=False when SAML is off (default test settings)."""
        resp = await client.get("/api/v1/auth/saml/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False

    @pytest.mark.asyncio
    async def test_info_when_saml_enabled(self, client: AsyncClient, saml_settings: Settings) -> None:
        """Returns provider info when SAML is enabled."""
        with patch("app.auth.saml_router.get_settings", return_value=saml_settings):
            resp = await client.get("/api/v1/auth/saml/info")

        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["provider_name"] == "SAML SSO"
        assert data["login_url"] == "/api/v1/auth/saml/login"


# ---------------------------------------------------------------------------
# GET /auth/saml/login
# ---------------------------------------------------------------------------


class TestSAMLLoginEndpoint:
    """Test GET /auth/saml/login."""

    @pytest.mark.asyncio
    async def test_login_redirects(self, client: AsyncClient, saml_settings: Settings) -> None:
        """Login endpoint returns 302 redirect to IdP."""
        mock_provider = MagicMock()
        mock_provider.get_authn_request_url.return_value = "https://idp.example.com/saml/sso?SAMLRequest=encoded"

        with (
            patch("app.auth.saml_router.get_settings", return_value=saml_settings),
            patch("app.auth.saml_router.get_saml_provider", return_value=mock_provider),
        ):
            resp = await client.get("/api/v1/auth/saml/login", follow_redirects=False)

        assert resp.status_code == 302
        assert "idp.example.com" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_login_when_disabled(self, client: AsyncClient) -> None:
        """Login returns 404 when SAML is disabled (request-time guard)."""
        resp = await client.get("/api/v1/auth/saml/login", follow_redirects=False)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_login_when_provider_none(self, client: AsyncClient, saml_settings: Settings) -> None:
        """Login returns 503 when SAML enabled but provider is None."""
        with (
            patch("app.auth.saml_router.get_settings", return_value=saml_settings),
            patch("app.auth.saml_router.get_saml_provider", return_value=None),
        ):
            resp = await client.get("/api/v1/auth/saml/login", follow_redirects=False)
        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /auth/saml/acs
# ---------------------------------------------------------------------------


class TestSAMLACSEndpoint:
    """Test POST /auth/saml/acs."""

    @pytest.mark.asyncio
    async def test_acs_with_valid_response(self, client: AsyncClient, saml_settings: Settings) -> None:
        """Successful ACS processes SAML response and returns JWT tokens."""
        mock_provider = MagicMock()
        mock_provider.entity_id = "https://nexus.example.com/saml"
        mock_provider.parse_acs_response.return_value = _SAML_ATTRIBUTES
        mock_provider.get_or_create_user = AsyncMock(return_value=(_SAML_USER, True))

        with (
            patch("app.auth.saml_router.get_settings", return_value=saml_settings),
            patch("app.auth.saml_router.get_saml_provider", return_value=mock_provider),
            patch("app.auth.saml_router.AuthService.create_access_token", return_value="test-access"),
            patch("app.auth.saml_router.AuthService.create_refresh_token", return_value="test-refresh"),
        ):
            resp = await client.post(
                "/api/v1/auth/saml/acs",
                data={"SAMLResponse": "base64encoded", "RelayState": ""},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] == "test-access"
        assert data["refresh_token"] == "test-refresh"
        assert data["is_new_user"] is True
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_acs_with_invalid_response(self, client: AsyncClient, saml_settings: Settings) -> None:
        """ACS returns 401 when SAML assertion is invalid."""
        mock_provider = MagicMock()
        mock_provider.entity_id = "https://nexus.example.com/saml"
        mock_provider.parse_acs_response.side_effect = ValueError("invalid assertion")

        with (
            patch("app.auth.saml_router.get_settings", return_value=saml_settings),
            patch("app.auth.saml_router.get_saml_provider", return_value=mock_provider),
        ):
            resp = await client.post(
                "/api/v1/auth/saml/acs",
                data={"SAMLResponse": "bad-response"},
            )

        assert resp.status_code == 401
        assert "SAML authentication failed" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_acs_rejects_missing_email(self, client: AsyncClient, saml_settings: Settings) -> None:
        """ACS returns 401 when assertion has no email."""
        mock_provider = MagicMock()
        mock_provider.entity_id = "https://nexus.example.com/saml"
        mock_provider.parse_acs_response.return_value = {"name_id": "abc", "name": "No Email", "groups": []}

        with (
            patch("app.auth.saml_router.get_settings", return_value=saml_settings),
            patch("app.auth.saml_router.get_saml_provider", return_value=mock_provider),
        ):
            resp = await client.post(
                "/api/v1/auth/saml/acs",
                data={"SAMLResponse": "base64encoded"},
            )

        assert resp.status_code == 401
        assert "email" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_acs_when_disabled(self, client: AsyncClient) -> None:
        """ACS returns 404 when SAML is disabled (request-time guard)."""
        resp = await client.post(
            "/api/v1/auth/saml/acs",
            data={"SAMLResponse": "base64encoded"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_acs_when_provider_none(self, client: AsyncClient, saml_settings: Settings) -> None:
        """ACS returns 503 when SAML enabled but provider is None."""
        with (
            patch("app.auth.saml_router.get_settings", return_value=saml_settings),
            patch("app.auth.saml_router.get_saml_provider", return_value=None),
        ):
            resp = await client.post(
                "/api/v1/auth/saml/acs",
                data={"SAMLResponse": "base64encoded"},
            )
        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# GET /auth/saml/metadata.xml
# ---------------------------------------------------------------------------


class TestSAMLMetadataEndpoint:
    """Test GET /auth/saml/metadata.xml."""

    @pytest.mark.asyncio
    async def test_metadata_returns_xml(self, client: AsyncClient, saml_settings: Settings) -> None:
        """Metadata endpoint returns XML content."""
        mock_provider = MagicMock()
        mock_provider.get_sp_metadata.return_value = '<?xml version="1.0"?><md:EntityDescriptor/>'

        with (
            patch("app.auth.saml_router.get_settings", return_value=saml_settings),
            patch("app.auth.saml_router.get_saml_provider", return_value=mock_provider),
        ):
            resp = await client.get("/api/v1/auth/saml/metadata.xml")

        assert resp.status_code == 200
        assert "xml" in resp.headers.get("content-type", "")
        assert resp.text.startswith("<?xml")

    @pytest.mark.asyncio
    async def test_metadata_when_disabled(self, client: AsyncClient) -> None:
        """Metadata returns 404 when SAML is disabled (request-time guard)."""
        resp = await client.get("/api/v1/auth/saml/metadata.xml")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_metadata_when_provider_none(self, client: AsyncClient, saml_settings: Settings) -> None:
        """Metadata returns 503 when SAML enabled but provider is None."""
        with (
            patch("app.auth.saml_router.get_settings", return_value=saml_settings),
            patch("app.auth.saml_router.get_saml_provider", return_value=None),
        ):
            resp = await client.get("/api/v1/auth/saml/metadata.xml")
        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_metadata_generation_failure(self, client: AsyncClient, saml_settings: Settings) -> None:
        """Metadata returns 500 when generation fails."""
        mock_provider = MagicMock()
        mock_provider.get_sp_metadata.side_effect = ValueError("invalid metadata")

        with (
            patch("app.auth.saml_router.get_settings", return_value=saml_settings),
            patch("app.auth.saml_router.get_saml_provider", return_value=mock_provider),
        ):
            resp = await client.get("/api/v1/auth/saml/metadata.xml")

        assert resp.status_code == 500
        assert "metadata" in resp.json()["detail"].lower()
