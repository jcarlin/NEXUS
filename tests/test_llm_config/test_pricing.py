"""Tests for LLM model pricing lookup."""

from __future__ import annotations

from app.llm_config.pricing import get_model_pricing


class TestGetModelPricing:
    def test_known_model_exact(self) -> None:
        inp, out = get_model_pricing("gpt-4o")
        assert inp == 2.50
        assert out == 10.0

    def test_known_anthropic_model(self) -> None:
        inp, out = get_model_pricing("claude-sonnet-4-5-20250929")
        assert inp == 3.0
        assert out == 15.0

    def test_unknown_model_returns_zero(self) -> None:
        assert get_model_pricing("totally-unknown-model") == (0.0, 0.0)

    def test_ollama_returns_zero(self) -> None:
        assert get_model_pricing("ollama") == (0.0, 0.0)

    def test_fuzzy_match_substring(self) -> None:
        # "gpt-4o" is a key and is a substring of "gpt-4o-2024-08-06"
        inp, out = get_model_pricing("gpt-4o-2024-08-06")
        assert inp > 0

    def test_fuzzy_match_key_in_model(self) -> None:
        # "gemini-2.0-flash" is a key and substring
        inp, out = get_model_pricing("gemini-2.0-flash")
        assert inp == 0.10
        assert out == 0.40
