"""Tests for the cross-encoder reranker module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.query.reranker import Reranker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_results(n: int, text_key: str = "chunk_text") -> list[dict]:
    """Generate N fake retrieval results."""
    return [
        {
            "id": f"p{i}",
            "score": 0.5,
            text_key: f"passage text {i}",
            "source_file": f"doc{i}.pdf",
            "page_number": i,
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_reranker_lazy_loads_model():
    """Model should be None until first rerank call."""
    reranker = Reranker(model_name="test-model")
    assert reranker._model is None


def test_reranker_returns_sorted_by_score():
    """Results should be sorted by cross-encoder score descending."""
    reranker = Reranker()

    mock_model = MagicMock()
    mock_model.predict.return_value = [0.9, 0.1, 0.5]
    reranker._model = mock_model

    results = _make_results(3)
    ranked = reranker.rerank("test query", results, top_n=10)

    scores = [r["score"] for r in ranked]
    assert scores == [0.9, 0.5, 0.1]


def test_reranker_respects_top_n():
    """Should return at most top_n results."""
    reranker = Reranker()

    mock_model = MagicMock()
    mock_model.predict.return_value = [float(i) / 10 for i in range(10)]
    reranker._model = mock_model

    results = _make_results(10)
    ranked = reranker.rerank("test query", results, top_n=3)

    assert len(ranked) == 3


def test_reranker_handles_empty_results():
    """Empty input should return empty output without loading the model."""
    reranker = Reranker()
    ranked = reranker.rerank("test query", [], top_n=10)

    assert ranked == []
    assert reranker._model is None  # Model never loaded


def test_reranker_builds_correct_pairs():
    """Should pass [[query, passage], ...] pairs to model.predict."""
    reranker = Reranker()

    mock_model = MagicMock()
    mock_model.predict.return_value = [0.8, 0.6]
    reranker._model = mock_model

    results = _make_results(2)
    reranker.rerank("my query", results, top_n=10)

    pairs = mock_model.predict.call_args[0][0]
    assert len(pairs) == 2
    assert pairs[0] == ["my query", "passage text 0"]
    assert pairs[1] == ["my query", "passage text 1"]


def test_reranker_updates_score_field():
    """Each result dict should get its score overwritten with the cross-encoder score."""
    reranker = Reranker()

    mock_model = MagicMock()
    mock_model.predict.return_value = [0.95, 0.3]
    reranker._model = mock_model

    results = _make_results(2)
    ranked = reranker.rerank("query", results, top_n=10)

    assert ranked[0]["score"] == 0.95
    assert ranked[1]["score"] == 0.3


def test_reranker_uses_custom_text_key():
    """Should use the specified text_key to build pairs."""
    reranker = Reranker()

    mock_model = MagicMock()
    mock_model.predict.return_value = [0.7]
    reranker._model = mock_model

    results = [{"id": "p0", "score": 0.5, "text": "custom passage", "source_file": "doc.pdf"}]
    reranker.rerank("query", results, top_n=10, text_key="text")

    pairs = mock_model.predict.call_args[0][0]
    assert pairs[0][1] == "custom passage"


def test_reranker_model_loaded_only_once():
    """CrossEncoder should be instantiated only once across multiple calls."""
    with patch("sentence_transformers.CrossEncoder") as MockCE:
        mock_instance = MagicMock()
        mock_instance.predict.return_value = [0.5]
        MockCE.return_value = mock_instance

        reranker = Reranker(model_name="test-model")

        results1 = _make_results(1)
        results2 = _make_results(1)
        reranker.rerank("q1", results1, top_n=10)
        reranker.rerank("q2", results2, top_n=10)

        # Model should have been instantiated exactly once
        MockCE.assert_called_once_with("test-model")
        assert mock_instance.predict.call_count == 2
