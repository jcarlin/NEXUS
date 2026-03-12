"""Tests for auto-registration of LLM providers from environment."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.llm_config.schemas import LLMProviderResponse, LLMProviderType, OllamaModel
from app.llm_config.service import LLMConfigService

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_PROVIDER_ID = uuid4()


def _make_provider_response(
    provider: str = "anthropic",
    label: str = "Test",
    is_active: bool = True,
) -> LLMProviderResponse:
    return LLMProviderResponse(
        id=uuid4(),
        provider=LLMProviderType(provider),
        label=label,
        api_key_set=True,
        base_url="",
        is_active=is_active,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _make_settings(**overrides: str) -> MagicMock:
    s = MagicMock()
    s.anthropic_api_key = overrides.get("anthropic_api_key", "")
    s.openai_api_key = overrides.get("openai_api_key", "")
    s.gemini_api_key = overrides.get("gemini_api_key", "")
    s.ollama_base_url = overrides.get("ollama_base_url", "http://localhost:11434/v1")
    return s


def _make_db_for_create() -> AsyncMock:
    """Return a mock db where execute returns a valid provider row."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.one.return_value = {
        "id": uuid4(),
        "provider": "anthropic",
        "label": "Anthropic (from env)",
        "api_key": "sk-test",
        "base_url": "",
        "is_active": True,
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    db.execute.return_value = mock_result
    return db


class TestAutoRegisterFromEnv:
    @pytest.mark.asyncio
    async def test_registers_anthropic_from_env(self) -> None:
        """When ANTHROPIC_API_KEY is set and no active anthropic provider exists, auto-register."""
        db = _make_db_for_create()
        settings = _make_settings(anthropic_api_key="sk-ant-test123")

        with patch.object(LLMConfigService, "discover_ollama_models", new_callable=AsyncMock, return_value=[]):
            new = await LLMConfigService._auto_register_providers(db, [], settings)

        assert len(new) == 1
        assert new[0].label == "Anthropic (from env)"

    @pytest.mark.asyncio
    async def test_registers_multiple_providers(self) -> None:
        """When multiple API keys are set, register all of them."""
        call_count = 0

        def make_result(*a, **kw):
            nonlocal call_count
            call_count += 1
            providers = ["anthropic", "openai", "gemini"]
            labels = ["Anthropic (from env)", "OpenAI (from env)", "Gemini (from env)"]
            idx = min(call_count - 1, 2)
            m = MagicMock()
            m.mappings.return_value.one.return_value = {
                "id": uuid4(),
                "provider": providers[idx],
                "label": labels[idx],
                "api_key": "sk-test",
                "base_url": "",
                "is_active": True,
                "created_at": _NOW,
                "updated_at": _NOW,
            }
            return m

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=make_result)
        settings = _make_settings(
            anthropic_api_key="sk-ant",
            openai_api_key="sk-oai",
            gemini_api_key="gemini-key",
        )

        with patch.object(LLMConfigService, "discover_ollama_models", new_callable=AsyncMock, return_value=[]):
            new = await LLMConfigService._auto_register_providers(db, [], settings)

        assert len(new) == 3

    @pytest.mark.asyncio
    async def test_skips_if_already_active(self) -> None:
        """When an active provider of that type exists, don't create a duplicate."""
        existing = [_make_provider_response(provider="anthropic", is_active=True)]
        settings = _make_settings(anthropic_api_key="sk-ant-test123")
        db = AsyncMock()

        with patch.object(LLMConfigService, "discover_ollama_models", new_callable=AsyncMock, return_value=[]):
            new = await LLMConfigService._auto_register_providers(db, existing, settings)

        assert len(new) == 0
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_empty_api_key(self) -> None:
        """When API key is empty string, don't try to register."""
        settings = _make_settings(anthropic_api_key="")
        db = AsyncMock()

        with patch.object(LLMConfigService, "discover_ollama_models", new_callable=AsyncMock, return_value=[]):
            new = await LLMConfigService._auto_register_providers(db, [], settings)

        assert len(new) == 0

    @pytest.mark.asyncio
    async def test_handles_integrity_error(self) -> None:
        """When create_provider raises (e.g. IntegrityError), skip gracefully."""
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=Exception("UNIQUE constraint"))
        settings = _make_settings(anthropic_api_key="sk-ant-test123")

        with patch.object(LLMConfigService, "discover_ollama_models", new_callable=AsyncMock, return_value=[]):
            new = await LLMConfigService._auto_register_providers(db, [], settings)

        assert len(new) == 0


