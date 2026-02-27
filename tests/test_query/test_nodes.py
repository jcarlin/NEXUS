"""Tests for LangGraph node functions."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.query.nodes import (
    _format_chat_history,
    _format_context,
    _format_graph_context,
    create_nodes,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeEntity:
    text: str
    type: str
    score: float
    start: int
    end: int


def _make_nodes(llm_responses: list[str] | None = None):
    """Create nodes with mocked dependencies."""
    llm = AsyncMock()
    if llm_responses:
        llm.complete.side_effect = llm_responses
    else:
        llm.complete.return_value = "mocked response"

    # synthesize uses llm.stream() — provide an async generator
    async def _mock_stream(messages, **kwargs):
        response = llm_responses[-1] if llm_responses else "mocked response"
        yield response

    llm.stream = _mock_stream

    retriever = AsyncMock()
    retriever.retrieve_all.return_value = (
        [
            {"id": "p1", "score": 0.9, "source_file": "doc.pdf", "page_number": 1, "chunk_text": "chunk text 1"},
            {"id": "p2", "score": 0.5, "source_file": "doc2.pdf", "page_number": 3, "chunk_text": "chunk text 2"},
        ],
        [
            {"source": "Person A", "relationship_type": "ASSOCIATED_WITH", "target": "Person B"},
        ],
    )

    graph_service = AsyncMock()
    graph_service.get_entity_connections.return_value = []

    entity_extractor = MagicMock()
    entity_extractor.extract.return_value = [
        FakeEntity(text="John Doe", type="person", score=0.9, start=0, end=8),
    ]

    nodes = create_nodes(llm, retriever, graph_service, entity_extractor)
    return nodes, llm, retriever, graph_service, entity_extractor


def _base_state(**overrides) -> dict:
    state = {
        "messages": [],
        "thread_id": "test-thread",
        "user_id": "test-user",
        "original_query": "Who is John Doe?",
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
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------


def test_format_chat_history_empty():
    assert _format_chat_history([]) == "(no prior conversation)"


def test_format_chat_history_with_messages():
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    result = _format_chat_history(messages)
    assert "User: hello" in result
    assert "Assistant: hi" in result


def test_format_chat_history_truncates_to_six():
    messages = [{"role": "user", "content": f"msg {i}"} for i in range(10)]
    result = _format_chat_history(messages)
    # Should only include last 6
    assert "msg 4" in result
    assert "msg 3" not in result


def test_format_context_empty():
    assert "(no evidence retrieved)" in _format_context([])


def test_format_context_with_results():
    results = [
        {"source_file": "doc.pdf", "page_number": 1, "chunk_text": "evidence text"},
    ]
    result = _format_context(results)
    assert "[1]" in result
    assert "doc.pdf" in result
    assert "evidence text" in result


def test_format_graph_context_empty():
    assert "(no graph connections found)" in _format_graph_context([])


def test_format_graph_context_with_connections():
    connections = [
        {"source": "A", "relationship_type": "KNOWS", "target": "B"},
    ]
    result = _format_graph_context(connections)
    assert "A --[KNOWS]--> B" in result


# ---------------------------------------------------------------------------
# Node tests
# ---------------------------------------------------------------------------


async def test_classify_returns_valid_category():
    nodes, llm, *_ = _make_nodes(["factual"])
    result = await nodes["classify"](_base_state())
    assert result["query_type"] in {"factual", "analytical", "exploratory", "timeline"}


async def test_classify_defaults_to_factual_on_garbage():
    nodes, llm, *_ = _make_nodes(["gobbledygook nonsense"])
    result = await nodes["classify"](_base_state())
    assert result["query_type"] == "factual"


async def test_rewrite_returns_rewritten_query():
    nodes, llm, *_ = _make_nodes(["Who is John Doe according to the documents?"])
    result = await nodes["rewrite"](_base_state())
    assert "rewritten_query" in result
    assert len(result["rewritten_query"]) > 0


async def test_rewrite_falls_back_to_original_on_empty():
    nodes, llm, *_ = _make_nodes(["   "])
    result = await nodes["rewrite"](_base_state())
    assert result["rewritten_query"] == "Who is John Doe?"


async def test_retrieve_calls_retriever():
    nodes, _, retriever, *_ = _make_nodes()
    state = _base_state(rewritten_query="Who is John Doe?")
    result = await nodes["retrieve"](state)
    retriever.retrieve_all.assert_called_once()
    assert len(result["text_results"]) == 2
    assert len(result["graph_results"]) == 1


async def test_rerank_takes_top_10_by_score():
    nodes, *_ = _make_nodes()
    results = [
        {"id": f"p{i}", "score": 1.0 - i * 0.05, "source_file": f"doc{i}.pdf", "page_number": i, "chunk_text": f"text {i}"}
        for i in range(15)
    ]
    state = _base_state(text_results=results)
    result = await nodes["rerank"](state)
    assert len(result["fused_context"]) == 10
    assert len(result["source_documents"]) == 10
    # First should be highest score
    assert result["source_documents"][0]["relevance_score"] == 1.0


async def test_check_relevance_relevant():
    nodes, *_ = _make_nodes()
    state = _base_state(fused_context=[{"score": 0.8}, {"score": 0.7}, {"score": 0.6}, {"score": 0.5}, {"score": 0.4}])
    result = await nodes["check_relevance"](state)
    assert result["_relevance"] == "relevant"


async def test_check_relevance_not_relevant():
    nodes, *_ = _make_nodes()
    state = _base_state(fused_context=[{"score": 0.1}, {"score": 0.15}, {"score": 0.2}])
    result = await nodes["check_relevance"](state)
    assert result["_relevance"] == "not_relevant"


async def test_check_relevance_empty_results():
    nodes, *_ = _make_nodes()
    state = _base_state(fused_context=[])
    result = await nodes["check_relevance"](state)
    assert result["_relevance"] == "not_relevant"


async def test_reformulate_returns_new_query():
    nodes, llm, *_ = _make_nodes(["alternative query about John Doe"])
    state = _base_state(rewritten_query="Who is John Doe?")
    result = await nodes["reformulate"](state)
    assert result["rewritten_query"] == "alternative query about John Doe"
    assert result["_reformulated"] is True


async def test_synthesize_generates_response():
    nodes, llm, *_ = _make_nodes(["Based on evidence, John Doe is [Source: doc.pdf, page 1]..."])
    state = _base_state(
        fused_context=[{"source_file": "doc.pdf", "page_number": 1, "chunk_text": "evidence"}],
        graph_results=[{"source": "A", "relationship_type": "KNOWS", "target": "B"}],
    )
    result = await nodes["synthesize"](state)
    assert "response" in result
    assert len(result["response"]) > 0
    assert "entities_mentioned" in result


async def test_generate_follow_ups_returns_list():
    nodes, llm, *_ = _make_nodes([
        "mocked",  # For any prior calls
        "1. What connections does John Doe have to other individuals?\n"
        "2. Are there financial records mentioning John Doe?\n"
        "3. What is the timeline of John Doe's activities?"
    ])
    state = _base_state(
        response="John Doe is mentioned in documents.",
        entities_mentioned=[{"name": "John Doe", "type": "person"}],
    )
    # Need to set up fresh nodes with the right response
    nodes2, llm2, *_ = _make_nodes([
        "What connections does John Doe have to other individuals?\n"
        "Are there financial records mentioning John Doe?\n"
        "What is the timeline of John Doe's activities?"
    ])
    result = await nodes2["generate_follow_ups"](state)
    assert "follow_up_questions" in result
    assert isinstance(result["follow_up_questions"], list)
    assert len(result["follow_up_questions"]) <= 3


# ---------------------------------------------------------------------------
# Reranker feature-flag tests
# ---------------------------------------------------------------------------


async def test_rerank_uses_cross_encoder_when_enabled():
    """When enable_reranker=True and reranker available, use cross-encoder."""
    nodes, *_ = _make_nodes()
    results = [
        {"id": f"p{i}", "score": 0.5, "source_file": f"doc{i}.pdf", "page_number": i, "chunk_text": f"text {i}"}
        for i in range(5)
    ]
    state = _base_state(text_results=results, rewritten_query="test query")

    mock_reranker = MagicMock()
    mock_reranker.rerank.return_value = [
        {"id": "p2", "score": 0.95, "source_file": "doc2.pdf", "page_number": 2, "chunk_text": "text 2"},
        {"id": "p0", "score": 0.80, "source_file": "doc0.pdf", "page_number": 0, "chunk_text": "text 0"},
    ]

    mock_settings = MagicMock()
    mock_settings.enable_reranker = True
    mock_settings.reranker_top_n = 10

    with patch("app.dependencies.get_settings", return_value=mock_settings), \
         patch("app.dependencies.get_reranker", return_value=mock_reranker):
        result = await nodes["rerank"](state)

    mock_reranker.rerank.assert_called_once()
    assert len(result["source_documents"]) == 2
    assert result["source_documents"][0]["relevance_score"] == 0.95


async def test_rerank_falls_back_when_reranker_none():
    """Flag on but reranker returns None → fall back to score-based sorting."""
    nodes, *_ = _make_nodes()
    results = [
        {"id": "p0", "score": 0.9, "source_file": "doc0.pdf", "page_number": 0, "chunk_text": "text 0"},
        {"id": "p1", "score": 0.3, "source_file": "doc1.pdf", "page_number": 1, "chunk_text": "text 1"},
    ]
    state = _base_state(text_results=results)

    mock_settings = MagicMock()
    mock_settings.enable_reranker = True
    mock_settings.reranker_top_n = 10

    with patch("app.dependencies.get_settings", return_value=mock_settings), \
         patch("app.dependencies.get_reranker", return_value=None):
        result = await nodes["rerank"](state)

    # Should use score-based sorting
    assert result["source_documents"][0]["relevance_score"] == 0.9
    assert result["source_documents"][1]["relevance_score"] == 0.3


async def test_graph_lookup_passes_exclude_privilege():
    """graph_lookup must forward _exclude_privilege state to get_entity_connections."""
    nodes, _, _, graph_service, _ = _make_nodes()
    state = _base_state(
        fused_context=[
            {"chunk_text": "John Doe was seen at the meeting.", "score": 0.9,
             "source_file": "doc.pdf", "page_number": 1, "id": "p1"},
        ],
        graph_results=[],
        _exclude_privilege=["privileged", "work_product"],
    )
    await nodes["graph_lookup"](state)

    # get_entity_connections should have been called with the exclusion list
    graph_service.get_entity_connections.assert_called_once()
    call_kwargs = graph_service.get_entity_connections.call_args.kwargs
    assert call_kwargs["exclude_privilege_statuses"] == ["privileged", "work_product"]


async def test_rerank_uses_score_sorting_when_disabled():
    """When enable_reranker=False, no reranker call, score-based sorting only."""
    nodes, *_ = _make_nodes()
    results = [
        {"id": "p0", "score": 0.4, "source_file": "doc0.pdf", "page_number": 0, "chunk_text": "text 0"},
        {"id": "p1", "score": 0.8, "source_file": "doc1.pdf", "page_number": 1, "chunk_text": "text 1"},
    ]
    state = _base_state(text_results=results)

    mock_settings = MagicMock()
    mock_settings.enable_reranker = False
    mock_settings.reranker_top_n = 10

    with patch("app.dependencies.get_settings", return_value=mock_settings), \
         patch("app.dependencies.get_reranker") as mock_get_reranker:
        result = await nodes["rerank"](state)

    # get_reranker should not be called when flag is off
    mock_get_reranker.assert_not_called()
    # Sorted by score descending
    assert result["source_documents"][0]["relevance_score"] == 0.8
    assert result["source_documents"][1]["relevance_score"] == 0.4
