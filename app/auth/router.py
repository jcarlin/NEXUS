"""Auth API endpoints: login, refresh, current user profile.

POST /auth/login    -- JWT token issuance
POST /auth/refresh  -- Token refresh
GET  /auth/me       -- Current user profile (requires auth)
"""

from __future__ import annotations

from uuid import UUID

import jwt
import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import get_current_user
from app.auth.schemas import (
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserResponse,
)
from app.auth.service import AuthService
from app.dependencies import get_db, get_settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with email/password and receive JWT tokens."""
    settings = get_settings()

    user = await AuthService.authenticate_user(db, body.email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = AuthService.create_access_token(user["id"], user["role"], settings)
    refresh_token = AuthService.create_refresh_token(user["id"], settings)

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
    if user is None or not user.get("is_active", False):
        raise HTTPException(status_code=401, detail="User not found or inactive")

    access_token = AuthService.create_access_token(user["id"], user["role"], settings)
    refresh_token = AuthService.create_refresh_token(user["id"], settings)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserResponse)
async def me(
    current_user: dict = Depends(get_current_user),
):
    """Return the profile of the currently authenticated user."""
    return UserResponse(
        id=current_user["id"],
        email=current_user["email"],
        full_name=current_user["full_name"],
        role=current_user["role"],
        is_active=current_user["is_active"],
        created_at=current_user["created_at"],
    )
