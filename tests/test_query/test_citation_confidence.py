"""Tests for T1-9: Citation confidence scores via VerificationJudgment."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    return llm


@pytest.fixture
def mock_retriever():
    retriever = AsyncMock()
    retriever.retrieve_text = AsyncMock(
        return_value=[
            {"source_file": "doc.pdf", "page_number": 1, "chunk_text": "Evidence text here"},
        ]
    )
    return retriever


@pytest.mark.asyncio
async def test_verify_single_claim_extracts_confidence(mock_llm, mock_retriever):
    """Verify that structured VerificationJudgment populates grounding_score."""
    import json

    from app.query.nodes import _verify_single_claim

    # Mock LLM to return structured JSON judgment
    mock_llm.complete = AsyncMock(
        return_value=json.dumps(
            {
                "supported": True,
                "confidence": 0.92,
                "rationale": "The claim is directly supported by the document.",
            }
        )
    )

    claim = {
        "claim_text": "The agreement was signed in January 2020.",
        "filename": "agreement.pdf",
        "page_number": 5,
        "grounding_score": 0.5,  # Original decomposition score
    }

    result = await _verify_single_claim(mock_llm, mock_retriever, claim, filters=None, exclude_privilege=[])

    assert result["verification_status"] == "verified"
    assert result["grounding_score"] == 0.92  # Updated from verification


@pytest.mark.asyncio
async def test_verify_single_claim_fallback_on_parse_failure(mock_llm, mock_retriever):
    """Verify string heuristic fallback when structured parsing fails."""
    from app.query.nodes import _verify_single_claim

    # Mock LLM to return non-JSON response
    mock_llm.complete = AsyncMock(return_value="Yes, this claim is supported by the evidence.")

    claim = {
        "claim_text": "The meeting occurred on March 5.",
        "filename": "minutes.pdf",
        "page_number": 2,
        "grounding_score": 0.6,
    }

    result = await _verify_single_claim(mock_llm, mock_retriever, claim, filters=None, exclude_privilege=[])

    # Fallback heuristic: "supported" in response → verified
    assert result["verification_status"] == "verified"


@pytest.mark.asyncio
async def test_verify_single_claim_flagged_when_unsupported(mock_llm, mock_retriever):
    """Verify claims are flagged when evidence doesn't support them."""
    import json

    from app.query.nodes import _verify_single_claim

    mock_llm.complete = AsyncMock(
        return_value=json.dumps(
            {
                "supported": False,
                "confidence": 0.2,
                "rationale": "No evidence found for this claim.",
            }
        )
    )

    claim = {
        "claim_text": "The contract was worth $50 million.",
        "filename": "contract.pdf",
        "page_number": 1,
        "grounding_score": 0.8,
    }

    result = await _verify_single_claim(mock_llm, mock_retriever, claim, filters=None, exclude_privilege=[])

    assert result["verification_status"] == "flagged"
    assert result["grounding_score"] == 0.2


@pytest.mark.asyncio
async def test_grounding_score_updated_from_verification(mock_llm, mock_retriever):
    """Verify that grounding_score is updated by verification, not kept from decomposition."""
    import json

    from app.query.nodes import _verify_single_claim

    mock_llm.complete = AsyncMock(
        return_value=json.dumps(
            {
                "supported": True,
                "confidence": 0.75,
                "rationale": "Partially supported.",
            }
        )
    )

    claim = {
        "claim_text": "Test claim",
        "filename": "test.pdf",
        "page_number": 1,
        "grounding_score": 0.99,  # High decomposition score
    }

    result = await _verify_single_claim(mock_llm, mock_retriever, claim, filters=None, exclude_privilege=[])

    # Score should be overwritten by verification confidence, not kept at 0.99
    assert result["grounding_score"] == 0.75
