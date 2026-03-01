"""Tests for CompletenessAnalyzer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.analysis.completeness import CompletenessAnalyzer
from app.analysis.schemas import CompletenessResult, ContextGap, ContextGapType


@pytest.fixture
def analyzer():
    return CompletenessAnalyzer(api_key="test-key", model="test-model", provider="anthropic")


@pytest.fixture
def mock_result_with_gaps():
    return CompletenessResult(
        context_gap_score=0.7,
        gaps=[
            ContextGap(
                gap_type=ContextGapType.missing_attachment,
                evidence="See attached spreadsheet",
                severity=0.8,
            ),
            ContextGap(
                gap_type=ContextGapType.prior_conversation,
                evidence="As we discussed yesterday",
                severity=0.6,
            ),
        ],
        summary="Email references missing attachment and prior conversation.",
    )


@pytest.mark.asyncio
async def test_detects_missing_references(analyzer, mock_result_with_gaps):
    """CompletenessAnalyzer detects gaps in document context."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_result_with_gaps

    with patch.object(analyzer, "_get_client", return_value=mock_client):
        result = await analyzer.analyze("Please see the attached spreadsheet for details.")

    assert isinstance(result, CompletenessResult)
    assert result.context_gap_score > 0.0
    assert len(result.gaps) > 0
    assert any(g.gap_type == ContextGapType.missing_attachment for g in result.gaps)


@pytest.mark.asyncio
async def test_handles_thread_context(analyzer, mock_result_with_gaps):
    """CompletenessAnalyzer includes thread context in analysis."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_result_with_gaps

    with patch.object(analyzer, "_get_client", return_value=mock_client):
        await analyzer.analyze(
            "Yes, I agree with the approach.",
            thread_context="RE: Q3 Budget Review - Let's discuss the numbers.",
        )

    call_args = mock_client.chat.completions.create.call_args
    messages = call_args.kwargs.get("messages") or call_args[1].get("messages", [])
    content = messages[0]["content"]
    assert "Q3 Budget Review" in content
