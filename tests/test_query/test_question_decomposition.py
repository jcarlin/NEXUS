"""Tests for T1-10: Explicit question decomposition."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.query.decomposer import (
    SubQuestion,
    _parse_decomposition,
    decompose_question,
    retrieve_for_sub_questions,
)


@pytest.fixture
def mock_llm():
    return AsyncMock()


@pytest.fixture
def mock_retriever():
    retriever = AsyncMock()
    retriever.retrieve_text = AsyncMock(
        return_value=[
            {"id": "chunk-1", "source_file": "doc.pdf", "page_number": 1, "chunk_text": "Evidence", "score": 0.9},
        ]
    )
    return retriever


class TestDecomposeQuestion:
    @pytest.mark.asyncio
    async def test_complex_question_decomposed(self, mock_llm):
        """Verify complex multi-part questions are decomposed into sub-questions."""
        mock_llm.complete = AsyncMock(
            return_value=json.dumps(
                {
                    "is_complex": True,
                    "sub_questions": [
                        {"question": "Who knew about the deal?", "aspect": "who", "reasoning": "Identifies the actors"},
                        {
                            "question": "When did they learn about it?",
                            "aspect": "when",
                            "reasoning": "Establishes timeline",
                        },
                        {
                            "question": "What actions did they take?",
                            "aspect": "what action",
                            "reasoning": "Determines consequences",
                        },
                    ],
                }
            )
        )

        result = await decompose_question(
            "Who knew about the deal, when did they learn, and what did they do about it?",
            mock_llm,
        )

        assert result.is_complex is True
        assert len(result.sub_questions) == 3
        assert all(isinstance(sq, SubQuestion) for sq in result.sub_questions)

    @pytest.mark.asyncio
    async def test_simple_question_not_decomposed(self, mock_llm):
        """Verify simple questions return is_complex=False."""
        mock_llm.complete = AsyncMock(
            return_value=json.dumps(
                {
                    "is_complex": False,
                    "sub_questions": [],
                }
            )
        )

        result = await decompose_question("Who is John Smith?", mock_llm)
        assert result.is_complex is False
        assert len(result.sub_questions) == 0

    @pytest.mark.asyncio
    async def test_handles_llm_failure(self, mock_llm):
        """Verify graceful degradation on LLM failure."""
        mock_llm.complete = AsyncMock(side_effect=Exception("API error"))

        result = await decompose_question("test query", mock_llm)
        assert result.is_complex is False
        assert len(result.sub_questions) == 0


class TestRetrieveForSubQuestions:
    @pytest.mark.asyncio
    async def test_parallel_retrieval(self, mock_retriever):
        """Verify concurrent retrieval for each sub-question."""
        sub_questions = [
            SubQuestion(question="Who knew?", aspect="who", reasoning="r1"),
            SubQuestion(question="When?", aspect="when", reasoning="r2"),
        ]

        results = await retrieve_for_sub_questions(
            sub_questions,
            mock_retriever,
            filters={"matter_id": "test-matter"},
        )

        assert mock_retriever.retrieve_text.call_count == 2
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_deduplicates_results(self, mock_retriever):
        """Verify results are deduplicated across sub-questions."""
        mock_retriever.retrieve_text = AsyncMock(
            return_value=[
                {"id": "chunk-1", "score": 0.9, "source_file": "doc.pdf"},
            ]
        )

        sub_questions = [
            SubQuestion(question="Q1", aspect="a1", reasoning="r1"),
            SubQuestion(question="Q2", aspect="a2", reasoning="r2"),
        ]

        results = await retrieve_for_sub_questions(sub_questions, mock_retriever)
        assert len(results) == 1  # Deduped to 1


class TestParseDecomposition:
    def test_parses_valid_json(self):
        raw = json.dumps(
            {
                "is_complex": True,
                "sub_questions": [
                    {"question": "Q1", "aspect": "a1", "reasoning": "r1"},
                ],
            }
        )
        result = _parse_decomposition(raw)
        assert result.is_complex is True
        assert len(result.sub_questions) == 1

    def test_parses_json_in_text(self):
        raw = 'Here is the result:\n{"is_complex": false, "sub_questions": []}\n'
        result = _parse_decomposition(raw)
        assert result.is_complex is False

    def test_returns_default_for_garbage(self):
        result = _parse_decomposition("not json at all")
        assert result.is_complex is False
        assert len(result.sub_questions) == 0
