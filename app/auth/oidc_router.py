"""OIDC SSO endpoints.

GET  /auth/oidc/info       -- Provider info for frontend SSO button
GET  /auth/oidc/callback   -- Handle OIDC callback after provider authentication
"""

from __future__ import annotations

from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.oidc_schemas import OIDCCallbackResponse, OIDCProviderInfo
from app.auth.service import AuthService
from app.dependencies import get_db, get_oidc_provider, get_settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth/oidc", tags=["auth"])


@router.get("/info", response_model=OIDCProviderInfo)
async def oidc_info() -> OIDCProviderInfo:
    """Return OIDC provider info for frontend SSO button."""
    settings = get_settings()
    if not settings.enable_sso:
        return OIDCProviderInfo(enabled=False, provider_name="", authorize_url="")

    provider = get_oidc_provider()
    state = str(uuid4())
    authorize_url = await provider.get_authorize_url(state)
    return OIDCProviderInfo(
        enabled=True,
        provider_name=provider.provider_name,
        authorize_url=authorize_url,
    )


@router.get("/callback", response_model=OIDCCallbackResponse)
async def oidc_callback(
    code: str = Query(...),
    state: str = Query(""),
    db: AsyncSession = Depends(get_db),
) -> OIDCCallbackResponse:
    """Handle OIDC callback after provider authentication."""
    settings = get_settings()
    if not settings.enable_sso:
        raise HTTPException(status_code=404, detail="SSO is not enabled")

    provider = get_oidc_provider()

    try:
        userinfo = await provider.exchange_code(code)
    except Exception as exc:
        logger.error("oidc.token_exchange_failed", error=str(exc))
        raise HTTPException(status_code=401, detail="OIDC authentication failed")

    if not userinfo.get("email"):
        raise HTTPException(status_code=401, detail="OIDC provider did not return email")

    user, is_new = await provider.get_or_create_user(db, userinfo)
    await db.commit()

    access_token = AuthService.create_access_token(user.id, user.role, settings)
    refresh_token = AuthService.create_refresh_token(user.id, settings)

    return OIDCCallbackResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        is_new_user=is_new,
    )
