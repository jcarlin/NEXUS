"""Tests for SAML SSO flow: SAMLProvider logic."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.auth.saml import SAMLProvider, _build_request_data
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


@pytest.fixture()
def provider(saml_settings: Settings) -> SAMLProvider:
    """SAMLProvider with test settings."""
    return SAMLProvider(saml_settings)


# ---------------------------------------------------------------------------
# Unit tests: SAMLProvider initialization
# ---------------------------------------------------------------------------


class TestSAMLProviderInit:
    """Test SAMLProvider initialization."""

    def test_valid_role_mapping(self) -> None:
        """Valid JSON role mapping is parsed correctly."""
        settings = Settings(
            enable_saml=True,
            saml_entity_id="https://nexus.example.com/saml",
            saml_idp_sso_url="https://idp.example.com/saml/sso",
            saml_idp_cert="MIICdummycert==",
            saml_role_mapping='{"admins": "admin"}',
            saml_default_role="viewer",
            anthropic_api_key="test-key",
            openai_api_key="test-key",
        )
        p = SAMLProvider(settings)
        assert p._role_mapping == {"admins": "admin"}

    def test_invalid_role_mapping_json(self) -> None:
        """Invalid JSON in role mapping logs warning but doesn't crash."""
        settings = Settings(
            enable_saml=True,
            saml_entity_id="https://nexus.example.com/saml",
            saml_idp_sso_url="https://idp.example.com/saml/sso",
            saml_idp_cert="MIICdummycert==",
            saml_role_mapping="not-json",
            saml_default_role="viewer",
            anthropic_api_key="test-key",
            openai_api_key="test-key",
        )
        p = SAMLProvider(settings)
        assert p._role_mapping == {}

    def test_empty_role_mapping(self) -> None:
        """Empty role mapping string produces empty dict."""
        settings = Settings(
            enable_saml=True,
            saml_entity_id="https://nexus.example.com/saml",
            saml_idp_sso_url="https://idp.example.com/saml/sso",
            saml_idp_cert="MIICdummycert==",
            saml_role_mapping="",
            saml_default_role="viewer",
            anthropic_api_key="test-key",
            openai_api_key="test-key",
        )
        p = SAMLProvider(settings)
        assert p._role_mapping == {}

    def test_settings_stored(self, provider: SAMLProvider) -> None:
        """Provider stores settings correctly."""
        assert provider.entity_id == "https://nexus.example.com/saml"
        assert provider.idp_sso_url == "https://idp.example.com/saml/sso"
        assert provider.default_role == "viewer"


# ---------------------------------------------------------------------------
# Unit tests: get_saml_settings
# ---------------------------------------------------------------------------


class TestGetSamlSettings:
    """Test _get_saml_settings() dict generation."""

    def test_basic_structure(self, provider: SAMLProvider) -> None:
        """Settings dict has required keys."""
        s = provider._get_saml_settings()
        assert s["strict"] is True
        assert "sp" in s
        assert "idp" in s
        assert s["sp"]["entityId"] == "https://nexus.example.com/saml"
        assert s["idp"]["singleSignOnService"]["url"] == "https://idp.example.com/saml/sso"
        assert s["idp"]["x509cert"] == "MIICdummycert=="

    def test_sp_cert_included_when_set(self) -> None:
        """SP cert and key are included when configured."""
        settings = Settings(
            enable_saml=True,
            saml_entity_id="https://nexus.example.com/saml",
            saml_idp_sso_url="https://idp.example.com/saml/sso",
            saml_idp_cert="MIICdummycert==",
            saml_sp_cert="MIICspcert==",
            saml_sp_key="MIICspkey==",
            anthropic_api_key="test-key",
            openai_api_key="test-key",
        )
        p = SAMLProvider(settings)
        s = p._get_saml_settings()
        assert s["sp"]["x509cert"] == "MIICspcert=="
        assert s["sp"]["privateKey"] == "MIICspkey=="
        assert s["security"]["authnRequestsSigned"] is True


# ---------------------------------------------------------------------------
# Unit tests: map_role
# ---------------------------------------------------------------------------


class TestMapRole:
    """Test group-to-role mapping."""

    def test_matching_group(self, provider: SAMLProvider) -> None:
        assert provider.map_role(["admin_group"]) == "admin"

    def test_multiple_groups_first_match(self, provider: SAMLProvider) -> None:
        assert provider.map_role(["unknown", "attorney_group"]) == "attorney"

    def test_no_matching_group_returns_default(self, provider: SAMLProvider) -> None:
        assert provider.map_role(["other_group"]) == "viewer"

    def test_empty_groups_returns_default(self, provider: SAMLProvider) -> None:
        assert provider.map_role([]) == "viewer"


