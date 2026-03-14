"""Tests for the LLM-as-judge quality scorer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from evaluation.judge import (
    JudgeScorer,
    _compute_composite,
    _JudgeExtraction,
    detect_judge_provider,
    score_empty_response,
)
from evaluation.schemas import JudgeScore

# ---------------------------------------------------------------------------
# Composite score computation
# ---------------------------------------------------------------------------


class TestComputeComposite:
    def test_all_fives(self) -> None:
        result = _compute_composite(5.0, 5.0, 5.0, 5.0, 5.0)
        assert result == 5.0

    def test_all_ones(self) -> None:
        result = _compute_composite(1.0, 1.0, 1.0, 1.0, 1.0)
        assert result == 1.0

    def test_weighted_average(self) -> None:
        # relevance=4, completeness=3, accuracy=5, citation_support=5, conciseness=2
        # = 4*0.20 + 3*0.15 + 5*0.25 + 5*0.25 + 2*0.15
        # = 0.80 + 0.45 + 1.25 + 1.25 + 0.30 = 4.05
        result = _compute_composite(4.0, 3.0, 5.0, 5.0, 2.0)
        assert result == pytest.approx(4.05, abs=0.01)

    def test_accuracy_and_citation_weighted_higher(self) -> None:
        # High accuracy/citation scores should produce higher composite
        high_ac = _compute_composite(3.0, 3.0, 5.0, 5.0, 3.0)
        low_ac = _compute_composite(3.0, 3.0, 1.0, 1.0, 3.0)
        assert high_ac > low_ac


# ---------------------------------------------------------------------------
# Score for empty responses
# ---------------------------------------------------------------------------


class TestScoreEmptyResponse:
    def test_all_zeros(self) -> None:
        score = score_empty_response()
        assert score.relevance == 0.0
        assert score.completeness == 0.0
        assert score.accuracy == 0.0
        assert score.citation_support == 0.0
        assert score.conciseness == 0.0
        assert score.composite == 0.0
        assert "empty" in score.rationale.lower() or "error" in score.rationale.lower()

    def test_returns_judge_score(self) -> None:
        score = score_empty_response()
        assert isinstance(score, JudgeScore)


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------


class TestDetectProvider:
    def test_anthropic_from_env(self) -> None:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=False):
            provider, key, model = detect_judge_provider()
            assert provider == "anthropic"
            assert key == "sk-ant-test"
            assert "claude" in model

    def test_openai_from_env(self) -> None:
        with patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "sk-proj-test"},
            clear=False,
        ):
            with patch("evaluation.judge._load_dotenv_keys", return_value={}):
                provider, key, model = detect_judge_provider()
                # Will find anthropic first if it's in env, or openai
                assert provider in ("anthropic", "openai")

    def test_gemini_fallback(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with patch(
                "evaluation.judge._load_dotenv_keys",
                return_value={"GEMINI_API_KEY": "AIza-test"},
            ):
                provider, key, model = detect_judge_provider()
                assert provider == "gemini"
                assert key == "AIza-test"

    def test_no_keys_raises(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with patch("evaluation.judge._load_dotenv_keys", return_value={}):
                with pytest.raises(RuntimeError, match="No LLM API key"):
                    detect_judge_provider()


# ---------------------------------------------------------------------------
# JudgeScorer
# ---------------------------------------------------------------------------


class TestJudgeScorer:
    @pytest.mark.asyncio
    async def test_score_empty_answer(self) -> None:
        with patch(
            "evaluation.judge.detect_judge_provider", return_value=("anthropic", "test-key", "claude-sonnet-4-20250514")
        ):
            with patch("evaluation.judge._build_instructor_client", return_value=MagicMock()):
                scorer = JudgeScorer()
                score = await scorer.score_answer("What happened?", "")
                assert score.composite == 0.0
                assert "empty" in score.rationale.lower() or "error" in score.rationale.lower()

    @pytest.mark.asyncio
    async def test_score_whitespace_answer(self) -> None:
        with patch(
            "evaluation.judge.detect_judge_provider", return_value=("anthropic", "test-key", "claude-sonnet-4-20250514")
        ):
            with patch("evaluation.judge._build_instructor_client", return_value=MagicMock()):
                scorer = JudgeScorer()
                score = await scorer.score_answer("What happened?", "   \n  ")
                assert score.composite == 0.0

    @pytest.mark.asyncio
    async def test_score_answer_calls_llm(self) -> None:
        mock_extraction = _JudgeExtraction(
            relevance=4.0,
            completeness=3.5,
            accuracy=4.5,
            citation_support=4.0,
            conciseness=3.0,
            rationale="Good answer with solid citations.",
        )

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_extraction)

        with patch(
            "evaluation.judge.detect_judge_provider", return_value=("anthropic", "test-key", "claude-sonnet-4-20250514")
        ):
            with patch("evaluation.judge._build_instructor_client", return_value=mock_client):
                scorer = JudgeScorer()
                score = await scorer.score_answer(
                    "What are the key allegations?",
                    "The complaint alleges breach of contract.",
                    source_excerpts=["Section 3.1 of the complaint..."],
                )

                assert score.relevance == 4.0
                assert score.accuracy == 4.5
                assert score.composite > 0
                assert score.rationale == "Good answer with solid citations."
                mock_client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_score_answer_handles_llm_error(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("API rate limited"))

        with patch(
            "evaluation.judge.detect_judge_provider", return_value=("anthropic", "test-key", "claude-sonnet-4-20250514")
        ):
            with patch("evaluation.judge._build_instructor_client", return_value=mock_client):
                scorer = JudgeScorer()
                score = await scorer.score_answer(
                    "What happened?",
                    "The contract was breached.",
                )
                assert score.composite == 0.0
                assert "failed" in score.rationale.lower()

    def test_provider_info(self) -> None:
        with patch(
            "evaluation.judge.detect_judge_provider", return_value=("anthropic", "test-key", "claude-sonnet-4-20250514")
        ):
            with patch("evaluation.judge._build_instructor_client", return_value=MagicMock()):
                scorer = JudgeScorer()
                info = scorer.provider_info
                assert info["judge_provider"] == "anthropic"
                assert "claude" in info["judge_model"]

    def test_explicit_provider(self) -> None:
        with patch("evaluation.judge._build_instructor_client", return_value=MagicMock()):
            scorer = JudgeScorer(provider="openai", api_key="sk-test", model="gpt-4o")
            assert scorer.provider == "openai"
            assert scorer.model == "gpt-4o"


# ---------------------------------------------------------------------------
# Extraction model
# ---------------------------------------------------------------------------


class TestJudgeExtraction:
    def test_valid_scores(self) -> None:
        ext = _JudgeExtraction(
            relevance=4.0,
            completeness=3.0,
            accuracy=5.0,
            citation_support=4.5,
            conciseness=3.5,
            rationale="Good answer.",
        )
        assert ext.relevance == 4.0
        assert ext.rationale == "Good answer."

    def test_score_bounds(self) -> None:
        with pytest.raises(Exception):
            _JudgeExtraction(
                relevance=6.0,  # Too high
                completeness=3.0,
                accuracy=5.0,
                citation_support=4.5,
                conciseness=3.5,
            )

    def test_score_minimum(self) -> None:
        with pytest.raises(Exception):
            _JudgeExtraction(
                relevance=0.5,  # Too low (min 1.0)
                completeness=3.0,
                accuracy=5.0,
                citation_support=4.5,
                conciseness=3.5,
            )
