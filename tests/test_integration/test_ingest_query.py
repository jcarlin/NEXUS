"""Integration tests: ingestion → query pipeline.

Tests that parse, chunk, embed, and retrieval stages work together correctly
when composed through the LangGraph pipeline.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingestion.chunker import TextChunker
from app.ingestion.parser import DocumentParser


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _base_state(query: str = "Who is John Doe?", **overrides) -> dict:
    state = {
        "messages": [],
        "thread_id": "test-thread",
        "user_id": "test-user",
        "original_query": query,
        "rewritten_query": "",
        "query_type": "",
        "text_results": [],
        "visual_results": [],
        "graph_results": [],
        "fused_context": [],
        "response": "",
        "source_documents": [],
        "follow_up_questions": [],
        "entities_mentioned": [],
        "_relevance": "",
        "_reformulated": False,
        "_filters": None,
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_parse_chunk_produces_valid_chunks():
    """Real parser + chunker on a .txt file should produce valid chunks."""
    parser = DocumentParser()
    chunker = TextChunker(max_tokens=50, overlap_tokens=10)

    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        # Write enough text to get multiple chunks at 50 tokens max
        f.write("This is a legal document about an investigation. " * 20)
        f.write("\n\nA new paragraph discusses financial transactions. " * 20)
        f.flush()
        tmp_path = Path(f.name)

    try:
        result = parser.parse(tmp_path, "test_doc.txt")
        assert result.text
        assert result.page_count >= 1

        chunks = chunker.chunk(result.text, metadata={"source_file": "test_doc.txt"})
        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk.text
            assert chunk.token_count > 0
            assert chunk.token_count <= 50 + 10  # max + overlap tolerance
            assert chunk.metadata["source_file"] == "test_doc.txt"
    finally:
        tmp_path.unlink(missing_ok=True)


async def test_full_pipeline_ingestion_to_retrieval(compiled_graph, mock_services):
    """parse → chunk → mock embed → mock Qdrant → retriever returns chunks."""
    # The compiled_graph has a mocked retriever that returns results.
    # Verify the full graph invocation produces a response with sources.
    state = _base_state()
    # Set up LLM to return classify → rewrite → synthesize → follow-ups
    mock_services["llm"].complete.side_effect = [
        "factual",          # classify
        "Who is John Doe?", # rewrite
        "Follow-up question one about John Doe and his activities\n"
        "Follow-up question two about related documents\n"
        "Follow-up question three about timeline of events",  # follow-ups
    ]

    result = await compiled_graph.ainvoke(state)

    assert result["response"]
    assert len(result["source_documents"]) > 0
    assert result["source_documents"][0]["filename"] == "doc.pdf"


async def test_ingest_query_cited_answer(compiled_graph, mock_services):
    """Full graph invocation should produce a response with source_documents."""
    mock_services["llm"].complete.side_effect = [
        "factual",
        "Tell me about John Doe",
        "What else is known about John Doe?\n"
        "Are there financial records?\n"
        "What is the timeline?",
    ]

    state = _base_state()
    result = await compiled_graph.ainvoke(state)

    assert "response" in result
    assert len(result["response"]) > 0
    assert "source_documents" in result
    assert isinstance(result["source_documents"], list)


async def test_query_pipeline_with_entity_enrichment(compiled_graph, mock_services):
    """graph_lookup should enrich graph_results with entity connections."""
    mock_services["llm"].complete.side_effect = [
        "factual",
        "Who is John Doe?",
        "Follow-up one about connections\nFollow-up two about records\nFollow-up three about timeline",
    ]

    # Make graph_service return connections for entities found in chunks
    mock_services["graph_service"].get_entity_connections.return_value = [
        {"source": "John Doe", "relationship_type": "WORKS_AT", "target": "Acme Corp"},
    ]

    state = _base_state()
    result = await compiled_graph.ainvoke(state)

    # graph_results should contain enrichment from graph_lookup
    assert len(result["graph_results"]) >= 1


async def test_query_pipeline_reformulation_path(compiled_graph, mock_services):
    """Low-score results should trigger reformulation and a second retrieve."""
    # Return low-score results on first call, then better ones on second
    call_count = 0

    async def retriever_side_effect(query, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (
                [{"id": "c1", "score": 0.1, "source_file": "doc.pdf", "page_number": 1, "chunk_text": "low relevance"}],
                [],
            )
        return (
            [{"id": "c2", "score": 0.8, "source_file": "doc2.pdf", "page_number": 2, "chunk_text": "high relevance"}],
            [],
        )

    mock_services["retriever"].retrieve_all.side_effect = retriever_side_effect
    mock_services["llm"].complete.side_effect = [
        "factual",                           # classify
        "Who is John Doe?",                  # rewrite
        "alternative query about John Doe",  # reformulate
        "Follow-up one\nFollow-up two\nFollow-up three",  # follow-ups
    ]

    state = _base_state()

    # Patch get_settings and get_reranker so the rerank node doesn't error
    with patch("app.dependencies.get_settings") as mock_settings, \
         patch("app.dependencies.get_reranker", return_value=None):
        settings = MagicMock()
        settings.enable_reranker = False
        settings.reranker_top_n = 10
        mock_settings.return_value = settings

        result = await compiled_graph.ainvoke(state)

    # Reformulation should have been triggered
    assert result.get("_reformulated") is True
    # Retriever called twice (initial + after reformulation)
    assert call_count == 2
