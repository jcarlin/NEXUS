"""Admin-only endpoints for runtime feature flag management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import require_role
from app.auth.schemas import UserRecord
from app.dependencies import get_db
from app.feature_flags.schemas import (
    FeatureFlagListResponse,
    FeatureFlagUpdateRequest,
    FeatureFlagUpdateResponse,
)
from app.feature_flags.service import FeatureFlagService

router = APIRouter(prefix="/admin/feature-flags", tags=["admin", "feature-flags"])


@router.get("", response_model=FeatureFlagListResponse)
async def list_flags(
    db: AsyncSession = Depends(get_db),
    _current_user: UserRecord = Depends(require_role("admin")),
) -> FeatureFlagListResponse:
    """List all feature flags with current state and metadata."""
    items = await FeatureFlagService.list_flags(db)
    return FeatureFlagListResponse(items=items)


@router.put("/{flag_name}", response_model=FeatureFlagUpdateResponse)
async def update_flag(
    flag_name: str,
    data: FeatureFlagUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin")),
) -> FeatureFlagUpdateResponse:
    """Toggle a feature flag. Takes effect immediately for safe/cache_clear flags."""
    try:
        return await FeatureFlagService.update_flag(db, flag_name, data.enabled, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{flag_name}", status_code=204)
async def reset_flag(
    flag_name: str,
    db: AsyncSession = Depends(get_db),
    _current_user: UserRecord = Depends(require_role("admin")),
) -> None:
    """Reset a flag to its env default by removing the DB override."""
    try:
        await FeatureFlagService.reset_flag(db, flag_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
