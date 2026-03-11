"""Tests for Qdrant payload propagation in hot doc detection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.analysis.schemas import (
    DocumentSentimentResult,
    HotDocSignals,
    SentimentDimensions,
)
from app.llm_config.schemas import ResolvedLLMConfig


def test_set_payload_called_with_correct_args():
    """Qdrant set_payload is called with hot_doc_score and doc_id filter."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    mock_qdrant = MagicMock()
    mock_point = MagicMock()
    mock_point.payload = {"chunk_text": "Test text", "chunk_index": 0}
    mock_point.id = "point-1"
    mock_qdrant.scroll.return_value = ([mock_point], None)

    # Mock the document-type query result
    mock_doc_row = MagicMock()
    mock_doc_row.document_type = "document"
    mock_doc_row.metadata_ = None
    mock_doc_result = MagicMock()
    mock_doc_result.first.return_value = mock_doc_row
    mock_conn.execute.return_value = mock_doc_result

    sentiment_result = DocumentSentimentResult(
        sentiment=SentimentDimensions(
            positive=0.1,
            negative=0.2,
            pressure=0.8,
            opportunity=0.1,
            rationalization=0.05,
            intent=0.3,
            concealment=0.7,
        ),
        signals=HotDocSignals(
            admission_guilt=0.2,
            inappropriate_enthusiasm=0.0,
            deliberate_vagueness=0.4,
        ),
        hot_doc_score=0.72,
        summary="High pressure and concealment.",
    )

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
        mock_asyncio.run.return_value = sentiment_result

        from app.analysis.tasks import scan_document_sentiment

        scan_document_sentiment("doc-123", "matter-456")

    mock_qdrant.set_payload.assert_called_once()
    call_kwargs = mock_qdrant.set_payload.call_args
    # Verify collection name
    collection = call_kwargs.kwargs.get("collection_name")
    assert collection is not None
    # Verify payload contains hot_doc_score
    payload = call_kwargs.kwargs.get("payload")
    assert payload is not None
    assert "hot_doc_score" in payload
    assert payload["hot_doc_score"] == 0.72
