"""OIDC provider integration using authlib."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import structlog
from authlib.integrations.httpx_client import AsyncOAuth2Client
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import UserRecord
from app.auth.service import AuthService
from app.config import Settings

logger = structlog.get_logger(__name__)


class OIDCProvider:
    """Handles OIDC authentication flow."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client_id = settings.oidc_client_id
        self.client_secret = settings.oidc_client_secret
        self.issuer_url = settings.oidc_issuer_url.rstrip("/")
        self.redirect_uri = settings.oidc_redirect_uri
        self.provider_name = settings.oidc_provider_name
        self._role_mapping: dict[str, str] = {}
        if settings.oidc_role_mapping:
            try:
                self._role_mapping = json.loads(settings.oidc_role_mapping)
            except json.JSONDecodeError:
                logger.warning("oidc.invalid_role_mapping")
        self.default_role = settings.oidc_default_role
        # OIDC well-known metadata (lazy-loaded)
        self._metadata: dict | None = None

    async def _get_metadata(self) -> dict:
        """Fetch OIDC discovery document (cached after first call)."""
        if self._metadata is None:
            url = f"{self.issuer_url}/.well-known/openid-configuration"
            async with AsyncOAuth2Client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
                self._metadata = resp.json()
        return self._metadata

    async def get_authorize_url(self, state: str) -> str:
        """Build the authorization URL for the OIDC provider."""
        metadata = await self._get_metadata()
        client = AsyncOAuth2Client(
            client_id=self.client_id,
            redirect_uri=self.redirect_uri,
            scope="openid email profile",
        )
        url, _ = client.create_authorization_url(
            metadata["authorization_endpoint"],
            state=state,
        )
        return url

    async def exchange_code(self, code: str) -> dict:
        """Exchange authorization code for tokens and return user info claims."""
        metadata = await self._get_metadata()
        async with AsyncOAuth2Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
        ) as client:
            await client.fetch_token(
                metadata["token_endpoint"],
                code=code,
            )
            # Get userinfo
            resp = await client.get(metadata["userinfo_endpoint"])
            resp.raise_for_status()
            return resp.json()

    def map_role(self, groups: list[str]) -> str:
        """Map OIDC group claims to NEXUS role."""
        for group in groups:
            if group in self._role_mapping:
                return self._role_mapping[group]
        return self.default_role

    async def get_or_create_user(self, db: AsyncSession, userinfo: dict) -> tuple[UserRecord, bool]:
        """JIT provision: find existing SSO user or create new one.

        Returns (user, is_new_user).
        """
        email = userinfo.get("email", "")
        sub = userinfo.get("sub", "")
        name = userinfo.get("name", email.split("@")[0])
        groups: list[str] = userinfo.get("groups", [])

        # First try to find by sso_subject_id
        result = await db.execute(
            text("""
                SELECT id, email, password_hash, full_name, role, api_key_hash,
                       is_active, created_at, updated_at
                FROM users WHERE sso_subject_id = :sub AND sso_provider = :provider
            """),
            {"sub": sub, "provider": self.provider_name},
        )
        row = result.first()
        if row is not None:
            user = UserRecord.model_validate(dict(row._mapping))
            logger.info("oidc.user_found", user_id=str(user.id), email=email)
            return user, False

        # Try by email (link existing account)
        existing = await AuthService.get_user_by_email(db, email)
        if existing is not None:
            # Link SSO to existing account
            await db.execute(
                text("""
                    UPDATE users SET sso_provider = :provider, sso_subject_id = :sub, updated_at = NOW()
                    WHERE id = :user_id
                """),
                {"provider": self.provider_name, "sub": sub, "user_id": existing.id},
            )
            await db.flush()
            logger.info("oidc.account_linked", user_id=str(existing.id), email=email)
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
                "password_hash": "",  # SSO users don't have passwords
                "full_name": name,
                "role": role,
                "sso_provider": self.provider_name,
                "sso_subject_id": sub,
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
        logger.info("oidc.user_created", user_id=str(user_id), email=email, role=role)
        return user, True
