"""Resolve LLM configuration for a given tier.

Checks DB for tier overrides, falls back to env-var Settings.
Includes a 30-second TTL in-memory cache to avoid DB round-trips on every LLM call.
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm_config.schemas import LLMTier, ResolvedLLMConfig

logger = structlog.get_logger(__name__)

# In-memory cache: tier -> (ResolvedLLMConfig, timestamp)
_cache: dict[str, tuple[ResolvedLLMConfig, float]] = {}
_CACHE_TTL = 30.0  # seconds


def clear_cache() -> None:
    """Clear the resolver cache (called by /apply endpoint)."""
    _cache.clear()
    logger.info("llm_config.resolver.cache_cleared")


async def resolve_llm_config(
    tier: LLMTier | str,
    db: AsyncSession,
) -> ResolvedLLMConfig:
    """Resolve LLM provider+model+key for a given tier.

    1. Check 30s TTL in-memory cache
    2. Query DB: llm_tier_config JOIN llm_providers
    3. If found + active -> return DB config
    4. If not found -> fall back to env-var Settings
    """
    tier_str = tier.value if isinstance(tier, LLMTier) else tier

    # Check cache
    if tier_str in _cache:
        config, ts = _cache[tier_str]
        if time.monotonic() - ts < _CACHE_TTL:
            return config

    # Query DB
    result = await db.execute(
        text("""
            SELECT p.provider, t.model, p.api_key, p.base_url
            FROM llm_tier_config t
            JOIN llm_providers p ON p.id = t.provider_id
            WHERE t.tier = :tier AND p.is_active = true
        """),
        {"tier": tier_str},
    )
    row = result.mappings().first()

    if row:
        config = ResolvedLLMConfig(
            provider=row["provider"],
            model=row["model"],
            api_key=row["api_key"],
            base_url=row["base_url"],
        )
    else:
        # Fall back to env vars
        config = _resolve_from_env(tier_str)

    _cache[tier_str] = (config, time.monotonic())
    return config


def _resolve_from_env(tier: str) -> ResolvedLLMConfig:
    """Build ResolvedLLMConfig from environment variable settings."""
    from app.dependencies import get_settings

    settings = get_settings()

    model = settings.llm_model
    if tier == "query" and settings.query_llm_model:
        model = settings.query_llm_model

    api_key = ""
    base_url = ""
    if settings.llm_provider == "anthropic":
        api_key = settings.anthropic_api_key
    elif settings.llm_provider == "openai":
        api_key = settings.openai_api_key
    elif settings.llm_provider == "gemini":
        api_key = settings.gemini_api_key
    elif settings.llm_provider == "ollama":
        base_url = settings.ollama_base_url
    elif settings.llm_provider == "vllm":
        base_url = settings.vllm_base_url

    return ResolvedLLMConfig(
        provider=settings.llm_provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )


def resolve_llm_config_sync(tier: str, engine: Any) -> ResolvedLLMConfig:
    """Synchronous variant for Celery tasks.

    Uses a sync connection to query the DB for tier config.
    Falls back to env vars if no DB config exists.
    """
    # Check cache first (shared with async variant)
    if tier in _cache:
        config, ts = _cache[tier]
        if time.monotonic() - ts < _CACHE_TTL:
            return config

    from sqlalchemy import text as sa_text

    with engine.connect() as conn:
        row = (
            conn.execute(
                sa_text("""
                SELECT p.provider, t.model, p.api_key, p.base_url
                FROM llm_tier_config t
                JOIN llm_providers p ON p.id = t.provider_id
                WHERE t.tier = :tier AND p.is_active = true
            """),
                {"tier": tier},
            )
            .mappings()
            .first()
        )

    if row:
        config = ResolvedLLMConfig(
            provider=row["provider"],
            model=row["model"],
            api_key=row["api_key"],
            base_url=row["base_url"],
        )
    else:
        config = _resolve_from_env(tier)

    _cache[tier] = (config, time.monotonic())
    return config
