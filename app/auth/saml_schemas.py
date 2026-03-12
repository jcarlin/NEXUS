"""SAML SSO Pydantic schemas: provider info and ACS callback response."""

from __future__ import annotations

from pydantic import BaseModel


class SAMLProviderInfo(BaseModel):
    """Returned by GET /auth/saml/info for frontend to show SAML SSO button."""

    enabled: bool
    provider_name: str
    login_url: str  # URL to GET /auth/saml/login (triggers redirect to IdP)


class SAMLCallbackResponse(BaseModel):
    """Returned after successful SAML ACS callback."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    is_new_user: bool
