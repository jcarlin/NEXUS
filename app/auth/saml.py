"""SAML 2.0 provider integration using python3-saml."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import structlog
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.settings import OneLogin_Saml2_Settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import UserRecord
from app.auth.service import AuthService
from app.config import Settings

logger = structlog.get_logger(__name__)


class SAMLProvider:
    """Handles SAML 2.0 authentication flow."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.entity_id = settings.saml_entity_id
        self.idp_sso_url = settings.saml_idp_sso_url
        self.idp_cert = settings.saml_idp_cert
        self.sp_cert = settings.saml_sp_cert
        self.sp_key = settings.saml_sp_key
        self._role_mapping: dict[str, str] = {}
        if settings.saml_role_mapping:
            try:
                self._role_mapping = json.loads(settings.saml_role_mapping)
            except json.JSONDecodeError:
                logger.warning("saml.invalid_role_mapping")
        self.default_role = settings.saml_default_role

    def _get_saml_settings(self) -> dict:
        """Build python3-saml settings dict from config."""
        settings: dict = {
            "strict": True,
            "debug": False,
            "sp": {
                "entityId": self.entity_id,
                "assertionConsumerService": {
                    "url": f"{self.entity_id}/auth/saml/acs",
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
                },
                "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
            },
            "idp": {
                "entityId": self.idp_sso_url,
                "singleSignOnService": {
                    "url": self.idp_sso_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "x509cert": self.idp_cert,
            },
            "security": {
                "authnRequestsSigned": bool(self.sp_cert and self.sp_key),
                "wantAssertionsSigned": True,
                "wantNameId": True,
            },
        }
        if self.sp_cert and self.sp_key:
            settings["sp"]["x509cert"] = self.sp_cert
            settings["sp"]["privateKey"] = self.sp_key
        return settings

    def get_authn_request_url(self, return_to: str | None = None) -> str:
        """Generate SAML AuthnRequest redirect URL.

        Uses python3-saml to build a properly signed AuthnRequest and
        returns the full IdP redirect URL.
        """
        request_data = _build_request_data(self.entity_id)
        auth = OneLogin_Saml2_Auth(request_data, self._get_saml_settings())
        return auth.login(return_to=return_to)

    def parse_acs_response(self, saml_response: str, request_data: dict) -> dict:
        """Validate SAML assertion and extract user attributes.

        Args:
            saml_response: Base64-encoded SAMLResponse from IdP POST.
            request_data: python3-saml request dict (http_host, script_name, etc.).

        Returns:
            Dict with keys: email, name, groups, name_id.

        Raises:
            ValueError: If the assertion is invalid or expired.
        """
        auth = OneLogin_Saml2_Auth(request_data, self._get_saml_settings())
        auth.process_response()

        errors = auth.get_errors()
        if errors:
            error_reason = auth.get_last_error_reason()
            logger.error("saml.acs_validation_failed", errors=errors, reason=error_reason)
            raise ValueError(f"SAML assertion invalid: {', '.join(errors)}")

        if not auth.is_authenticated():
            raise ValueError("SAML assertion: user not authenticated")

        attributes = auth.get_attributes()
        name_id = auth.get_nameid()

        email = (
            attributes.get("email", [None])[0]
            or attributes.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress", [None])[0]
            or name_id
        )
        name = (
            attributes.get("displayName", [None])[0]
            or attributes.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name", [None])[0]
            or (email.split("@")[0] if email else "")
        )
        groups: list[str] = (
            attributes.get("groups", [])
            or attributes.get("http://schemas.xmlsoap.org/claims/Group", [])
            or attributes.get("memberOf", [])
        )

        return {
            "email": email,
            "name": name,
            "groups": groups,
            "name_id": name_id,
        }

    def map_role(self, groups: list[str]) -> str:
        """Map SAML group claims to NEXUS role."""
        for group in groups:
            if group in self._role_mapping:
                return self._role_mapping[group]
        return self.default_role

    async def get_or_create_user(self, db: AsyncSession, attributes: dict) -> tuple[UserRecord, bool]:
        """JIT provision: find existing SSO user or create new one.

        Returns (user, is_new_user).
        """
        email = attributes.get("email", "")
        name_id = attributes.get("name_id", "")
        name = attributes.get("name", email.split("@")[0])
        groups: list[str] = attributes.get("groups", [])

        # First try to find by sso_subject_id
        result = await db.execute(
            text("""
                SELECT id, email, password_hash, full_name, role, api_key_hash,
                       is_active, created_at, updated_at
                FROM users WHERE sso_subject_id = :sub AND sso_provider = :provider
            """),
            {"sub": name_id, "provider": "saml"},
        )
        row = result.first()
        if row is not None:
            user = UserRecord.model_validate(dict(row._mapping))
            logger.info("saml.user_found", user_id=str(user.id), email=email)
            return user, False

        # Try by email (link existing account)
        existing = await AuthService.get_user_by_email(db, email)
        if existing is not None:
            await db.execute(
                text("""
                    UPDATE users SET sso_provider = :provider, sso_subject_id = :sub, updated_at = NOW()
                    WHERE id = :user_id
                """),
                {"provider": "saml", "sub": name_id, "user_id": existing.id},
            )
            await db.flush()
            logger.info("saml.account_linked", user_id=str(existing.id), email=email)
            return existing, False

        # Create new user (JIT provisioning)
        role = self.map_role(groups)
        user_id = uuid4()
        now = datetime.now(UTC)
        await db.execute(
            text("""
                INSERT INTO users (id, email, password_hash, full_name, role,
                                   sso_provider, sso_subject_id, created_at, updated_at)
                VALUES (:id, :email, :password_hash, :full_name, :role,
                        :sso_provider, :sso_subject_id, :created_at, :updated_at)
            """),
            {
                "id": user_id,
                "email": email,
                "password_hash": "",
                "full_name": name,
                "role": role,
                "sso_provider": "saml",
                "sso_subject_id": name_id,
                "created_at": now,
                "updated_at": now,
            },
        )
        await db.flush()

        user = UserRecord(
            id=user_id,
            email=email,
            password_hash="",
            full_name=name,
            role=role,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        logger.info("saml.user_created", user_id=str(user_id), email=email, role=role)
        return user, True

    def get_sp_metadata(self) -> str:
        """Generate SP metadata XML for IdP configuration."""
        saml_settings = OneLogin_Saml2_Settings(
            settings=self._get_saml_settings(),
            sp_validation_only=True,
        )
        metadata = saml_settings.get_sp_metadata()
        errors = saml_settings.validate_metadata(metadata)
        if errors:
            logger.error("saml.metadata_validation_failed", errors=errors)
            raise ValueError(f"SP metadata invalid: {', '.join(errors)}")
        return metadata.decode("utf-8") if isinstance(metadata, bytes) else metadata


def _build_request_data(entity_id: str, **overrides: str) -> dict:
    """Build the python3-saml request dict from an entity ID URL.

    python3-saml expects a dict with http_host, script_name, etc.
    """
    from urllib.parse import urlparse

    parsed = urlparse(entity_id)
    data: dict = {
        "http_host": parsed.hostname or "localhost",
        "script_name": parsed.path or "/",
        "get_data": {},
        "post_data": {},
        "https": "on" if parsed.scheme == "https" else "off",
    }
    if parsed.port:
        server_port = str(parsed.port)
    elif parsed.scheme == "https":
        server_port = "443"
    else:
        server_port = "80"
    data["server_port"] = server_port
    data.update(overrides)
    return data
