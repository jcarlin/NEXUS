"""Tests for LLMConfigService methods."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.llm_config.schemas import (
    LLMProviderCreate,
    LLMProviderUpdate,
    LLMTier,
    LLMTierConfigSet,
)
from app.llm_config.service import LLMConfigService

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_PROVIDER_ID = uuid4()


def _make_provider_row(
    provider_id=None,
    provider="anthropic",
    label="Test",
    api_key="sk-test",
    base_url="",
    is_active=True,
) -> dict:
    return {
        "id": provider_id or _PROVIDER_ID,
        "provider": provider,
        "label": label,
        "api_key": api_key,
        "base_url": base_url,
        "is_active": is_active,
        "created_at": _NOW,
        "updated_at": _NOW,
    }


class TestListProviders:
    @pytest.mark.asyncio
    async def test_returns_formatted_list(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            _make_provider_row(),
            _make_provider_row(provider_id=uuid4(), label="Second"),
        ]
        db.execute.return_value = mock_result

        providers = await LLMConfigService.list_providers(db)
        assert len(providers) == 2
        assert providers[0].label == "Test"
        assert providers[0].api_key_set is True

    @pytest.mark.asyncio
    async def test_empty_api_key_shows_false(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            _make_provider_row(api_key=""),
        ]
        db.execute.return_value = mock_result

        providers = await LLMConfigService.list_providers(db)
        assert providers[0].api_key_set is False


class TestCreateProvider:
    @pytest.mark.asyncio
    async def test_creates_and_returns(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.one.return_value = _make_provider_row()
        db.execute.return_value = mock_result

        data = LLMProviderCreate(provider="anthropic", label="Test", api_key="sk-test")
        result = await LLMConfigService.create_provider(db, data)
        assert result.label == "Test"
        assert result.api_key_set is True
        db.execute.assert_called_once()


class TestUpdateProvider:
    @pytest.mark.asyncio
    async def test_partial_update(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = _make_provider_row(label="Updated")
        db.execute.return_value = mock_result

        data = LLMProviderUpdate(label="Updated")
        result = await LLMConfigService.update_provider(db, _PROVIDER_ID, data)
        assert result is not None
        assert result.label == "Updated"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = None
        db.execute.return_value = mock_result

        data = LLMProviderUpdate(label="Updated")
        result = await LLMConfigService.update_provider(db, uuid4(), data)
        assert result is None


class TestDeactivateProvider:
    @pytest.mark.asyncio
    async def test_returns_true_when_found(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        db.execute.return_value = mock_result

        assert await LLMConfigService.deactivate_provider(db, _PROVIDER_ID) is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        db.execute.return_value = mock_result

        assert await LLMConfigService.deactivate_provider(db, uuid4()) is False


class TestListTierConfigs:
    @pytest.mark.asyncio
    @patch("app.dependencies.get_settings")
    async def test_shows_db_override_and_env_defaults(self, mock_settings: MagicMock) -> None:
        s = mock_settings.return_value
        s.llm_provider = "anthropic"
        s.llm_model = "claude-sonnet-4-5-20250929"
        s.query_llm_model = ""

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {
                "tier": "query",
                "provider_id": _PROVIDER_ID,
                "model": "gpt-4o",
                "updated_at": _NOW,
                "updated_by": None,
                "provider_label": "OpenAI Prod",
                "provider_type": "openai",
            }
        ]
        db.execute.return_value = mock_result

        tiers = await LLMConfigService.list_tier_configs(db)
        assert len(tiers) == 3
        # Query tier has DB override
        query_tier = next(t for t in tiers if t.tier == LLMTier.QUERY)
        assert query_tier.is_env_default is False
        assert query_tier.model == "gpt-4o"
        # Other tiers fall back to env
        analysis_tier = next(t for t in tiers if t.tier == LLMTier.ANALYSIS)
        assert analysis_tier.is_env_default is True


class TestSetTierConfig:
    @pytest.mark.asyncio
    async def test_upserts_config(self) -> None:
        db = AsyncMock()
        call_count = 0

        def make_result(*a, **kw):
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            if call_count == 1:
                # Provider lookup
                m.mappings.return_value.first.return_value = {
                    "id": _PROVIDER_ID,
                    "label": "OpenAI",
                    "provider": "openai",
                }
            else:
                # UPSERT
                m.mappings.return_value.one.return_value = {
                    "tier": "query",
                    "provider_id": _PROVIDER_ID,
                    "model": "gpt-4o",
                    "updated_at": _NOW,
                    "updated_by": None,
                }
            return m

        db.execute = AsyncMock(side_effect=make_result)

        data = LLMTierConfigSet(provider_id=_PROVIDER_ID, model="gpt-4o")
        result = await LLMConfigService.set_tier_config(db, LLMTier.QUERY, data)
        assert result.model == "gpt-4o"
        assert result.is_env_default is False

    @pytest.mark.asyncio
    async def test_raises_on_inactive_provider(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = None
        db.execute.return_value = mock_result

        data = LLMTierConfigSet(provider_id=uuid4(), model="gpt-4o")
        with pytest.raises(ValueError, match="Provider not found or inactive"):
            await LLMConfigService.set_tier_config(db, LLMTier.QUERY, data)


class TestDeleteTierConfig:
    @pytest.mark.asyncio
    async def test_returns_true_on_delete(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        db.execute.return_value = mock_result

        assert await LLMConfigService.delete_tier_config(db, LLMTier.QUERY) is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_config(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        db.execute.return_value = mock_result

        assert await LLMConfigService.delete_tier_config(db, LLMTier.QUERY) is False


class TestDiscoverOllamaModels:
    @pytest.mark.asyncio
    @patch("app.dependencies.get_settings")
    async def test_returns_models(self, mock_settings: MagicMock) -> None:
        s = mock_settings.return_value
        s.ollama_base_url = "http://localhost:11434/v1"

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "models": [
                {"name": "llama3:latest", "size": 4_000_000_000},
                {"name": "mistral:latest", "size": 7_000_000_000, "modified_at": "2025-01-01"},
            ]
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            models = await LLMConfigService.discover_ollama_models()
            assert len(models) == 2
            assert models[0].name == "llama3:latest"

    @pytest.mark.asyncio
    @patch("app.dependencies.get_settings")
    async def test_returns_empty_on_error(self, mock_settings: MagicMock) -> None:
        s = mock_settings.return_value
        s.ollama_base_url = "http://localhost:11434/v1"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = Exception("Connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            models = await LLMConfigService.discover_ollama_models()
            assert models == []


class TestDiscoverModels:
    @pytest.mark.asyncio
    async def test_discover_models_anthropic(self) -> None:
        """Anthropic returns curated list with no external calls."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = _make_provider_row(
            provider="anthropic", api_key="sk-ant-test"
        )
        db.execute.return_value = mock_result

        models = await LLMConfigService.discover_models(db, _PROVIDER_ID)
        assert len(models) >= 3
        assert models[0].id == "claude-opus-4-20250514"
        assert models[0].context_window == 200_000

    @pytest.mark.asyncio
    async def test_discover_models_openai_filters_chat(self) -> None:
        """OpenAI discovery filters to only chat-capable models."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = _make_provider_row(
            provider="openai", api_key="sk-openai-test"
        )
        db.execute.return_value = mock_result

        # Mock OpenAI models.list() response
        mock_model_gpt = MagicMock()
        mock_model_gpt.id = "gpt-4o"
        mock_model_gpt.created = 1700000000

        mock_model_embed = MagicMock()
        mock_model_embed.id = "text-embedding-3-small"
        mock_model_embed.created = 1700000001

        mock_model_o3 = MagicMock()
        mock_model_o3.id = "o3-mini"
        mock_model_o3.created = 1700000002

        mock_response = MagicMock()
        mock_response.data = [mock_model_gpt, mock_model_embed, mock_model_o3]

        with patch("openai.AsyncOpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_client.models.list = AsyncMock(return_value=mock_response)
            mock_openai_cls.return_value = mock_client

            models = await LLMConfigService.discover_models(db, _PROVIDER_ID)

        model_ids = [m.id for m in models]
        assert "gpt-4o" in model_ids
        assert "o3-mini" in model_ids
        assert "text-embedding-3-small" not in model_ids

    @pytest.mark.asyncio
    async def test_discover_models_gemini_filters_generative(self) -> None:
        """Gemini discovery strips models/ prefix and filters to gemini-*."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = _make_provider_row(
            provider="gemini", api_key="gemini-test"
        )
        db.execute.return_value = mock_result

        mock_gemini = MagicMock()
        mock_gemini.name = "models/gemini-2.0-flash"
        mock_gemini.display_name = "Gemini 2.0 Flash"
        mock_gemini.input_token_limit = 1_000_000

        mock_non_gemini = MagicMock()
        mock_non_gemini.name = "models/embedding-001"
        mock_non_gemini.display_name = "Embedding"
        mock_non_gemini.input_token_limit = 2048

        with patch("google.genai.Client") as mock_genai_cls:
            mock_client = MagicMock()

            # Mock client.aio.models.list() returning an async iterator
            async def _async_iter():
                for item in [mock_gemini, mock_non_gemini]:
                    yield item

            mock_client.aio.models.list = AsyncMock(return_value=_async_iter())
            mock_genai_cls.return_value = mock_client

            models = await LLMConfigService.discover_models(db, _PROVIDER_ID)

        model_ids = [m.id for m in models]
        assert "gemini-2.0-flash" in model_ids
        assert "embedding-001" not in model_ids
        assert models[0].context_window == 1_000_000

    @pytest.mark.asyncio
    async def test_discover_models_ollama_delegates(self) -> None:
        """Ollama discovery delegates to existing discover_ollama_models."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = _make_provider_row(
            provider="ollama", api_key="", base_url="http://localhost:11434"
        )
        db.execute.return_value = mock_result

        from app.llm_config.schemas import OllamaModel

        with patch.object(
            LLMConfigService,
            "discover_ollama_models",
            new_callable=AsyncMock,
            return_value=[
                OllamaModel(name="llama3:latest", size=4_000_000_000),
                OllamaModel(name="mistral:latest", size=7_000_000_000),
            ],
        ):
            models = await LLMConfigService.discover_models(db, _PROVIDER_ID)

        assert len(models) == 2
        assert models[0].id == "llama3:latest"
        assert models[1].id == "mistral:latest"

    @pytest.mark.asyncio
    async def test_discover_models_provider_not_found(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = None
        db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Provider not found"):
            await LLMConfigService.discover_models(db, uuid4())

    @pytest.mark.asyncio
    async def test_discover_models_inactive_provider(self) -> None:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = _make_provider_row(is_active=False)
        db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Provider is inactive"):
            await LLMConfigService.discover_models(db, _PROVIDER_ID)


class TestEstimateCosts:
    @pytest.mark.asyncio
    @patch("app.llm_config.pricing.get_model_pricing")
    @patch.object(LLMConfigService, "list_tier_configs")
    async def test_aggregates_costs(self, mock_tiers: AsyncMock, mock_pricing: MagicMock) -> None:
        from app.llm_config.schemas import LLMTierConfigResponse

        mock_tiers.return_value = [
            LLMTierConfigResponse(tier=LLMTier.QUERY, model="gpt-4o", is_env_default=True),
            LLMTierConfigResponse(tier=LLMTier.ANALYSIS, model="gpt-4o", is_env_default=True),
            LLMTierConfigResponse(tier=LLMTier.INGESTION, model="gpt-4o", is_env_default=True),
        ]
        mock_pricing.return_value = (2.50, 10.0)

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.one.return_value = {
            "input_tokens": 1_000_000,
            "output_tokens": 500_000,
        }
        db.execute.return_value = mock_result

        result = await LLMConfigService.estimate_costs(db, period_days=30)
        assert result.period_days == 30
        assert len(result.tiers) == 3
        assert result.total_cost_usd > 0


class TestResolveTestModel:
    @pytest.mark.asyncio
    async def test_uses_tier_configured_model(self) -> None:
        """When a tier config references this provider, use that model."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = {"model": "llama3:8b"}
        db.execute.return_value = mock_result

        model = await LLMConfigService._resolve_test_model(db, _PROVIDER_ID, "ollama", "http://localhost:11434")
        assert model == "llama3:8b"

    @pytest.mark.asyncio
    async def test_ollama_discovers_model(self) -> None:
        """When no tier config, Ollama discovers available models."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = None
        db.execute.return_value = mock_result

        from app.llm_config.schemas import OllamaModel

        with patch.object(
            LLMConfigService,
            "discover_ollama_models",
            new_callable=AsyncMock,
            return_value=[OllamaModel(name="qwen2:7b"), OllamaModel(name="llama3:8b")],
        ):
            model = await LLMConfigService._resolve_test_model(db, _PROVIDER_ID, "ollama", "http://localhost:11434")
        assert model == "qwen2:7b"

    @pytest.mark.asyncio
    async def test_ollama_raises_when_no_models(self) -> None:
        """Ollama with no models available raises ValueError."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = None
        db.execute.return_value = mock_result

        with patch.object(
            LLMConfigService,
            "discover_ollama_models",
            new_callable=AsyncMock,
            return_value=[],
        ):
            with pytest.raises(ValueError, match="No Ollama models available"):
                await LLMConfigService._resolve_test_model(db, _PROVIDER_ID, "ollama", "http://localhost:11434")

    @pytest.mark.asyncio
    async def test_cloud_provider_defaults(self) -> None:
        """Cloud providers fall back to sensible defaults."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = None
        db.execute.return_value = mock_result

        model = await LLMConfigService._resolve_test_model(db, _PROVIDER_ID, "anthropic", "")
        assert model == "claude-sonnet-4-5-20250929"

        model = await LLMConfigService._resolve_test_model(db, _PROVIDER_ID, "gemini", "")
        assert model == "gemini-2.0-flash"


class TestGetOverview:
    @pytest.mark.asyncio
    @patch("app.dependencies.get_settings")
    async def test_includes_embedding_config(self, mock_settings: MagicMock) -> None:
        s = mock_settings.return_value
        s.llm_provider = "anthropic"
        s.llm_model = "claude-sonnet-4-5-20250929"
        s.query_llm_model = ""
        s.embedding_provider = "local"
        s.embedding_model = "BAAI/bge-small-en-v1.5"
        s.embedding_dimensions = 384

        db = AsyncMock()
        # list_providers
        mock_providers = MagicMock()
        mock_providers.mappings.return_value.all.return_value = []
        # list_tier_configs
        mock_tiers = MagicMock()
        mock_tiers.mappings.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[mock_providers, mock_tiers])

        overview = await LLMConfigService.get_overview(db)
        assert overview.embedding.provider == "local"
        assert overview.embedding.model == "BAAI/bge-small-en-v1.5"
        assert overview.embedding.dimensions == 384