# ---------------------------------------------------------------------------
# Unit tests: get_authn_request_url
# ---------------------------------------------------------------------------


class TestGetAuthnRequestUrl:
    """Test AuthnRequest URL generation."""

    def test_generates_url(self, provider: SAMLProvider) -> None:
        """get_authn_request_url returns a string URL starting with the IdP SSO URL."""
        with patch("app.auth.saml.OneLogin_Saml2_Auth") as mock_auth_cls:
            mock_auth = MagicMock()
            mock_auth.login.return_value = "https://idp.example.com/saml/sso?SAMLRequest=encoded"
            mock_auth_cls.return_value = mock_auth

            url = provider.get_authn_request_url()
            assert url.startswith("https://idp.example.com")
            mock_auth.login.assert_called_once_with(return_to=None)

    def test_generates_url_with_return_to(self, provider: SAMLProvider) -> None:
        """get_authn_request_url passes return_to parameter."""
        with patch("app.auth.saml.OneLogin_Saml2_Auth") as mock_auth_cls:
            mock_auth = MagicMock()
            mock_auth.login.return_value = "https://idp.example.com/saml/sso?SAMLRequest=encoded"
            mock_auth_cls.return_value = mock_auth

            provider.get_authn_request_url(return_to="/dashboard")
            mock_auth.login.assert_called_once_with(return_to="/dashboard")


# ---------------------------------------------------------------------------
# Unit tests: parse_acs_response
# ---------------------------------------------------------------------------


class TestParseAcsResponse:
    """Test SAML assertion parsing."""

    def test_valid_assertion(self, provider: SAMLProvider) -> None:
        """Valid assertion extracts user attributes."""
        with patch("app.auth.saml.OneLogin_Saml2_Auth") as mock_auth_cls:
            mock_auth = MagicMock()
            mock_auth.get_errors.return_value = []
            mock_auth.is_authenticated.return_value = True
            mock_auth.get_nameid.return_value = "saml-user@example.com"
            mock_auth.get_attributes.return_value = {
                "email": ["saml-user@example.com"],
                "displayName": ["SAML Test User"],
                "groups": ["admin_group"],
            }
            mock_auth_cls.return_value = mock_auth

            request_data = _build_request_data("https://nexus.example.com/saml")
            request_data["post_data"] = {"SAMLResponse": "base64encoded"}
            result = provider.parse_acs_response("base64encoded", request_data)

            assert result["email"] == "saml-user@example.com"
            assert result["name"] == "SAML Test User"
            assert result["groups"] == ["admin_group"]
            assert result["name_id"] == "saml-user@example.com"

    def test_invalid_assertion_raises(self, provider: SAMLProvider) -> None:
        """Invalid assertion raises ValueError."""
        with patch("app.auth.saml.OneLogin_Saml2_Auth") as mock_auth_cls:
            mock_auth = MagicMock()
            mock_auth.get_errors.return_value = ["invalid_response"]
            mock_auth.get_last_error_reason.return_value = "Signature validation failed"
            mock_auth_cls.return_value = mock_auth

            request_data = _build_request_data("https://nexus.example.com/saml")
            with pytest.raises(ValueError, match="SAML assertion invalid"):
                provider.parse_acs_response("bad-response", request_data)

    def test_unauthenticated_assertion_raises(self, provider: SAMLProvider) -> None:
        """Assertion where user is not authenticated raises ValueError."""
        with patch("app.auth.saml.OneLogin_Saml2_Auth") as mock_auth_cls:
            mock_auth = MagicMock()
            mock_auth.get_errors.return_value = []
            mock_auth.is_authenticated.return_value = False
            mock_auth_cls.return_value = mock_auth

            request_data = _build_request_data("https://nexus.example.com/saml")
            with pytest.raises(ValueError, match="user not authenticated"):
                provider.parse_acs_response("response", request_data)

    def test_fallback_email_from_nameid(self, provider: SAMLProvider) -> None:
        """Falls back to NameID when email attribute is missing."""
        with patch("app.auth.saml.OneLogin_Saml2_Auth") as mock_auth_cls:
            mock_auth = MagicMock()
            mock_auth.get_errors.return_value = []
            mock_auth.is_authenticated.return_value = True
            mock_auth.get_nameid.return_value = "fallback@example.com"
            mock_auth.get_attributes.return_value = {}
            mock_auth_cls.return_value = mock_auth

            request_data = _build_request_data("https://nexus.example.com/saml")
            result = provider.parse_acs_response("response", request_data)
            assert result["email"] == "fallback@example.com"


# ---------------------------------------------------------------------------
# Unit tests: get_or_create_user
# ---------------------------------------------------------------------------


