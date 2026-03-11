"""Tests for scan_document_sentiment Celery task."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.analysis.schemas import (
    DocumentSentimentResult,
    HotDocSignals,
    SentimentDimensions,
)
from app.llm_config.schemas import ResolvedLLMConfig


@pytest.fixture
def mock_sentiment_result():
    return DocumentSentimentResult(
        sentiment=SentimentDimensions(
            positive=0.1,
            negative=0.3,
            pressure=0.7,
            opportunity=0.2,
            rationalization=0.1,
            intent=0.4,
            concealment=0.6,
        ),
        signals=HotDocSignals(
            admission_guilt=0.3,
            inappropriate_enthusiasm=0.0,
            deliberate_vagueness=0.5,
        ),
        hot_doc_score=0.65,
        summary="Pressure and concealment detected.",
    )


def _make_mock_engine():
    """Build a mock sync engine with working context-manager connect()."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    # Mock the document-type query result
    mock_doc_row = MagicMock()
    mock_doc_row.document_type = "document"
    mock_doc_row.metadata_ = None
    mock_doc_result = MagicMock()
    mock_doc_result.first.return_value = mock_doc_row
    mock_conn.execute.return_value = mock_doc_result

    return mock_engine, mock_conn


def _make_mock_qdrant():
    """Build a mock Qdrant client with a single chunk point."""
    mock_qdrant = MagicMock()
    mock_point = MagicMock()
    mock_point.payload = {"chunk_text": "Test document text", "chunk_index": 0}
    mock_point.id = "point-1"
    mock_qdrant.scroll.return_value = ([mock_point], None)
    mock_qdrant.set_payload.return_value = None
    return mock_qdrant


def test_task_stores_scores_in_postgres(mock_sentiment_result):
    """scan_document_sentiment stores all scores in documents table."""
    mock_engine, mock_conn = _make_mock_engine()
    mock_qdrant = _make_mock_qdrant()

    mock_scorer_instance = MagicMock()

    mock_settings = MagicMock()
    mock_settings.qdrant_url = "http://localhost:6333"
    mock_settings.anthropic_api_key = "test"
    mock_settings.llm_model = "test-model"
    mock_settings.llm_provider = "anthropic"

    mock_llm_config = ResolvedLLMConfig(provider="anthropic", model="test-model", api_key="test", base_url="")

    with (
        patch("app.analysis.tasks._get_sync_engine", return_value=mock_engine),
        patch("qdrant_client.QdrantClient", return_value=mock_qdrant),
        patch("app.config.Settings", return_value=mock_settings),
        patch("app.analysis.sentiment.SentimentScorer", return_value=mock_scorer_instance),
        patch("app.analysis.tasks.asyncio") as mock_asyncio,
        patch(
            "app.llm_config.resolver.resolve_llm_config_sync",
            return_value=mock_llm_config,
        ),
    ):
        mock_asyncio.run.return_value = mock_sentiment_result

        from app.analysis.tasks import scan_document_sentiment

        result = scan_document_sentiment("doc-123", "matter-456")

    assert result["status"] == "complete"
    # Verify UPDATE was called (at least 2 execute calls: doc_type query + UPDATE)
    assert mock_conn.execute.call_count >= 2


def test_task_calls_qdrant_set_payload(mock_sentiment_result):
    """scan_document_sentiment propagates scores to Qdrant via set_payload."""
    mock_engine, mock_conn = _make_mock_engine()
    mock_qdrant = _make_mock_qdrant()

    mock_settings = MagicMock()
    mock_settings.qdrant_url = "http://localhost:6333"
    mock_settings.anthropic_api_key = "test"
    mock_settings.llm_model = "test-model"
    mock_settings.llm_provider = "anthropic"

    mock_llm_config = ResolvedLLMConfig(provider="anthropic", model="test-model", api_key="test", base_url="")

    with (
        patch("app.analysis.tasks._get_sync_engine", return_value=mock_engine),
        patch("qdrant_client.QdrantClient", return_value=mock_qdrant),
        patch("app.config.Settings", return_value=mock_settings),
        patch("app.analysis.sentiment.SentimentScorer"),
        patch("app.analysis.tasks.asyncio") as mock_asyncio,
        patch(
            "app.llm_config.resolver.resolve_llm_config_sync",
            return_value=mock_llm_config,
        ),
    ):
        mock_asyncio.run.return_value = mock_sentiment_result

        from app.analysis.tasks import scan_document_sentiment

        scan_document_sentiment("doc-123", "matter-456")

    mock_qdrant.set_payload.assert_called_once()
    call_kwargs = mock_qdrant.set_payload.call_args
    payload = call_kwargs.kwargs.get("payload")
    assert payload is not None
    assert "hot_doc_score" in payload
