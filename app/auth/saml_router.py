"""SAML 2.0 SSO endpoints.

GET  /auth/saml/info         -- Provider info for frontend SSO button
GET  /auth/saml/login        -- 302 redirect to IdP SSO URL
POST /auth/saml/acs          -- Assertion Consumer Service (form POST from IdP)
GET  /auth/saml/metadata.xml -- SP metadata XML for IdP configuration
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.saml import _build_request_data
from app.auth.saml_schemas import SAMLCallbackResponse, SAMLProviderInfo
from app.auth.service import AuthService
from app.dependencies import get_db, get_saml_provider, get_settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth/saml", tags=["auth"])


@router.get("/info", response_model=SAMLProviderInfo)
async def saml_info() -> SAMLProviderInfo:
    """Return SAML provider info for frontend SSO button."""
    settings = get_settings()
    if not settings.enable_saml:
        return SAMLProviderInfo(enabled=False, provider_name="", login_url="")

    return SAMLProviderInfo(
        enabled=True,
        provider_name="SAML SSO",
        login_url="/api/v1/auth/saml/login",
    )


@router.get("/login")
async def saml_login() -> RedirectResponse:
    """Redirect to IdP SSO URL with SAML AuthnRequest."""
    settings = get_settings()
    if not settings.enable_saml:
        raise HTTPException(status_code=404, detail="SAML SSO is not enabled")

    provider = get_saml_provider()
    redirect_url = provider.get_authn_request_url()
    return RedirectResponse(url=redirect_url, status_code=302)


@router.post("/acs", response_model=SAMLCallbackResponse)
async def saml_acs(
    request: Request,
    db: AsyncSession = Depends(get_db),
    saml_response: str = Form(alias="SAMLResponse"),
    relay_state: str = Form("", alias="RelayState"),
) -> SAMLCallbackResponse:
    """Assertion Consumer Service — processes SAML response from IdP.

    The IdP sends a form POST with SAMLResponse (base64-encoded XML assertion)
    and optionally RelayState.
    """
    settings = get_settings()
    if not settings.enable_saml:
        raise HTTPException(status_code=404, detail="SAML SSO is not enabled")

    provider = get_saml_provider()

    # Build request_data for python3-saml from the incoming request
    request_data = _build_request_data(provider.entity_id)
    request_data["post_data"] = {"SAMLResponse": saml_response}
    if relay_state:
        request_data["post_data"]["RelayState"] = relay_state

    try:
        attributes = provider.parse_acs_response(saml_response, request_data)
    except ValueError as exc:
        logger.error("saml.acs_failed", error=str(exc))
        raise HTTPException(status_code=401, detail="SAML authentication failed")

    if not attributes.get("email"):
        raise HTTPException(status_code=401, detail="SAML assertion did not contain email")

    user, is_new = await provider.get_or_create_user(db, attributes)
    await db.commit()

    access_token = AuthService.create_access_token(user.id, user.role, settings)
    refresh_token = AuthService.create_refresh_token(user.id, settings)

    return SAMLCallbackResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        is_new_user=is_new,
    )


@router.get("/metadata.xml")
async def saml_metadata() -> Response:
    """Return SP metadata XML for IdP configuration."""
    settings = get_settings()
    if not settings.enable_saml:
        raise HTTPException(status_code=404, detail="SAML SSO is not enabled")

    provider = get_saml_provider()

    try:
        metadata_xml = provider.get_sp_metadata()
    except ValueError as exc:
        logger.error("saml.metadata_generation_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to generate SP metadata")

    return Response(content=metadata_xml, media_type="application/xml")