class TestGetOrCreateUser:
    """Test JIT user provisioning."""

    @pytest.mark.asyncio
    async def test_creates_new_user(self, provider: SAMLProvider) -> None:
        """First SAML login creates a new user."""
        mock_db = AsyncMock()
        mock_result_sso = MagicMock()
        mock_result_sso.first.return_value = None
        mock_result_email = MagicMock()
        mock_result_email.first.return_value = None

        mock_db.execute = AsyncMock(side_effect=[mock_result_sso, mock_result_email, MagicMock()])

        user, is_new = await provider.get_or_create_user(mock_db, _SAML_ATTRIBUTES)

        assert is_new is True
        assert user.email == "saml@example.com"
        assert user.full_name == "SAML User"
        assert user.role == "admin"  # admin_group maps to admin
        assert user.password_hash == ""
        assert mock_db.flush.await_count == 1

    @pytest.mark.asyncio
    async def test_finds_existing_sso_user(self, provider: SAMLProvider) -> None:
        """Returning SAML user is found by subject ID."""
        mock_db = AsyncMock()
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": _SAML_USER.id,
            "email": _SAML_USER.email,
            "password_hash": "",
            "full_name": _SAML_USER.full_name,
            "role": _SAML_USER.role,
            "api_key_hash": None,
            "is_active": True,
            "created_at": _SAML_USER.created_at,
            "updated_at": _SAML_USER.updated_at,
        }
        mock_result = MagicMock()
        mock_result.first.return_value = mock_row

        mock_db.execute = AsyncMock(return_value=mock_result)

        user, is_new = await provider.get_or_create_user(mock_db, _SAML_ATTRIBUTES)

        assert is_new is False
        assert user.id == _SAML_USER.id

    @pytest.mark.asyncio
    async def test_links_existing_email_account(self, provider: SAMLProvider) -> None:
        """Existing user with matching email gets SAML linked."""
        mock_db = AsyncMock()
        mock_result_sso = MagicMock()
        mock_result_sso.first.return_value = None
        mock_result_email = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": _SAML_USER.id,
            "email": _SAML_USER.email,
            "password_hash": "$2b$12$existing",
            "full_name": _SAML_USER.full_name,
            "role": _SAML_USER.role,
            "api_key_hash": None,
            "is_active": True,
            "created_at": _SAML_USER.created_at,
            "updated_at": _SAML_USER.updated_at,
        }
        mock_result_email.first.return_value = mock_row

        mock_db.execute = AsyncMock(side_effect=[mock_result_sso, mock_result_email, MagicMock()])

        user, is_new = await provider.get_or_create_user(mock_db, _SAML_ATTRIBUTES)

        assert is_new is False
        assert user.id == _SAML_USER.id
        assert mock_db.flush.await_count == 1


# ---------------------------------------------------------------------------
# Unit tests: get_sp_metadata
# ---------------------------------------------------------------------------


class TestGetSpMetadata:
    """Test SP metadata generation."""

    def test_returns_xml_string(self, provider: SAMLProvider) -> None:
        """get_sp_metadata returns valid XML string."""
        with patch("app.auth.saml.OneLogin_Saml2_Settings") as mock_settings_cls:
            mock_settings = MagicMock()
            mock_settings.get_sp_metadata.return_value = b'<?xml version="1.0"?><md:EntityDescriptor/>'
            mock_settings.validate_metadata.return_value = []
            mock_settings_cls.return_value = mock_settings

            metadata = provider.get_sp_metadata()
            assert metadata.startswith("<?xml")
            mock_settings_cls.assert_called_once()

    def test_raises_on_invalid_metadata(self, provider: SAMLProvider) -> None:
        """get_sp_metadata raises ValueError on invalid metadata."""
        with patch("app.auth.saml.OneLogin_Saml2_Settings") as mock_settings_cls:
            mock_settings = MagicMock()
            mock_settings.get_sp_metadata.return_value = b"<invalid/>"
            mock_settings.validate_metadata.return_value = ["missing_entityid"]
            mock_settings_cls.return_value = mock_settings

            with pytest.raises(ValueError, match="SP metadata invalid"):
                provider.get_sp_metadata()


# ---------------------------------------------------------------------------
# Unit tests: _build_request_data
# ---------------------------------------------------------------------------


class TestBuildRequestData:
    """Test request data builder."""

    def test_https_url(self) -> None:
        data = _build_request_data("https://nexus.example.com/saml")
        assert data["http_host"] == "nexus.example.com"
        assert data["https"] == "on"
        assert data["server_port"] == "443"

    def test_http_url(self) -> None:
        data = _build_request_data("http://localhost:8000/saml")
        assert data["http_host"] == "localhost"
        assert data["https"] == "off"
        assert data["server_port"] == "8000"

    def test_overrides(self) -> None:
        data = _build_request_data("https://nexus.example.com/saml", server_port="9999")
        assert data["server_port"] == "9999"
