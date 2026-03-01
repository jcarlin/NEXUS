"""Tests for the HybridRetriever."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.query.retriever import HybridRetriever

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass
class FakeEntity:
    text: str
    type: str
    score: float
    start: int
    end: int


@pytest.fixture()
def mock_embedder():
    embedder = AsyncMock()
    embedder.embed_query.return_value = [0.1] * 1024
    return embedder


@pytest.fixture()
def mock_vector_store():
    vs = AsyncMock()
    vs.query_text.return_value = [
        {"id": "p1", "score": 0.9, "source_file": "doc.pdf", "page_number": 1, "chunk_text": "chunk 1"},
        {"id": "p2", "score": 0.8, "source_file": "doc.pdf", "page_number": 2, "chunk_text": "chunk 2"},
    ]
    return vs


@pytest.fixture()
def mock_entity_extractor():
    extractor = MagicMock()
    extractor.extract.return_value = [
        FakeEntity(text="Jeffrey Epstein", type="person", score=0.95, start=0, end=15),
    ]
    return extractor


@pytest.fixture()
def mock_graph_service():
    gs = AsyncMock()
    gs.get_entity_connections.return_value = [
        {"source": "Jeffrey Epstein", "relationship_type": "ASSOCIATED_WITH", "target": "Ghislaine Maxwell"},
    ]
    return gs


@pytest.fixture()
def retriever(mock_embedder, mock_vector_store, mock_entity_extractor, mock_graph_service):
    return HybridRetriever(
        embedder=mock_embedder,
        vector_store=mock_vector_store,
        entity_extractor=mock_entity_extractor,
        graph_service=mock_graph_service,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_retrieve_text_embeds_query_and_searches(retriever, mock_embedder, mock_vector_store):
    results = await retriever.retrieve_text("Who is Epstein?")
    mock_embedder.embed_query.assert_called_once_with("Who is Epstein?")
    mock_vector_store.query_text.assert_called_once()
    assert len(results) == 2


async def test_retrieve_text_passes_filters(retriever, mock_vector_store):
    await retriever.retrieve_text("query", filters={"document_type": "flight_log"})
    _, kwargs = mock_vector_store.query_text.call_args
    assert kwargs["filters"] == {"document_type": "flight_log"}


async def test_retrieve_graph_extracts_entities_and_fetches_connections(
    retriever, mock_entity_extractor, mock_graph_service
):
    results = await retriever.retrieve_graph("Who is Jeffrey Epstein?")
    mock_entity_extractor.extract.assert_called_once()
    mock_graph_service.get_entity_connections.assert_called_once_with(
        "Jeffrey Epstein",
        limit=20,
        exclude_privilege_statuses=None,
    )
    assert len(results) == 1
    assert results[0]["source"] == "Jeffrey Epstein"


async def test_retrieve_graph_returns_empty_when_no_entities(retriever, mock_entity_extractor):
    mock_entity_extractor.extract.return_value = []
    results = await retriever.retrieve_graph("what happened?")
    assert results == []


async def test_retrieve_graph_deduplicates_connections(retriever, mock_entity_extractor, mock_graph_service):
    mock_entity_extractor.extract.return_value = [
        FakeEntity(text="Epstein", type="person", score=0.9, start=0, end=7),
        FakeEntity(text="Maxwell", type="person", score=0.8, start=10, end=17),
    ]
    # Both entities return the same connection
    mock_graph_service.get_entity_connections.return_value = [
        {"source": "Epstein", "relationship_type": "ASSOCIATED_WITH", "target": "Maxwell"},
    ]
    results = await retriever.retrieve_graph("Epstein and Maxwell")
    # Should be deduplicated to 1
    assert len(results) == 1


async def test_retrieve_all_runs_in_parallel(retriever):
    text_results, graph_results = await retriever.retrieve_all("test query")
    assert len(text_results) == 2
    assert len(graph_results) == 1


async def test_extract_query_entities_uses_higher_threshold(retriever, mock_entity_extractor):
    retriever.extract_query_entities("Who is Epstein?")
    _, kwargs = mock_entity_extractor.extract.call_args
    assert kwargs["threshold"] == 0.5


async def test_retrieve_text_with_sparse_embedder(
    mock_embedder, mock_vector_store, mock_entity_extractor, mock_graph_service
):
    """When sparse_embedder is provided, retrieve_text generates sparse vector and passes it."""
    mock_sparse = MagicMock()
    mock_sparse.embed_single.return_value = ([0, 5, 10], [0.9, 0.4, 0.1])

    retriever = HybridRetriever(
        embedder=mock_embedder,
        vector_store=mock_vector_store,
        entity_extractor=mock_entity_extractor,
        graph_service=mock_graph_service,
        sparse_embedder=mock_sparse,
    )

    await retriever.retrieve_text("Who is Epstein?")

    mock_sparse.embed_single.assert_called_once_with("Who is Epstein?")
    call_kwargs = mock_vector_store.query_text.call_args.kwargs
    assert call_kwargs["sparse_vector"] == ([0, 5, 10], [0.9, 0.4, 0.1])


async def test_retrieve_graph_passes_exclude_privilege(retriever, mock_graph_service):
    """retrieve_graph must forward exclude_privilege_statuses to get_entity_connections."""
    await retriever.retrieve_graph(
        "Who is Jeffrey Epstein?",
        exclude_privilege_statuses=["privileged", "work_product"],
    )
    call_kwargs = mock_graph_service.get_entity_connections.call_args.kwargs
    assert call_kwargs["exclude_privilege_statuses"] == ["privileged", "work_product"]


async def test_retrieve_all_forwards_privilege_to_graph(retriever, mock_graph_service):
    """retrieve_all must pass exclude_privilege_statuses through to retrieve_graph."""
    await retriever.retrieve_all(
        "test query",
        exclude_privilege_statuses=["privileged"],
    )
    call_kwargs = mock_graph_service.get_entity_connections.call_args.kwargs
    assert call_kwargs["exclude_privilege_statuses"] == ["privileged"]


async def test_retrieve_text_without_sparse_embedder_skips_sparse(retriever, mock_vector_store):
    """When no sparse_embedder, retrieve_text should not pass sparse_vector."""
    await retriever.retrieve_text("Who is Epstein?")

    call_kwargs = mock_vector_store.query_text.call_args.kwargs
    assert call_kwargs.get("sparse_vector") is None


# ---------------------------------------------------------------------------
# Visual reranking tests
# ---------------------------------------------------------------------------


async def test_rerank_visual_blends_scores(mock_embedder, mock_vector_store, mock_entity_extractor, mock_graph_service):
    """When visual_embedder is provided, rerank_visual blends text and visual scores."""
    mock_visual = MagicMock()
    mock_visual.embed_query.return_value = [[0.1] * 128, [0.2] * 128]

    retriever = HybridRetriever(
        embedder=mock_embedder,
        vector_store=mock_vector_store,
        entity_extractor=mock_entity_extractor,
        graph_service=mock_graph_service,
        visual_embedder=mock_visual,
    )

    # Mock visual query results
    mock_vector_store.query_visual = AsyncMock(
        return_value=[{"id": "job1_page_1", "score": 0.9, "doc_id": "job1", "page_number": 1}]
    )

    candidates = [
        {"id": "p1", "score": 0.8, "doc_id": "job1", "page_number": 1, "chunk_text": "chunk 1"},
        {"id": "p2", "score": 0.7, "doc_id": "job1", "page_number": 2, "chunk_text": "chunk 2"},
    ]

    results = await retriever.rerank_visual("test query", candidates, weight=0.3)

    # First candidate: (1 - 0.3) * 0.8 + 0.3 * 0.9 = 0.56 + 0.27 = 0.83
    assert results[0].get("_visual_reranked") is True
    assert abs(results[0]["score"] - 0.83) < 0.01


async def test_rerank_visual_disabled_returns_unchanged(
    mock_embedder, mock_vector_store, mock_entity_extractor, mock_graph_service
):
    """When no visual_embedder, rerank_visual returns candidates unchanged."""
    retriever = HybridRetriever(
        embedder=mock_embedder,
        vector_store=mock_vector_store,
        entity_extractor=mock_entity_extractor,
        graph_service=mock_graph_service,
        visual_embedder=None,
    )

    candidates = [
        {"id": "p1", "score": 0.8, "chunk_text": "chunk 1"},
        {"id": "p2", "score": 0.7, "chunk_text": "chunk 2"},
    ]

    results = await retriever.rerank_visual("test query", candidates, top_n=10)

    assert len(results) == 2
    assert results[0]["score"] == 0.8  # Unchanged
    assert results[1]["score"] == 0.7


async def test_rerank_visual_empty_candidates(
    mock_embedder, mock_vector_store, mock_entity_extractor, mock_graph_service
):
    """rerank_visual with empty candidates returns empty list."""
    mock_visual = MagicMock()

    retriever = HybridRetriever(
        embedder=mock_embedder,
        vector_store=mock_vector_store,
        entity_extractor=mock_entity_extractor,
        graph_service=mock_graph_service,
        visual_embedder=mock_visual,
    )

    results = await retriever.rerank_visual("test query", [])
    assert results == []
