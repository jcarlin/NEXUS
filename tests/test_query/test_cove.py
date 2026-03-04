"""Tests for the Chain-of-Verification (CoVe) citation verification node."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

from app.query.nodes import verify_citations


async def test_verify_citations_decomposes_and_verifies():
    """verify_citations decomposes claims and runs independent verification."""
    mock_llm = AsyncMock()
    # First call: decompose response into claims (JSON array)
    claims_json = json.dumps(
        [
            {
                "claim_text": "The contract was signed on January 5",
                "document_id": "doc-001",
                "filename": "contract.pdf",
                "page_number": 3,
                "excerpt": "Signed this 5th day of January",
                "grounding_score": 0.9,
            }
        ]
    )
    # Second call: judgment
    judgment_text = "This claim is supported by the evidence. Confidence: 0.95"

    mock_llm.complete.side_effect = [claims_json, judgment_text]

    mock_retriever = AsyncMock()
    mock_retriever.retrieve_text.return_value = [
        {
            "id": "v1",
            "source_file": "contract.pdf",
            "page_number": 3,
            "chunk_text": "Signed this 5th day of January 2024",
            "score": 0.88,
        }
    ]

    state = {
        "_skip_verification": False,
        "response": "The contract was signed on January 5 [Source: contract.pdf, page 3].",
        "source_documents": [
            {"filename": "contract.pdf", "page": 3, "chunk_text": "Signed this 5th day of January"},
        ],
        "_filters": {"matter_id": "test-matter"},
        "_exclude_privilege": [],
    }

    with (
        patch("app.dependencies.get_llm", return_value=mock_llm),
        patch("app.dependencies.get_retriever", return_value=mock_retriever),
    ):
        result = await verify_citations(state)

    assert "cited_claims" in result
    assert len(result["cited_claims"]) == 1
    assert result["cited_claims"][0]["verification_status"] == "verified"
    assert result["cited_claims"][0]["claim_text"] == "The contract was signed on January 5"


async def test_verify_citations_runs_claims_concurrently():
    """verify_citations uses asyncio.gather to verify claims in parallel."""
    # Track concurrent execution
    active_count = 0
    max_concurrent = 0

    async def mock_verify_single_claim(llm, retriever, claim, filters, exclude_privilege):
        nonlocal active_count, max_concurrent
        active_count += 1
        max_concurrent = max(max_concurrent, active_count)
        await asyncio.sleep(0.05)  # simulate I/O
        active_count -= 1
        return {**claim, "verification_status": "verified", "confidence": 0.9}

    claims = [{"claim_text": f"Claim {i}", "document_id": f"doc-{i}", "grounding_score": 0.8} for i in range(3)]
    claims_json = json.dumps(claims)

    mock_llm = AsyncMock()
    mock_llm.complete.return_value = claims_json
    mock_retriever = AsyncMock()

    state = {
        "response": "Some response with claims.",
        "source_documents": [],
        "_filters": {"matter_id": "test-matter"},
        "_exclude_privilege": [],
    }

    with (
        patch("app.dependencies.get_llm", return_value=mock_llm),
        patch("app.dependencies.get_retriever", return_value=mock_retriever),
        patch("app.query.nodes._verify_single_claim", side_effect=mock_verify_single_claim),
    ):
        result = await verify_citations(state)

    assert len(result["cited_claims"]) == 3
    # If claims ran concurrently, max_concurrent should be > 1
    assert max_concurrent > 1, f"Expected concurrent execution but max_concurrent was {max_concurrent}"


async def test_verify_citations_skips_fast_tier():
    """verify_citations returns empty claims immediately for fast-tier queries."""
    state = {
        "_skip_verification": True,
        "response": "Some response",
        "source_documents": [],
    }

    result = await verify_citations(state)

    assert result == {"cited_claims": []}
