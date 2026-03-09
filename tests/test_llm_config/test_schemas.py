"""Tests for LLM config Pydantic schemas."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.llm_config.schemas import (
    LLMProviderCreate,
    LLMProviderType,
    LLMTier,
    LLMTierConfigSet,
    ResolvedLLMConfig,
)


class TestLLMProviderType:
    def test_enum_values(self) -> None:
        assert LLMProviderType.ANTHROPIC == "anthropic"
        assert LLMProviderType.OPENAI == "openai"
        assert LLMProviderType.GEMINI == "gemini"
        assert LLMProviderType.OLLAMA == "ollama"

    def test_enum_count(self) -> None:
        assert len(LLMProviderType) == 4


class TestLLMTier:
    def test_enum_values(self) -> None:
        assert LLMTier.QUERY == "query"
        assert LLMTier.ANALYSIS == "analysis"
        assert LLMTier.INGESTION == "ingestion"

    def test_enum_count(self) -> None:
        assert len(LLMTier) == 3


class TestLLMProviderCreate:
    def test_valid(self) -> None:
        p = LLMProviderCreate(provider="anthropic", label="My Anthropic")
        assert p.provider == LLMProviderType.ANTHROPIC
        assert p.label == "My Anthropic"
        assert p.api_key == ""
        assert p.base_url == ""

    def test_label_min_length(self) -> None:
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            LLMProviderCreate(provider="anthropic", label="")

    def test_label_max_length(self) -> None:
        with pytest.raises(ValidationError):
            LLMProviderCreate(provider="anthropic", label="x" * 101)

    def test_invalid_provider(self) -> None:
        with pytest.raises(ValidationError):
            LLMProviderCreate(provider="invalid", label="Test")


class TestLLMTierConfigSet:
    def test_valid(self) -> None:
        t = LLMTierConfigSet(provider_id=uuid4(), model="gpt-4o")
        assert t.model == "gpt-4o"

    def test_model_min_length(self) -> None:
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            LLMTierConfigSet(provider_id=uuid4(), model="")

    def test_model_max_length(self) -> None:
        with pytest.raises(ValidationError):
            LLMTierConfigSet(provider_id=uuid4(), model="x" * 101)


class TestResolvedLLMConfig:
    def test_construction(self) -> None:
        cfg = ResolvedLLMConfig(
            provider="anthropic",
            model="claude-sonnet-4-5-20250929",
            api_key="sk-test",
            base_url="",
        )
        assert cfg.provider == "anthropic"
        assert cfg.model == "claude-sonnet-4-5-20250929"
        assert cfg.api_key == "sk-test"
        assert cfg.base_url == ""
