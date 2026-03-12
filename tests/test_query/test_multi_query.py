"""Tests for T1-1: Multi-query expansion."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.query.multi_query import _parse_variants, expand_query


@pytest.fixture
def mock_llm():
    return AsyncMock()


class TestExpandQuery:
    @pytest.mark.asyncio
    async def test_generates_variants(self, mock_llm):
        """Verify expand_query returns the requested number of variants."""
        mock_llm.complete = AsyncMock(
            return_value=json.dumps(
                [
                    "What was Smith's awareness of the transaction?",
                    "Did Smith have knowledge of the agreement?",
                    "Was Smith informed about the deal terms?",
                ]
            )
        )

        variants = await expand_query("What did Smith know about the deal?", mock_llm, count=3)
        assert len(variants) == 3
        assert all(isinstance(v, str) for v in variants)

    @pytest.mark.asyncio
    async def test_uses_term_map(self, mock_llm):
        """Verify term_map is passed to the prompt."""
        mock_llm.complete = AsyncMock(
            return_value=json.dumps(
                [
                    "What was John Doe's awareness of Project Alpha?",
                ]
            )
        )

        await expand_query(
            "What did JD know about PA?",
            mock_llm,
            term_map={"jd": "John Doe", "pa": "Project Alpha"},
            count=1,
        )

        # Verify the prompt included the term map
        call_args = mock_llm.complete.call_args
        prompt_content = call_args[0][0][0]["content"]
        assert "John Doe" in prompt_content
        assert "Project Alpha" in prompt_content

    @pytest.mark.asyncio
    async def test_handles_llm_failure(self, mock_llm):
        """Verify graceful degradation when LLM fails."""
        mock_llm.complete = AsyncMock(side_effect=Exception("API error"))

        variants = await expand_query("test query", mock_llm)
        assert variants == []

    @pytest.mark.asyncio
    async def test_handles_unparseable_response(self, mock_llm):
        """Verify graceful degradation when LLM returns non-JSON."""
        mock_llm.complete = AsyncMock(return_value="I cannot generate variants for this query.")

        variants = await expand_query("test query", mock_llm)
        assert variants == []


class TestParseVariants:
    def test_parses_json_array(self):
        raw = '["variant 1 query here", "variant 2 query here"]'
        result = _parse_variants(raw)
        assert len(result) == 2

    def test_parses_json_in_text(self):
        raw = 'Here are the variants:\n["variant 1 query here", "variant 2 query here"]\n'
        result = _parse_variants(raw)
        assert len(result) == 2

    def test_filters_short_strings(self):
        raw = '["ok", "this is a real variant query"]'
        result = _parse_variants(raw)
        assert len(result) == 1  # "ok" is too short

    def test_returns_empty_for_garbage(self):
        result = _parse_variants("no json here at all")
        assert result == []
