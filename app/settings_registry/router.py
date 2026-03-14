"""Admin-only endpoints for runtime tuning settings management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import require_role
from app.auth.schemas import UserRecord
from app.dependencies import get_db
from app.settings_registry.schemas import (
    SettingListResponse,
    SettingUpdateRequest,
    SettingUpdateResponse,
)
from app.settings_registry.service import SettingsRegistryService

router = APIRouter(prefix="/admin/settings", tags=["admin", "settings"])


@router.get("", response_model=SettingListResponse)
async def list_settings(
    db: AsyncSession = Depends(get_db),
    _current_user: UserRecord = Depends(require_role("admin")),
) -> SettingListResponse:
    """List all tunable settings with current values and metadata."""
    items = await SettingsRegistryService.list_settings(db)
    return SettingListResponse(items=items)


@router.put("/{setting_name}", response_model=SettingUpdateResponse)
async def update_setting(
    setting_name: str,
    data: SettingUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin")),
) -> SettingUpdateResponse:
    """Update a tunable setting. Takes effect immediately for safe/cache_clear settings."""
    try:
        return await SettingsRegistryService.update_setting(db, setting_name, data.value, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{setting_name}", status_code=204)
async def reset_setting(
    setting_name: str,
    db: AsyncSession = Depends(get_db),
    _current_user: UserRecord = Depends(require_role("admin")),
) -> None:
    """Reset a setting to its env default by removing the DB override."""
    try:
        await SettingsRegistryService.reset_setting(db, setting_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
