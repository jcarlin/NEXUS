"""FastAPI auth dependencies: JWT/API-key authentication, role enforcement, matter scoping.

These are FastAPI ``Depends()`` callables, not ASGI middleware.  This
allows per-route opt-out (e.g. health endpoint needs no auth).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import jwt
import structlog
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import AuthService
from app.dependencies import get_db, get_settings

logger = structlog.get_logger(__name__)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Extract and validate user identity from Bearer token or API key.

    Sets ``request.state.user`` for downstream consumers.
    Raises 401 if no valid credentials are provided.
    """
    settings = get_settings()

    # Try Bearer token first
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = AuthService.decode_token(token, settings)
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Invalid token")

        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")

        user = await AuthService.get_user_by_id(db, UUID(payload["sub"]))
        if user is None or not user.get("is_active", False):
            raise HTTPException(status_code=401, detail="User not found or inactive")

        request.state.user = user
        return user

    # Fall back to API key
    api_key = request.headers.get("X-API-Key", "")
    if api_key:
        user = await AuthService.get_user_by_api_key(db, api_key)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid API key")

        request.state.user = user
        return user

    raise HTTPException(status_code=401, detail="Authentication required")


def require_role(*allowed_roles: str):
    """Return a dependency that checks the current user has one of the allowed roles."""

    async def _check_role(
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{current_user['role']}' is not authorized for this action",
            )
        return current_user

    return _check_role


async def get_matter_id(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UUID:
    """Read and validate X-Matter-ID header.

    - Validates the matter exists and is active.
    - Checks the user has access (admins bypass).
    - Returns the validated matter UUID.
    """
    matter_header = request.headers.get("X-Matter-ID", "")
    if not matter_header:
        raise HTTPException(status_code=400, detail="X-Matter-ID header is required")

    try:
        matter_id = UUID(matter_header)
    except ValueError:
        raise HTTPException(status_code=400, detail="X-Matter-ID must be a valid UUID")

    # Check matter exists
    exists = await AuthService.matter_exists(db, matter_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Matter not found")

    # Check user access
    has_access = await AuthService.check_user_matter_access(
        db, current_user["id"], matter_id, current_user["role"]
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="Not authorized for this matter")

    return matter_id
