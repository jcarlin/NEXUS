"""Pydantic v2 schemas for LLM runtime configuration."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class LLMProviderType(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"
    OLLAMA = "ollama"


class LLMTier(StrEnum):
    QUERY = "query"
    ANALYSIS = "analysis"
    INGESTION = "ingestion"


# --- Provider schemas ---


class LLMProviderCreate(BaseModel):
    provider: LLMProviderType
    label: str = Field(min_length=1, max_length=100)
    api_key: str = ""
    base_url: str = ""


class LLMProviderUpdate(BaseModel):
    label: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    is_active: bool | None = None


class LLMProviderResponse(BaseModel):
    id: UUID
    provider: LLMProviderType
    label: str
    api_key_set: bool  # Never expose actual key
    base_url: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LLMProviderListResponse(BaseModel):
    items: list[LLMProviderResponse]


# --- Tier config schemas ---


class LLMTierConfigSet(BaseModel):
    provider_id: UUID
    model: str = Field(min_length=1, max_length=100)


class LLMTierConfigResponse(BaseModel):
    tier: LLMTier
    provider_id: UUID | None = None
    provider_label: str | None = None
    provider_type: LLMProviderType | None = None
    model: str | None = None
    updated_at: datetime | None = None
    updated_by: UUID | None = None
    is_env_default: bool = True  # True when no DB override exists


class LLMTierConfigListResponse(BaseModel):
    items: list[LLMTierConfigResponse]


# --- Resolved config (internal, not API-facing) ---


class ResolvedLLMConfig(BaseModel):
    provider: str
    model: str
    api_key: str
    base_url: str


# --- Ollama models ---


class OllamaModel(BaseModel):
    name: str
    size: int | None = None
    modified_at: str | None = None


class OllamaModelListResponse(BaseModel):
    items: list[OllamaModel]


# --- Cost estimation ---


class TierCostEstimate(BaseModel):
    tier: LLMTier
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0


class CostEstimateResponse(BaseModel):
    period_days: int
    tiers: list[TierCostEstimate]
    total_cost_usd: float = 0.0


# --- Overview ---


class LLMConfigOverview(BaseModel):
    providers: list[LLMProviderResponse]
    tiers: list[LLMTierConfigResponse]
    env_defaults: dict[str, str]  # tier -> "provider/model" from env


# --- Test connection ---


class TestConnectionResponse(BaseModel):
    success: bool
    latency_ms: int | None = None
    error: str | None = None


# --- Model discovery ---


class AvailableModel(BaseModel):
    id: str
    display_name: str
    context_window: int | None = None


class AvailableModelListResponse(BaseModel):
    items: list[AvailableModel]
    provider_type: LLMProviderType


# --- Active model (public) ---


class ActiveModelResponse(BaseModel):
    tier: LLMTier
    model: str
    provider_type: LLMProviderType | None = None
