"""LLM configuration service — CRUD for providers and tier configs."""

from __future__ import annotations

import time
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm_config.schemas import (
    AvailableModel,
    CostEstimateResponse,
    LLMConfigOverview,
    LLMProviderCreate,
    LLMProviderResponse,
    LLMProviderUpdate,
    LLMTier,
    LLMTierConfigResponse,
    LLMTierConfigSet,
    OllamaModel,
    TestConnectionResponse,
    TierCostEstimate,
)

logger = structlog.get_logger(__name__)


class LLMConfigService:
    """Static methods for LLM provider and tier configuration."""

    # ------------------------------------------------------------------
    # Providers CRUD
    # ------------------------------------------------------------------

    @staticmethod
    async def list_providers(db: AsyncSession) -> list[LLMProviderResponse]:
        result = await db.execute(
            text("""
                SELECT id, provider, label, api_key, base_url, is_active, created_at, updated_at
                FROM llm_providers
                ORDER BY created_at
            """)
        )
        rows = result.mappings().all()
        return [
            LLMProviderResponse(
                id=r["id"],
                provider=r["provider"],
                label=r["label"],
                api_key_set=bool(r["api_key"]),
                base_url=r["base_url"],
                is_active=r["is_active"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    @staticmethod
    async def create_provider(db: AsyncSession, data: LLMProviderCreate) -> LLMProviderResponse:
        result = await db.execute(
            text("""
                INSERT INTO llm_providers (provider, label, api_key, base_url)
                VALUES (:provider, :label, :api_key, :base_url)
                RETURNING id, provider, label, api_key, base_url, is_active, created_at, updated_at
            """),
            {
                "provider": data.provider.value,
                "label": data.label,
                "api_key": data.api_key,
                "base_url": data.base_url,
            },
        )
        r = result.mappings().one()
        return LLMProviderResponse(
            id=r["id"],
            provider=r["provider"],
            label=r["label"],
            api_key_set=bool(r["api_key"]),
            base_url=r["base_url"],
            is_active=r["is_active"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    @staticmethod
    async def update_provider(
        db: AsyncSession, provider_id: UUID, data: LLMProviderUpdate
    ) -> LLMProviderResponse | None:
        set_clauses: list[str] = ["updated_at = now()"]
        params: dict = {"provider_id": provider_id}

        if data.label is not None:
            set_clauses.append("label = :label")
            params["label"] = data.label
        if data.api_key is not None:
            set_clauses.append("api_key = :api_key")
            params["api_key"] = data.api_key
        if data.base_url is not None:
            set_clauses.append("base_url = :base_url")
            params["base_url"] = data.base_url
        if data.is_active is not None:
            set_clauses.append("is_active = :is_active")
            params["is_active"] = data.is_active

        result = await db.execute(
            text(f"""
                UPDATE llm_providers
                SET {', '.join(set_clauses)}
                WHERE id = :provider_id
                RETURNING id, provider, label, api_key, base_url, is_active, created_at, updated_at
            """),
            params,
        )
        row = result.mappings().first()
        if not row:
            return None
        return LLMProviderResponse(
            id=row["id"],
            provider=row["provider"],
            label=row["label"],
            api_key_set=bool(row["api_key"]),
            base_url=row["base_url"],
            is_active=row["is_active"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    async def deactivate_provider(db: AsyncSession, provider_id: UUID) -> bool:
        result = await db.execute(
            text("""
                UPDATE llm_providers
                SET is_active = false, updated_at = now()
                WHERE id = :provider_id
            """),
            {"provider_id": provider_id},
        )
        return (result.rowcount or 0) > 0

    @staticmethod
    async def get_provider_with_key(db: AsyncSession, provider_id: UUID) -> dict | None:
        """Fetch a provider including the raw API key (internal use only)."""
        result = await db.execute(
            text("""
                SELECT id, provider, label, api_key, base_url, is_active
                FROM llm_providers
                WHERE id = :provider_id
            """),
            {"provider_id": provider_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Tier config
    # ------------------------------------------------------------------

    @staticmethod
    async def list_tier_configs(db: AsyncSession) -> list[LLMTierConfigResponse]:
        """Return config for all 3 tiers, showing DB override or env default."""
        from app.dependencies import get_settings

        settings = get_settings()

        result = await db.execute(
            text("""
                SELECT t.tier, t.provider_id, t.model, t.updated_at, t.updated_by,
                       p.label AS provider_label, p.provider AS provider_type
                FROM llm_tier_config t
                JOIN llm_providers p ON p.id = t.provider_id
            """)
        )
        db_configs = {r["tier"]: dict(r) for r in result.mappings().all()}

        items = []
        for tier in LLMTier:
            if tier.value in db_configs:
                cfg = db_configs[tier.value]
                items.append(
                    LLMTierConfigResponse(
                        tier=tier,
                        provider_id=cfg["provider_id"],
                        provider_label=cfg["provider_label"],
                        provider_type=cfg["provider_type"],
                        model=cfg["model"],
                        updated_at=cfg["updated_at"],
                        updated_by=cfg["updated_by"],
                        is_env_default=False,
                    )
                )
            else:
                items.append(
                    LLMTierConfigResponse(
                        tier=tier,
                        model=settings.query_llm_model or settings.llm_model
                        if tier == LLMTier.QUERY
                        else settings.llm_model,
                        is_env_default=True,
                    )
                )
        return items

    @staticmethod
    async def set_tier_config(
        db: AsyncSession, tier: LLMTier, data: LLMTierConfigSet, user_id: UUID | None = None
    ) -> LLMTierConfigResponse:
        # Verify provider exists and is active
        prov = await db.execute(
            text("SELECT id, label, provider FROM llm_providers WHERE id = :pid AND is_active = true"),
            {"pid": data.provider_id},
        )
        provider_row = prov.mappings().first()
        if not provider_row:
            raise ValueError("Provider not found or inactive")

        result = await db.execute(
            text("""
                INSERT INTO llm_tier_config (tier, provider_id, model, updated_by)
                VALUES (:tier, :provider_id, :model, :updated_by)
                ON CONFLICT (tier) DO UPDATE SET
                    provider_id = EXCLUDED.provider_id,
                    model = EXCLUDED.model,
                    updated_at = now(),
                    updated_by = EXCLUDED.updated_by
                RETURNING tier, provider_id, model, updated_at, updated_by
            """),
            {
                "tier": tier.value,
                "provider_id": data.provider_id,
                "model": data.model,
                "updated_by": user_id,
            },
        )
        r = result.mappings().one()
        return LLMTierConfigResponse(
            tier=tier,
            provider_id=r["provider_id"],
            provider_label=provider_row["label"],
            provider_type=provider_row["provider"],
            model=r["model"],
            updated_at=r["updated_at"],
            updated_by=r["updated_by"],
            is_env_default=False,
        )

    @staticmethod
    async def delete_tier_config(db: AsyncSession, tier: LLMTier) -> bool:
        result = await db.execute(
            text("DELETE FROM llm_tier_config WHERE tier = :tier"),
            {"tier": tier.value},
        )
        return (result.rowcount or 0) > 0

    # ------------------------------------------------------------------
    # Test connection
    # ------------------------------------------------------------------

    @staticmethod
    async def test_connection(db: AsyncSession, provider_id: UUID) -> TestConnectionResponse:
        """Test connectivity by making a trivial LLM completion call."""
        provider = await LLMConfigService.get_provider_with_key(db, provider_id)
        if not provider:
            return TestConnectionResponse(success=False, error="Provider not found")

        try:
            from app.common.llm import LLMClient
            from app.config import Settings

            settings = Settings()
            # Build a temporary LLMClient with the provider's credentials
            prov_type = provider["provider"]
            # Override settings for temporary client
            settings.llm_provider = prov_type
            if prov_type == "anthropic":
                settings.anthropic_api_key = provider["api_key"]
            elif prov_type in ("openai", "gemini"):
                settings.openai_api_key = provider["api_key"]
                if prov_type == "gemini":
                    settings.gemini_api_key = provider["api_key"]
            elif prov_type == "ollama":
                settings.ollama_base_url = provider["base_url"] or settings.ollama_base_url

            if provider["base_url"] and prov_type != "ollama":
                if prov_type == "openai":
                    pass  # base_url handled in LLMClient

            # Use a simple test model appropriate for each provider
            if prov_type == "anthropic":
                test_model = "claude-sonnet-4-5-20250929"
            elif prov_type == "gemini":
                test_model = "gemini-2.0-flash"
            else:
                test_model = "gpt-4o-mini"
            settings.llm_model = test_model

            client = LLMClient(settings)
            start = time.perf_counter()
            await client.complete(
                [{"role": "user", "content": "Reply with OK."}],
                max_tokens=4,
                temperature=0,
            )
            latency_ms = round((time.perf_counter() - start) * 1000)
            return TestConnectionResponse(success=True, latency_ms=latency_ms)
        except Exception as exc:
            return TestConnectionResponse(success=False, error=str(exc))

    # ------------------------------------------------------------------
    # Model discovery (all providers)
    # ------------------------------------------------------------------

    @staticmethod
    async def discover_models(db: AsyncSession, provider_id: UUID) -> list[AvailableModel]:
        """Discover available models for a given provider."""
        provider = await LLMConfigService.get_provider_with_key(db, provider_id)
        if not provider:
            raise ValueError("Provider not found")
        if not provider["is_active"]:
            raise ValueError("Provider is inactive")

        prov_type = provider["provider"]

        if prov_type == "anthropic":
            return LLMConfigService._discover_anthropic_models()
        elif prov_type == "openai":
            return await LLMConfigService._discover_openai_models(
                api_key=provider["api_key"],
                base_url=provider["base_url"] or None,
            )
        elif prov_type == "gemini":
            return await LLMConfigService._discover_gemini_models(
                api_key=provider["api_key"],
            )
        elif prov_type == "ollama":
            return await LLMConfigService._discover_ollama_models_as_available(
                base_url=provider["base_url"],
            )
        else:
            raise ValueError(f"Unknown provider type: {prov_type}")

    @staticmethod
    def _discover_anthropic_models() -> list[AvailableModel]:
        from app.llm_config.pricing import CURATED_ANTHROPIC_MODELS

        return [AvailableModel(**m) for m in CURATED_ANTHROPIC_MODELS]

    @staticmethod
    async def _discover_openai_models(api_key: str, base_url: str | None = None) -> list[AvailableModel]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        response = await client.models.list()
        models = []
        for m in response.data:
            mid = m.id
            if not any(mid.startswith(p) for p in ("gpt-", "o1-", "o3-", "o4-")):
                continue
            models.append(
                AvailableModel(
                    id=mid,
                    display_name=mid,
                    context_window=None,
                )
            )
        models.sort(key=lambda x: getattr(x, "id", ""))
        return models

    @staticmethod
    async def _discover_gemini_models(api_key: str) -> list[AvailableModel]:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = await client.aio.models.list()
        # AsyncPager — collect into list
        models_list: list = []
        async for m in response:
            models_list.append(m)
        models = []
        for m in models_list:
            name = m.name or ""
            if not name.startswith("models/gemini-"):
                continue
            model_id = name.removeprefix("models/")
            display = m.display_name or model_id
            models.append(
                AvailableModel(
                    id=model_id,
                    display_name=display,
                    context_window=getattr(m, "input_token_limit", None),
                )
            )

        # Sort: pro first, then flash, then rest
        def _sort_key(m: AvailableModel) -> tuple[int, str]:
            if "pro" in m.id:
                return (0, m.id)
            if "flash" in m.id:
                return (1, m.id)
            return (2, m.id)

        models.sort(key=_sort_key)
        return models

    @staticmethod
    async def _discover_ollama_models_as_available(
        base_url: str = "",
    ) -> list[AvailableModel]:
        ollama_models = await LLMConfigService.discover_ollama_models(base_url)
        return sorted(
            [AvailableModel(id=m.name, display_name=m.name, context_window=None) for m in ollama_models],
            key=lambda x: x.id,
        )

    # ------------------------------------------------------------------
    # Ollama discovery
    # ------------------------------------------------------------------

    @staticmethod
    async def discover_ollama_models(base_url: str = "") -> list[OllamaModel]:
        """Query local Ollama API for available models."""
        import httpx

        from app.dependencies import get_settings

        settings = get_settings()
        raw = base_url or settings.ollama_base_url
        url = raw.removesuffix("/v1").removesuffix("/")

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{url}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                return [
                    OllamaModel(
                        name=m["name"],
                        size=m.get("size"),
                        modified_at=m.get("modified_at"),
                    )
                    for m in data.get("models", [])
                ]
        except Exception as exc:
            logger.warning("ollama.discover.failed", error=str(exc))
            return []

    # ------------------------------------------------------------------
    # Cost estimation
    # ------------------------------------------------------------------

    @staticmethod
    async def estimate_costs(db: AsyncSession, period_days: int = 30) -> CostEstimateResponse:
        from app.llm_config.pricing import get_model_pricing

        # Map node_names to tiers
        tier_node_map: dict[str, str] = {
            "query": "investigation_agent,verify_claims_decompose,verify_claims_judge,classify,rewrite,synthesize",
            "analysis": "generate_follow_ups,sentiment,completeness,case_setup,memo",
            "ingestion": "relationship_extraction",
        }

        tiers: list[TierCostEstimate] = []
        total_cost = 0.0

        # Get current tier configs to know which model each tier uses
        tier_configs = await LLMConfigService.list_tier_configs(db)
        tier_model_map = {tc.tier.value: tc.model or "unknown" for tc in tier_configs}

        for tier_name, node_names_str in tier_node_map.items():
            node_list = [n.strip() for n in node_names_str.split(",")]
            placeholders = ", ".join(f":n{i}" for i in range(len(node_list)))
            params: dict = {f"n{i}": n for i, n in enumerate(node_list)}
            params["days"] = period_days

            result = await db.execute(
                text(f"""
                    SELECT COALESCE(SUM(input_tokens), 0) AS input_tokens,
                           COALESCE(SUM(output_tokens), 0) AS output_tokens
                    FROM ai_audit_log
                    WHERE node_name IN ({placeholders})
                      AND created_at >= now() - make_interval(days => :days)
                """),
                params,
            )
            row = result.mappings().one()
            input_tokens = row["input_tokens"]
            output_tokens = row["output_tokens"]

            model = tier_model_map.get(tier_name, "unknown")
            input_price, output_price = get_model_pricing(model)
            cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
            total_cost += cost

            tiers.append(
                TierCostEstimate(
                    tier=LLMTier(tier_name),
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    estimated_cost_usd=round(cost, 4),
                )
            )

        return CostEstimateResponse(
            period_days=period_days,
            tiers=tiers,
            total_cost_usd=round(total_cost, 4),
        )

    # ------------------------------------------------------------------
    # Overview
    # ------------------------------------------------------------------

    @staticmethod
    async def get_overview(db: AsyncSession) -> LLMConfigOverview:
        from app.dependencies import get_settings

        settings = get_settings()

        providers = await LLMConfigService.list_providers(db)
        tiers = await LLMConfigService.list_tier_configs(db)

        env_defaults = {
            "query": f"{settings.llm_provider}/{settings.query_llm_model or settings.llm_model}",
            "analysis": f"{settings.llm_provider}/{settings.llm_model}",
            "ingestion": f"{settings.llm_provider}/{settings.llm_model}",
        }

        return LLMConfigOverview(
            providers=providers,
            tiers=tiers,
            env_defaults=env_defaults,
        )
