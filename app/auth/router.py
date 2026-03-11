"""Auth API endpoints: login, refresh, current user profile, user matters.

POST /auth/login        -- JWT token issuance
POST /auth/refresh      -- Token refresh
GET  /auth/me           -- Current user profile (requires auth)
GET  /auth/me/matters   -- Matters accessible to the current user
"""

from __future__ import annotations

from uuid import UUID

import jwt
import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import get_current_user
from app.auth.schemas import (
    LoginRequest,
    MatterResponse,
    RefreshRequest,
    TokenResponse,
    UserRecord,
    UserResponse,
)
from app.auth.service import AuthService
from app.common.rate_limit import rate_limit_login
from app.dependencies import get_db, get_settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
    _rate_limit=Depends(rate_limit_login),
):
    """Authenticate with email/password and receive JWT tokens."""
    settings = get_settings()

    user = await AuthService.authenticate_user(db, body.email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = AuthService.create_access_token(user.id, user.role, settings)
    refresh_token = AuthService.create_refresh_token(user.id, settings)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Exchange a valid refresh token for a new access + refresh token pair."""
    settings = get_settings()

    try:
        payload = AuthService.decode_token(body.refresh_token, settings)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token has expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user = await AuthService.get_user_by_id(db, UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    access_token = AuthService.create_access_token(user.id, user.role, settings)
    refresh_token = AuthService.create_refresh_token(user.id, settings)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserResponse)
async def me(
    current_user: UserRecord = Depends(get_current_user),
):
    """Return the profile of the currently authenticated user."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )


@router.get("/me/matters", response_model=list[MatterResponse])
async def my_matters(
    current_user: UserRecord = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the matters accessible to the current user.

    Admins see all active matters; other roles see only matters linked
    via the ``user_case_matters`` join table.
    """
    if current_user.role == "admin":
        result = await db.execute(
            text(
                "SELECT id, name, description, is_active, created_at FROM case_matters WHERE is_active = true ORDER BY name"
            )
        )
    else:
        result = await db.execute(
            text("""
                SELECT cm.id, cm.name, cm.description, cm.is_active, cm.created_at
                FROM case_matters cm
                JOIN user_case_matters ucm ON cm.id = ucm.matter_id
                WHERE ucm.user_id = :user_id AND cm.is_active = true
                ORDER BY cm.name
            """),
            {"user_id": current_user.id},
        )
    rows = result.all()
    return [MatterResponse.model_validate(dict(r._mapping)) for r in rows]
