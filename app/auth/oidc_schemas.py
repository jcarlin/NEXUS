"""OIDC SSO Pydantic schemas: provider info and callback response."""

from __future__ import annotations

from pydantic import BaseModel


class OIDCProviderInfo(BaseModel):
    """Returned by GET /auth/oidc/info for frontend to show SSO button."""

    enabled: bool
    provider_name: str
    authorize_url: str  # Full URL to redirect to


class OIDCCallbackResponse(BaseModel):
    """Returned after successful OIDC callback."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    is_new_user: bool
