"""Tests for LLM config resolver (DB + env fallback + cache)."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm_config.resolver import (
    _cache,
    _resolve_from_env,
    clear_cache,
    resolve_llm_config,
    resolve_llm_config_sync,
)
from app.llm_config.schemas import LLMTier, ResolvedLLMConfig


@pytest.fixture(autouse=True)
def _clear_resolver_cache():
    """Ensure each test starts with a clean cache."""
    _cache.clear()
    yield
    _cache.clear()


class TestResolveFromEnv:
    @patch("app.dependencies.get_settings")
    def test_anthropic_provider(self, mock_settings: MagicMock) -> None:
        s = mock_settings.return_value
        s.llm_provider = "anthropic"
        s.llm_model = "claude-sonnet-4-5-20250929"
        s.query_llm_model = ""
        s.anthropic_api_key = "sk-ant-test"

        cfg = _resolve_from_env("analysis")
        assert cfg.provider == "anthropic"
        assert cfg.model == "claude-sonnet-4-5-20250929"
        assert cfg.api_key == "sk-ant-test"

    @patch("app.dependencies.get_settings")
    def test_query_tier_uses_query_model(self, mock_settings: MagicMock) -> None:
        s = mock_settings.return_value
        s.llm_provider = "anthropic"
        s.llm_model = "claude-sonnet-4-5-20250929"
        s.query_llm_model = "claude-opus-4-20250514"
        s.anthropic_api_key = "sk-ant-test"

        cfg = _resolve_from_env("query")
        assert cfg.model == "claude-opus-4-20250514"

    @patch("app.dependencies.get_settings")
    def test_ollama_provider(self, mock_settings: MagicMock) -> None:
        s = mock_settings.return_value
        s.llm_provider = "ollama"
        s.llm_model = "llama3"
        s.query_llm_model = ""
        s.ollama_base_url = "http://localhost:11434/v1"

        cfg = _resolve_from_env("ingestion")
        assert cfg.provider == "ollama"
        assert cfg.base_url == "http://localhost:11434/v1"
        assert cfg.api_key == ""

    @patch("app.dependencies.get_settings")
    def test_openai_provider(self, mock_settings: MagicMock) -> None:
        s = mock_settings.return_value
        s.llm_provider = "openai"
        s.llm_model = "gpt-4o"
        s.query_llm_model = ""
        s.openai_api_key = "sk-openai-test"

        cfg = _resolve_from_env("query")
        assert cfg.provider == "openai"
        assert cfg.api_key == "sk-openai-test"

    @patch("app.dependencies.get_settings")
    def test_gemini_provider(self, mock_settings: MagicMock) -> None:
        s = mock_settings.return_value
        s.llm_provider = "gemini"
        s.llm_model = "gemini-2.0-flash"
        s.query_llm_model = ""
        s.gemini_api_key = "gemini-key"

        cfg = _resolve_from_env("analysis")
        assert cfg.provider == "gemini"
        assert cfg.api_key == "gemini-key"


class TestResolveAsync:
    @pytest.mark.asyncio
    async def test_returns_db_config_when_available(self) -> None:
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = {
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-db-key",
            "base_url": "",
        }
        mock_db.execute.return_value = mock_result

        cfg = await resolve_llm_config(LLMTier.QUERY, mock_db)
        assert cfg.provider == "openai"
        assert cfg.model == "gpt-4o"
        assert cfg.api_key == "sk-db-key"

    @pytest.mark.asyncio
    @patch("app.llm_config.resolver._resolve_from_env")
    async def test_falls_back_to_env_when_no_db_config(self, mock_env: MagicMock) -> None:
        mock_env.return_value = ResolvedLLMConfig(
            provider="anthropic", model="claude-sonnet-4-5-20250929", api_key="sk-env", base_url=""
        )
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result

        cfg = await resolve_llm_config("query", mock_db)
        assert cfg.provider == "anthropic"
        mock_env.assert_called_once_with("query")

    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self) -> None:
        expected = ResolvedLLMConfig(
            provider="anthropic", model="claude-sonnet-4-5-20250929", api_key="cached", base_url=""
        )
        _cache["query"] = (expected, time.monotonic())

        mock_db = AsyncMock()
        cfg = await resolve_llm_config("query", mock_db)
        assert cfg.api_key == "cached"
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_expired_cache_queries_db(self) -> None:
        stale = ResolvedLLMConfig(provider="anthropic", model="old", api_key="stale", base_url="")
        _cache["query"] = (stale, time.monotonic() - 60)  # expired

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = {
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "fresh",
            "base_url": "",
        }
        mock_db.execute.return_value = mock_result

        cfg = await resolve_llm_config("query", mock_db)
        assert cfg.api_key == "fresh"
        mock_db.execute.assert_called_once()


class TestClearCache:
    def test_clear_cache(self) -> None:
        _cache["query"] = (
            ResolvedLLMConfig(provider="x", model="x", api_key="x", base_url=""),
            time.monotonic(),
        )
        assert len(_cache) == 1
        clear_cache()
        assert len(_cache) == 0


class TestResolveSyncVariant:
    @patch("app.llm_config.resolver._resolve_from_env")
    def test_returns_db_config(self, mock_env: MagicMock) -> None:
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.mappings.return_value.first.return_value = {
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sync-key",
            "base_url": "",
        }

        cfg = resolve_llm_config_sync("query", mock_engine)
        assert cfg.provider == "openai"
        assert cfg.api_key == "sync-key"
        mock_env.assert_not_called()

    @patch("app.llm_config.resolver._resolve_from_env")
    def test_falls_back_to_env_on_no_row(self, mock_env: MagicMock) -> None:
        mock_env.return_value = ResolvedLLMConfig(
            provider="anthropic", model="fallback", api_key="env-key", base_url=""
        )
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.mappings.return_value.first.return_value = None

        cfg = resolve_llm_config_sync("analysis", mock_engine)
        assert cfg.model == "fallback"

    def test_raises_on_db_error(self) -> None:
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception("DB down")

        with pytest.raises(Exception, match="DB down"):
            resolve_llm_config_sync("query", mock_engine)
