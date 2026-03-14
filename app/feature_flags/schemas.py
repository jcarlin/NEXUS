"""Pydantic schemas for feature flag management."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class FlagCategory(StrEnum):
    RETRIEVAL = "retrieval"
    INGESTION = "ingestion"
    QUERY = "query"
    ENTITY_GRAPH = "entity_graph"
    INTELLIGENCE = "intelligence"
    AUDIT = "audit"
    INTEGRATIONS = "integrations"


class FlagRiskLevel(StrEnum):
    SAFE = "safe"
    CACHE_CLEAR = "cache_clear"
    RESTART = "restart"


class FeatureFlagDetail(BaseModel):
    flag_name: str
    display_name: str
    description: str
    category: FlagCategory
    risk_level: FlagRiskLevel
    enabled: bool
    is_override: bool
    env_default: bool
    depends_on: list[str] = []
    updated_at: datetime | None = None
    updated_by: UUID | None = None


class FeatureFlagListResponse(BaseModel):
    items: list[FeatureFlagDetail]


class FeatureFlagUpdateRequest(BaseModel):
    enabled: bool


class FeatureFlagUpdateResponse(FeatureFlagDetail):
    caches_cleared: list[str]
    restart_required: bool
    cascaded: list[str] = []
