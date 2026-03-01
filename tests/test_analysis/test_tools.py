"""Tests for sentiment/hot doc query tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_sentiment_search_validates_dimension():
    """sentiment_search rejects invalid dimension parameter."""
    from app.query.tools import sentiment_search

    result = await sentiment_search.ainvoke({"query": "test", "dimension": "invalid_dim", "state": {}})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "invalid_dim" in parsed["error"]


@pytest.mark.asyncio
async def test_hot_doc_search_orders_by_score():
    """hot_doc_search returns results ordered by hot_doc_score DESC."""
    from app.query.tools import hot_doc_search

    mock_row_1 = MagicMock()
    mock_row_1._mapping = {
        "id": "doc-1",
        "filename": "a.pdf",
        "document_type": "document",
        "hot_doc_score": 0.9,
        "sentiment_pressure": 0.8,
        "sentiment_concealment": 0.7,
        "sentiment_intent": 0.6,
    }
    mock_row_2 = MagicMock()
    mock_row_2._mapping = {
        "id": "doc-2",
        "filename": "b.pdf",
        "document_type": "email",
        "hot_doc_score": 0.7,
        "sentiment_pressure": 0.5,
        "sentiment_concealment": 0.4,
        "sentiment_intent": 0.3,
    }

    mock_result = MagicMock()
    mock_result.all.return_value = [mock_row_1, mock_row_2]

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    with patch("app.dependencies.get_db", mock_get_db):
        result = await hot_doc_search.ainvoke(
            {
                "min_score": 0.6,
                "state": {"_filters": {"matter_id": "test-matter"}},
            }
        )

    parsed = json.loads(result)
    assert len(parsed) == 2
    assert parsed[0]["hot_doc_score"] == 0.9
    assert parsed[1]["hot_doc_score"] == 0.7


@pytest.mark.asyncio
async def test_context_gap_search_filters_by_type():
    """context_gap_search supports gap_type filter."""
    from app.query.tools import context_gap_search

    mock_row = MagicMock()
    mock_row._mapping = {
        "id": "doc-1",
        "filename": "email.eml",
        "document_type": "email",
        "context_gap_score": 0.8,
        "context_gaps": [{"gap_type": "missing_attachment", "evidence": "See attached", "severity": 0.9}],
    }
    mock_result = MagicMock()
    mock_result.all.return_value = [mock_row]

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    with patch("app.dependencies.get_db", mock_get_db):
        result = await context_gap_search.ainvoke(
            {
                "gap_type": "missing_attachment",
                "state": {"_filters": {"matter_id": "test-matter"}},
            }
        )

    parsed = json.loads(result)
    assert len(parsed) == 1
    # Verify the execute call included gap_filter in params
    mock_db.execute.assert_called_once()
    call_args = mock_db.execute.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args.kwargs.get("params", {})
    assert "gap_filter" in params