class TestAutoRegisterOllama:
    @pytest.mark.asyncio
    async def test_registers_ollama_when_reachable(self) -> None:
        """When Ollama probe returns models, auto-register it."""
        db = _make_db_for_create()
        # Override the provider type in the mock result for Ollama
        mock_result = MagicMock()
        mock_result.mappings.return_value.one.return_value = {
            "id": uuid4(),
            "provider": "ollama",
            "label": "Ollama (auto-detected)",
            "api_key": "",
            "base_url": "http://localhost:11434/v1",
            "is_active": True,
            "created_at": _NOW,
            "updated_at": _NOW,
        }
        db.execute.return_value = mock_result
        settings = _make_settings()

        with patch.object(
            LLMConfigService,
            "discover_ollama_models",
            new_callable=AsyncMock,
            return_value=[OllamaModel(name="llama3:latest", size=4_000_000_000)],
        ):
            new = await LLMConfigService._auto_register_providers(db, [], settings)

        assert len(new) == 1
        assert new[0].label == "Ollama (auto-detected)"

    @pytest.mark.asyncio
    async def test_skips_ollama_when_unreachable(self) -> None:
        """When Ollama probe returns empty, don't register."""
        db = AsyncMock()
        settings = _make_settings()

        with patch.object(
            LLMConfigService,
            "discover_ollama_models",
            new_callable=AsyncMock,
            return_value=[],
        ):
            new = await LLMConfigService._auto_register_providers(db, [], settings)

        assert len(new) == 0

    @pytest.mark.asyncio
    async def test_skips_ollama_if_already_active(self) -> None:
        """When an active Ollama provider exists, don't create a duplicate."""
        existing = [_make_provider_response(provider="ollama", is_active=True)]
        settings = _make_settings()
        db = AsyncMock()

        # discover_ollama_models should NOT even be called
        with patch.object(
            LLMConfigService,
            "discover_ollama_models",
            new_callable=AsyncMock,
        ) as mock_discover:
            new = await LLMConfigService._auto_register_providers(db, existing, settings)

        assert len(new) == 0
        mock_discover.assert_not_called()


class TestGetOverviewAutoRegister:
    @pytest.mark.asyncio
    @patch("app.dependencies.get_settings")
    async def test_overview_includes_auto_registered(self, mock_get_settings: MagicMock) -> None:
        """get_overview auto-registers providers and includes them in response."""
        s = mock_get_settings.return_value
        s.llm_provider = "anthropic"
        s.llm_model = "claude-sonnet-4-5-20250929"
        s.query_llm_model = ""
        s.embedding_provider = "local"
        s.embedding_model = "BAAI/bge-small-en-v1.5"
        s.embedding_dimensions = 384
        s.anthropic_api_key = "sk-ant-test"
        s.openai_api_key = ""
        s.gemini_api_key = ""
        s.ollama_base_url = "http://localhost:11434/v1"

        db = AsyncMock()
        call_count = 0

        def make_result(*a, **kw):
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            if call_count == 1:
                # list_providers — empty
                m.mappings.return_value.all.return_value = []
            elif call_count == 2:
                # create_provider (auto-register anthropic)
                m.mappings.return_value.one.return_value = {
                    "id": uuid4(),
                    "provider": "anthropic",
                    "label": "Anthropic (from env)",
                    "api_key": "sk-ant-test",
                    "base_url": "",
                    "is_active": True,
                    "created_at": _NOW,
                    "updated_at": _NOW,
                }
            else:
                # list_tier_configs
                m.mappings.return_value.all.return_value = []
            return m

        db.execute = AsyncMock(side_effect=make_result)

        with patch.object(LLMConfigService, "discover_ollama_models", new_callable=AsyncMock, return_value=[]):
            overview = await LLMConfigService.get_overview(db)

        assert len(overview.providers) == 1
        assert overview.providers[0].label == "Anthropic (from env)"
