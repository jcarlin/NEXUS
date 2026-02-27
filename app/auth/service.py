"""Auth service layer — user CRUD, password hashing, JWT management, matter access.

All DB queries use raw ``sqlalchemy.text()`` with named parameters.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
import structlog
from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings

logger = structlog.get_logger(__name__)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Static-style methods for auth operations."""

    # ------------------------------------------------------------------
    # Password hashing
    # ------------------------------------------------------------------

    @staticmethod
    def hash_password(password: str) -> str:
        return _pwd_context.hash(password)

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        return _pwd_context.verify(plain, hashed)

    @staticmethod
    def hash_api_key(api_key: str) -> str:
        return hashlib.sha256(api_key.encode()).hexdigest()

    # ------------------------------------------------------------------
    # User CRUD
    # ------------------------------------------------------------------

    @staticmethod
    async def create_user(
        db: AsyncSession,
        email: str,
        password: str,
        full_name: str,
        role: str = "reviewer",
    ) -> dict[str, Any]:
        user_id = uuid4()
        now = datetime.now(UTC)
        password_hash = AuthService.hash_password(password)

        await db.execute(
            text("""
                INSERT INTO users (id, email, password_hash, full_name, role, created_at, updated_at)
                VALUES (:id, :email, :password_hash, :full_name, :role, :created_at, :updated_at)
            """),
            {
                "id": user_id,
                "email": email,
                "password_hash": password_hash,
                "full_name": full_name,
                "role": role,
                "created_at": now,
                "updated_at": now,
            },
        )
        await db.flush()

        logger.info("auth.user_created", user_id=str(user_id), email=email)
        return {
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "role": role,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }

    @staticmethod
    async def authenticate_user(
        db: AsyncSession,
        email: str,
        password: str,
    ) -> dict[str, Any] | None:
        user = await AuthService.get_user_by_email(db, email)
        if user is None:
            return None
        if not user.get("is_active", False):
            return None
        if not AuthService.verify_password(password, user["password_hash"]):
            return None
        return user

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: UUID) -> dict[str, Any] | None:
        result = await db.execute(
            text("""
                SELECT id, email, password_hash, full_name, role, api_key_hash,
                       is_active, created_at, updated_at
                FROM users WHERE id = :user_id
            """),
            {"user_id": user_id},
        )
        row = result.first()
        if row is None:
            return None
        return dict(row._mapping)

    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> dict[str, Any] | None:
        result = await db.execute(
            text("""
                SELECT id, email, password_hash, full_name, role, api_key_hash,
                       is_active, created_at, updated_at
                FROM users WHERE email = :email
            """),
            {"email": email},
        )
        row = result.first()
        if row is None:
            return None
        return dict(row._mapping)

    @staticmethod
    async def get_user_by_api_key(db: AsyncSession, api_key: str) -> dict[str, Any] | None:
        key_hash = AuthService.hash_api_key(api_key)
        result = await db.execute(
            text("""
                SELECT id, email, password_hash, full_name, role, api_key_hash,
                       is_active, created_at, updated_at
                FROM users WHERE api_key_hash = :key_hash AND is_active = true
            """),
            {"key_hash": key_hash},
        )
        row = result.first()
        if row is None:
            return None
        return dict(row._mapping)

    # ------------------------------------------------------------------
    # JWT tokens
    # ------------------------------------------------------------------

    @staticmethod
    def create_access_token(user_id: UUID, role: str, settings: Settings) -> str:
        expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
        payload = {
            "sub": str(user_id),
            "role": role,
            "type": "access",
            "exp": expire,
        }
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    @staticmethod
    def create_refresh_token(user_id: UUID, settings: Settings) -> str:
        expire = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days)
        payload = {
            "sub": str(user_id),
            "type": "refresh",
            "exp": expire,
        }
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    @staticmethod
    def decode_token(token: str, settings: Settings) -> dict[str, Any]:
        """Decode and validate a JWT. Raises jwt.PyJWTError on failure."""
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])

    # ------------------------------------------------------------------
    # Matter access
    # ------------------------------------------------------------------

    @staticmethod
    async def get_user_matters(db: AsyncSession, user_id: UUID) -> list[UUID]:
        result = await db.execute(
            text("SELECT matter_id FROM user_case_matters WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        return [row.matter_id for row in result.all()]

    @staticmethod
    async def check_user_matter_access(
        db: AsyncSession,
        user_id: UUID,
        matter_id: UUID,
        role: str,
    ) -> bool:
        """Check if a user has access to a matter. Admins always pass."""
        if role == "admin":
            return True

        result = await db.execute(
            text("""
                SELECT 1 FROM user_case_matters
                WHERE user_id = :user_id AND matter_id = :matter_id
            """),
            {"user_id": user_id, "matter_id": matter_id},
        )
        return result.first() is not None

    @staticmethod
    async def matter_exists(db: AsyncSession, matter_id: UUID) -> bool:
        result = await db.execute(
            text("SELECT 1 FROM case_matters WHERE id = :matter_id AND is_active = true"),
            {"matter_id": matter_id},
        )
        return result.first() is not None
