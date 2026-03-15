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

    async def mock_verify_single_claim(llm, retriever, claim, filters, exclude_privilege, claim_vector=None):
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
    """verify_citations returns empty claims immediately for fast-tier queries with no sources."""
    state = {
        "_skip_verification": True,
        "response": "Some response",
        "source_documents": [],
    }

    result = await verify_citations(state)

    assert result == {"cited_claims": []}


async def test_verify_citations_extracts_citations_in_fast_tier():
    """verify_citations extracts citation markers [1], [2] and maps to source documents in fast-tier."""
    state = {
        "_skip_verification": True,
        "response": "The key parties are Alice [1] and Bob [2] from the contract.",
        "source_documents": [
            {
                "document_id": "doc-001",
                "filename": "contract.pdf",
                "page": 1,
                "chunk_text": "Alice and Bob are parties to this agreement",
            },
            {
                "document_id": "doc-002",
                "filename": "agreement.pdf",
                "page": 2,
                "chunk_text": "Bob is the second party to this agreement",
            },
        ],
    }

    result = await verify_citations(state)

    assert "cited_claims" in result
    cited_claims = result["cited_claims"]
    assert len(cited_claims) == 2  # Two citation markers found

    # First citation
    assert cited_claims[0]["document_id"] == "doc-001"
    assert cited_claims[0]["filename"] == "contract.pdf"
    assert cited_claims[0]["page_number"] == 1
    assert cited_claims[0]["verification_status"] == "unverified"
    assert cited_claims[0]["grounding_score"] == 1.0

    # Second citation
    assert cited_claims[1]["document_id"] == "doc-002"
    assert cited_claims[1]["filename"] == "agreement.pdf"
    assert cited_claims[1]["page_number"] == 2


def test_agentic_graph_parallel_post_processing():
    """verify_citations and generate_follow_ups both follow post_agent_extract."""
    from unittest.mock import MagicMock

    from app.query.graph import build_agentic_graph

    mock_settings = MagicMock()
    mock_settings.llm_model = "claude-sonnet-4-20250514"
    mock_settings.anthropic_api_key = "sk-test"

    # build_agentic_graph compiles the graph — inspect edges
    with patch("app.query.tools.INVESTIGATION_TOOLS", []):
        compiled = build_agentic_graph(mock_settings, checkpointer=None)

    # The compiled graph's underlying graph_data stores the edges.
    # Check that post_agent_extract fans out to both verify_citations and generate_follow_ups.
    graph = compiled.get_graph()
    post_extract_targets = {edge.target for edge in graph.edges if edge.source == "post_agent_extract"}
    assert "verify_citations" in post_extract_targets
    assert "generate_follow_ups" in post_extract_targets
