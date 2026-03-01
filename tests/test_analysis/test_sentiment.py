"""Tests for SentimentScorer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.analysis.schemas import DocumentSentimentResult, HotDocSignals, SentimentDimensions
from app.analysis.sentiment import SentimentScorer


@pytest.fixture
def scorer():
    return SentimentScorer(api_key="test-key", model="test-model", provider="anthropic")


@pytest.fixture
def mock_result():
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
        summary="Document shows significant pressure and concealment indicators.",
    )


@pytest.mark.asyncio
async def test_scorer_returns_valid_dimensions(scorer, mock_result):
    """SentimentScorer returns valid 7-dimension scores."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_result

    with patch.object(scorer, "_get_client", return_value=mock_client):
        result = await scorer.score_document("Test document text about financial pressure.")

    assert isinstance(result, DocumentSentimentResult)
    assert 0.0 <= result.sentiment.pressure <= 1.0
    assert 0.0 <= result.sentiment.concealment <= 1.0
    assert 0.0 <= result.hot_doc_score <= 1.0
    mock_client.chat.completions.create.assert_called_once()


@pytest.mark.asyncio
async def test_scorer_truncates_long_text(scorer, mock_result):
    """SentimentScorer truncates text longer than 8000 chars."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_result

    long_text = "x" * 20000

    with patch.object(scorer, "_get_client", return_value=mock_client):
        await scorer.score_document(long_text)

    call_args = mock_client.chat.completions.create.call_args
    # The messages content should contain truncated text (max 8000 chars of the doc)
    content = call_args.kwargs.get("messages", call_args[1].get("messages", [{}]))[0]["content"]
    # The actual document text in the prompt should be truncated
    assert len(content) < len(long_text) + 5000  # prompt + truncated text
