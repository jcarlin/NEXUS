"""Pydantic schemas for runtime tuning settings management."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class SettingCategory(StrEnum):
    RETRIEVAL = "retrieval"
    ADAPTIVE_DEPTH = "adaptive_depth"
    QUERY = "query"
    AGENT = "agent"
    INGESTION = "ingestion"
    VISUAL = "visual"
    AUTH = "auth"


class SettingType(StrEnum):
    INT = "int"
    FLOAT = "float"
    STRING = "string"


class SettingRiskLevel(StrEnum):
    SAFE = "safe"
    CACHE_CLEAR = "cache_clear"
    RESTART = "restart"


class SettingDetail(BaseModel):
    setting_name: str
    display_name: str
    description: str
    category: SettingCategory
    setting_type: SettingType
    risk_level: SettingRiskLevel
    value: int | float | str
    env_default: int | float | str
    min_value: float | None = None
    max_value: float | None = None
    unit: str | None = None
    step: float | None = None
    is_override: bool
    updated_at: datetime | None = None
    updated_by: UUID | None = None
    requires_flag: str | None = None
    flag_enabled: bool | None = None


class SettingListResponse(BaseModel):
    items: list[SettingDetail]


class SettingUpdateRequest(BaseModel):
    value: int | float | str


class SettingUpdateResponse(SettingDetail):
    caches_cleared: list[str]
    restart_required: bool
