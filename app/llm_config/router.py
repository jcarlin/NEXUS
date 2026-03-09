"""Admin-only endpoints for runtime LLM configuration."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import require_role
from app.auth.schemas import UserRecord
from app.dependencies import get_db
from app.llm_config.schemas import (
    CostEstimateResponse,
    LLMConfigOverview,
    LLMProviderCreate,
    LLMProviderResponse,
    LLMProviderUpdate,
    LLMTier,
    LLMTierConfigResponse,
    LLMTierConfigSet,
    OllamaModelListResponse,
    TestConnectionResponse,
)
from app.llm_config.service import LLMConfigService

router = APIRouter(prefix="/admin/llm-config", tags=["admin", "llm-config"])


@router.get("", response_model=LLMConfigOverview)
async def get_overview(
    db: AsyncSession = Depends(get_db),
    _current_user: UserRecord = Depends(require_role("admin")),
) -> LLMConfigOverview:
    """Get full LLM configuration overview: providers + tiers + env defaults."""
    return await LLMConfigService.get_overview(db)


# ------------------------------------------------------------------
# Providers
# ------------------------------------------------------------------


@router.post("/providers", response_model=LLMProviderResponse, status_code=201)
async def create_provider(
    data: LLMProviderCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: UserRecord = Depends(require_role("admin")),
) -> LLMProviderResponse:
    """Add an LLM provider with credentials."""
    return await LLMConfigService.create_provider(db, data)


@router.patch("/providers/{provider_id}", response_model=LLMProviderResponse)
async def update_provider(
    provider_id: UUID,
    data: LLMProviderUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: UserRecord = Depends(require_role("admin")),
) -> LLMProviderResponse:
    """Update an existing provider."""
    result = await LLMConfigService.update_provider(db, provider_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Provider not found")
    return result


@router.delete("/providers/{provider_id}", status_code=204)
async def deactivate_provider(
    provider_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: UserRecord = Depends(require_role("admin")),
):
    """Deactivate a provider (soft delete)."""
    if not await LLMConfigService.deactivate_provider(db, provider_id):
        raise HTTPException(status_code=404, detail="Provider not found")


@router.post("/providers/{provider_id}/test", response_model=TestConnectionResponse)
async def test_connection(
    provider_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: UserRecord = Depends(require_role("admin")),
) -> TestConnectionResponse:
    """Test connectivity by making a trivial LLM call."""
    return await LLMConfigService.test_connection(db, provider_id)


# ------------------------------------------------------------------
# Tiers
# ------------------------------------------------------------------


@router.put("/tiers/{tier}", response_model=LLMTierConfigResponse)
async def set_tier_config(
    tier: LLMTier,
    data: LLMTierConfigSet,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(require_role("admin")),
) -> LLMTierConfigResponse:
    """Set provider + model for a tier."""
    try:
        return await LLMConfigService.set_tier_config(db, tier, data, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/tiers/{tier}", status_code=204)
async def delete_tier_config(
    tier: LLMTier,
    db: AsyncSession = Depends(get_db),
    _current_user: UserRecord = Depends(require_role("admin")),
):
    """Remove tier override (falls back to env-var default)."""
    await LLMConfigService.delete_tier_config(db, tier)


# ------------------------------------------------------------------
# Ollama
# ------------------------------------------------------------------


@router.get("/ollama/models", response_model=OllamaModelListResponse)
async def discover_ollama_models(
    base_url: str = Query("", description="Override Ollama base URL"),
    _current_user: UserRecord = Depends(require_role("admin")),
) -> OllamaModelListResponse:
    """Discover models from local Ollama API."""
    models = await LLMConfigService.discover_ollama_models(base_url)
    return OllamaModelListResponse(items=models)


# ------------------------------------------------------------------
# Cost estimation
# ------------------------------------------------------------------


@router.get("/cost-estimate", response_model=CostEstimateResponse)
async def get_cost_estimate(
    period_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _current_user: UserRecord = Depends(require_role("admin")),
) -> CostEstimateResponse:
    """Estimate costs per tier based on ai_audit_log token usage."""
    return await LLMConfigService.estimate_costs(db, period_days)


# ------------------------------------------------------------------
# Apply
# ------------------------------------------------------------------


@router.post("/apply", status_code=204)
async def apply_config(
    _current_user: UserRecord = Depends(require_role("admin")),
):
    """Clear LLM client caches to force rebuild with new config.

    This clears the resolver cache and the DI singletons for the LLM
    client and query graph, so the next request picks up the new config.
    """
    from app.llm_config.resolver import clear_cache

    clear_cache()

    # Clear the cached LLM singleton and query graph so they rebuild
    from app.dependencies import get_llm, get_query_graph

    get_llm.cache_clear()
    get_query_graph.cache_clear()
