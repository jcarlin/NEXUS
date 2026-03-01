"""Tests for the LangGraph investigation state graph."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.query.graph import _route_relevance, build_graph

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
def mock_llm():
    llm = AsyncMock()
    llm.complete.return_value = "mocked response"
    return llm


@pytest.fixture()
def mock_retriever():
    retriever = AsyncMock()
    retriever.retrieve_all.return_value = (
        [
            {"id": "p1", "score": 0.85, "source_file": "doc.pdf", "page_number": 1, "chunk_text": "chunk 1"},
        ],
        [
            {"source": "Person A", "relationship_type": "ASSOCIATED_WITH", "target": "Person B"},
        ],
    )
    return retriever


@pytest.fixture()
def mock_graph_service():
    gs = AsyncMock()
    gs.get_entity_connections.return_value = []
    return gs


@pytest.fixture()
def mock_entity_extractor():
    extractor = MagicMock()
    extractor.extract.return_value = [
        FakeEntity(text="Test Person", type="person", score=0.9, start=0, end=11),
    ]
    return extractor


# ---------------------------------------------------------------------------
# Route relevance tests
# ---------------------------------------------------------------------------


def test_route_relevance_returns_graph_lookup_when_relevant():
    assert _route_relevance({"_relevance": "relevant", "_reformulated": False}) == "graph_lookup"


def test_route_relevance_returns_reformulate_when_not_relevant():
    assert _route_relevance({"_relevance": "not_relevant", "_reformulated": False}) == "reformulate"


def test_route_relevance_returns_graph_lookup_when_already_reformulated():
    assert _route_relevance({"_relevance": "not_relevant", "_reformulated": True}) == "graph_lookup"


def test_route_relevance_defaults_to_graph_lookup():
    assert _route_relevance({}) == "graph_lookup"


# ---------------------------------------------------------------------------
# Graph construction tests
# ---------------------------------------------------------------------------


def test_build_graph_returns_state_graph(mock_llm, mock_retriever, mock_graph_service, mock_entity_extractor):
    graph = build_graph(mock_llm, mock_retriever, mock_graph_service, mock_entity_extractor)
    assert graph is not None


def test_build_graph_compiles(mock_llm, mock_retriever, mock_graph_service, mock_entity_extractor):
    graph = build_graph(mock_llm, mock_retriever, mock_graph_service, mock_entity_extractor)
    compiled = graph.compile()
    assert compiled is not None


def test_compiled_graph_has_expected_nodes(mock_llm, mock_retriever, mock_graph_service, mock_entity_extractor):
    graph = build_graph(mock_llm, mock_retriever, mock_graph_service, mock_entity_extractor)
    compiled = graph.compile()
    # The compiled graph should have our node names
    node_names = set(compiled.get_graph().nodes.keys())
    expected = {
        "classify",
        "rewrite",
        "retrieve",
        "rerank",
        "check_relevance",
        "graph_lookup",
        "reformulate",
        "synthesize",
        "generate_follow_ups",
    }
    # LangGraph adds __start__ and __end__ nodes
    assert expected.issubset(node_names)


def test_agentic_graph_has_expected_nodes():
    """The agentic graph should have the 4 expected parent nodes."""
    from app.query.graph import build_agentic_graph

    mock_settings = MagicMock()
    mock_settings.llm_model = "claude-sonnet-4-5-20250929"
    mock_settings.anthropic_api_key = "test-key"
    mock_settings.enable_citation_verification = True

    compiled = build_agentic_graph(mock_settings, checkpointer=False)
    node_names = set(compiled.get_graph().nodes.keys())

    expected = {
        "case_context_resolve",
        "investigation_agent",
        "verify_citations",
        "generate_follow_ups",
    }
    assert expected.issubset(node_names)


async def test_graph_invoke_end_to_end(mock_llm, mock_retriever, mock_graph_service, mock_entity_extractor):
    """Full end-to-end graph invocation with all mocks."""
    # Set up LLM to return different things for different calls
    call_count = 0

    async def mock_complete(messages, **kwargs):
        nonlocal call_count
        call_count += 1
        max_tokens = kwargs.get("max_tokens", 4096)
        if max_tokens == 20:
            return "factual"  # classify
        if max_tokens == 300:
            return "Who is Test Person in the documents?"  # rewrite
        if max_tokens == 500:
            return (
                "What documents mention Test Person?\n"
                "Are there financial connections?\n"
                "What is the chronological timeline?"
            )  # follow-ups
        return "Based on the evidence, Test Person is mentioned in doc.pdf [Source: doc.pdf, page 1]."  # synthesize

    mock_llm.complete.side_effect = mock_complete

    # synthesize node now uses llm.stream() — return an async iterator of tokens
    async def mock_stream(messages, **kwargs):
        for token in ["Based on the evidence, ", "Test Person is mentioned in doc.pdf."]:
            yield token

    mock_llm.stream = mock_stream

    graph = build_graph(mock_llm, mock_retriever, mock_graph_service, mock_entity_extractor)
    compiled = graph.compile()

    initial_state = {
        "messages": [],
        "thread_id": "test-thread",
        "user_id": "test-user",
        "original_query": "Who is Test Person?",
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

    final_state = await compiled.ainvoke(initial_state)

    # Verify the pipeline produced expected outputs
    assert final_state["query_type"] == "factual"
    assert len(final_state["rewritten_query"]) > 0
    assert len(final_state["response"]) > 0
    assert isinstance(final_state["source_documents"], list)
    assert isinstance(final_state["follow_up_questions"], list)
    assert isinstance(final_state["entities_mentioned"], list)
