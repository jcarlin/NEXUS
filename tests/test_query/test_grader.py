"""Tests for the CRAG-style retrieval grading module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.query.grader import (
    _parse_grading_response,
    _tokenize,
    grade_retrieval,
    heuristic_relevance,
)


class TestHeuristicRelevance:
    """Tests for heuristic_relevance."""

    def test_high_keyword_overlap(self):
        """Query and chunk sharing many terms should score high."""
        query = "John Smith payment Acme Corporation March 2024"
        chunk = "John Smith confirmed the payment to Acme Corporation on March 15, 2024."
        score = heuristic_relevance(query, chunk, qdrant_score=0.8)
        assert score > 0.6

    def test_no_keyword_overlap(self):
        """Query and chunk with no shared terms should rely on qdrant_score."""
        query = "merger agreement timeline"
        chunk = "The weather was sunny and warm outside the courthouse."
        score = heuristic_relevance(query, chunk, qdrant_score=0.2)
        assert score < 0.3

    def test_qdrant_score_dominant(self):
        """Qdrant score should be the primary signal (60% weight)."""
        query = "financial transactions"
        chunk = "Random unrelated text."
        score_high_qdrant = heuristic_relevance(query, chunk, qdrant_score=0.9)
        score_low_qdrant = heuristic_relevance(query, chunk, qdrant_score=0.1)
        assert score_high_qdrant > score_low_qdrant

    def test_empty_query(self):
        """Empty query should return qdrant_score directly."""
        score = heuristic_relevance("", "Some chunk text.", qdrant_score=0.7)
        assert score == 0.7

    def test_score_in_range(self):
        """Score should always be in [0.0, 1.0]."""
        score = heuristic_relevance("test query", "test text", qdrant_score=1.0)
        assert 0.0 <= score <= 1.0


class TestGradeRetrieval:
    """Tests for the grade_retrieval function."""

    @pytest.mark.asyncio
    async def test_llm_grading_triggered_when_low_confidence(self):
        """Median heuristic < threshold should trigger LLM grading."""
        results = [
            {"chunk_text": "Unrelated content.", "score": 0.1},
            {"chunk_text": "More unrelated text.", "score": 0.15},
            {"chunk_text": "Still not relevant.", "score": 0.12},
        ]

        llm = MagicMock()
        llm.complete = AsyncMock(return_value="1: 2\n2: 1\n3: 3")

        _, confidence, triggered = await grade_retrieval(
            query="John Smith payment",
            results=results,
            llm=llm,
            confidence_threshold=0.5,
        )

        assert triggered is True
        assert llm.complete.call_count == 1

    @pytest.mark.asyncio
    async def test_llm_grading_skipped_when_high_confidence(self):
        """Median heuristic > threshold should NOT trigger LLM grading."""
        results = [
            {"chunk_text": "John Smith made a payment.", "score": 0.9},
            {"chunk_text": "Smith payment to Acme Corp.", "score": 0.85},
        ]

        llm = MagicMock()
        llm.complete = AsyncMock()

        _, confidence, triggered = await grade_retrieval(
            query="John Smith payment",
            results=results,
            llm=llm,
            confidence_threshold=0.5,
        )

        assert triggered is False
        assert llm.complete.call_count == 0

    @pytest.mark.asyncio
    async def test_grade_node_disabled(self):
        """When no LLM provided, only heuristic scoring is done."""
        results = [
            {"chunk_text": "Some text.", "score": 0.3},
        ]

        _, confidence, triggered = await grade_retrieval(
            query="test query",
            results=results,
            llm=None,
            confidence_threshold=0.5,
        )

        assert triggered is False
        assert "relevance_score" in results[0]

    @pytest.mark.asyncio
    async def test_empty_results(self):
        """Empty results should return confidence 1.0."""
        results, confidence, triggered = await grade_retrieval(query="test", results=[], llm=None)
        assert confidence == 1.0
        assert triggered is False

    @pytest.mark.asyncio
    async def test_llm_failure_graceful(self):
        """LLM failure should fall back to heuristic scores."""
        results = [
            {"chunk_text": "Some text.", "score": 0.1},
        ]

        llm = MagicMock()
        llm.complete = AsyncMock(side_effect=RuntimeError("API Error"))

        _, confidence, triggered = await grade_retrieval(
            query="test query",
            results=results,
            llm=llm,
            confidence_threshold=0.5,
        )

        # Should trigger but fail gracefully
        assert triggered is True
        assert "relevance_score" in results[0]


class TestParseGradingResponse:
    """Tests for _parse_grading_response."""

    def test_colon_format(self):
        result = _parse_grading_response("1: 8\n2: 3\n3: 9", 3)
        assert result == [8.0, 3.0, 9.0]

    def test_dot_format(self):
        result = _parse_grading_response("1. 7\n2. 5", 2)
        assert result == [7.0, 5.0]

    def test_missing_numbers(self):
        result = _parse_grading_response("1: 8\n3: 6", 3)
        assert result[0] == 8.0
        assert result[1] is None  # Missing [2]
        assert result[2] == 6.0

    def test_empty_response(self):
        result = _parse_grading_response("", 3)
        assert result == [None, None, None]


class TestTokenize:
    """Tests for the _tokenize helper."""

    def test_basic_tokenization(self):
        tokens = _tokenize("John Smith made a payment to Acme Corp")
        assert "john" in tokens
        assert "smith" in tokens
        assert "payment" in tokens
        assert "acme" in tokens
        # Stopwords removed
        assert "a" not in tokens
        assert "to" not in tokens

    def test_empty_string(self):
        assert _tokenize("") == []
