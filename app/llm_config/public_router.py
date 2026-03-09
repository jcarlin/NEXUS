"""Public (non-admin) endpoints for LLM configuration."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import get_current_user
from app.auth.schemas import UserRecord
from app.dependencies import get_db
from app.llm_config.schemas import ActiveModelResponse, LLMTier
from app.llm_config.service import LLMConfigService

router = APIRouter(prefix="/llm-config", tags=["llm-config"])


@router.get("/active-model", response_model=ActiveModelResponse)
async def get_active_model(
    db: AsyncSession = Depends(get_db),
    _user: UserRecord = Depends(get_current_user),
) -> ActiveModelResponse:
    """Return the model name configured for the query tier."""
    tiers = await LLMConfigService.list_tier_configs(db)
    for t in tiers:
        if t.tier == LLMTier.QUERY:
            return ActiveModelResponse(
                tier=LLMTier.QUERY,
                model=t.model or "unknown",
                provider_type=t.provider_type,
            )
    return ActiveModelResponse(tier=LLMTier.QUERY, model="unknown")
