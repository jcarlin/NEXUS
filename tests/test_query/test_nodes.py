"""Tests for LangGraph node functions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage, SystemMessage

from app.query.nodes import (
    _decompose_claims,
    _format_chat_history,
    _format_context,
    _format_graph_context,
    _verify_single_claim,
    audit_log_hook,
    build_system_prompt,
    classify_tier,
    create_nodes,
    post_agent_extract,
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
        {
            "id": f"p{i}",
            "score": 1.0 - i * 0.05,
            "source_file": f"doc{i}.pdf",
            "page_number": i,
            "chunk_text": f"text {i}",
        }
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
    nodes, llm, *_ = _make_nodes(
        [
            "mocked",  # For any prior calls
            "1. What connections does John Doe have to other individuals?\n"
            "2. Are there financial records mentioning John Doe?\n"
            "3. What is the timeline of John Doe's activities?",
        ]
    )
    state = _base_state(
        response="John Doe is mentioned in documents.",
        entities_mentioned=[{"name": "John Doe", "type": "person"}],
    )
    # Need to set up fresh nodes with the right response
    nodes2, llm2, *_ = _make_nodes(
        [
            "What connections does John Doe have to other individuals?\n"
            "Are there financial records mentioning John Doe?\n"
            "What is the timeline of John Doe's activities?"
        ]
    )
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
    mock_settings.enable_visual_embeddings = False

    with (
        patch("app.dependencies.get_settings", return_value=mock_settings),
        patch("app.dependencies.get_reranker", return_value=mock_reranker),
    ):
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
    mock_settings.enable_visual_embeddings = False

    with (
        patch("app.dependencies.get_settings", return_value=mock_settings),
        patch("app.dependencies.get_reranker", return_value=None),
    ):
        result = await nodes["rerank"](state)

    # Should use score-based sorting
    assert result["source_documents"][0]["relevance_score"] == 0.9
    assert result["source_documents"][1]["relevance_score"] == 0.3


async def test_graph_lookup_passes_exclude_privilege():
    """graph_lookup must forward _exclude_privilege state to get_entity_connections."""
    nodes, _, _, graph_service, _ = _make_nodes()
    state = _base_state(
        fused_context=[
            {
                "chunk_text": "John Doe was seen at the meeting.",
                "score": 0.9,
                "source_file": "doc.pdf",
                "page_number": 1,
                "id": "p1",
            },
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
    mock_settings.enable_visual_embeddings = False

    with (
        patch("app.dependencies.get_settings", return_value=mock_settings),
        patch("app.dependencies.get_reranker") as mock_get_reranker,
    ):
        result = await nodes["rerank"](state)

    # get_reranker should not be called when flag is off
    mock_get_reranker.assert_not_called()
    # Sorted by score descending
    assert result["source_documents"][0]["relevance_score"] == 0.8
    assert result["source_documents"][1]["relevance_score"] == 0.4


# ---------------------------------------------------------------------------
# _decompose_claims tests
# ---------------------------------------------------------------------------


async def test_decompose_claims_success():
    """LLM returns valid JSON array of claims -- should parse correctly."""
    llm = AsyncMock()
    llm.complete.return_value = json.dumps(
        [
            {"claim_text": "John Doe was present", "filename": "doc.pdf", "page_number": 1},
            {"claim_text": "Meeting occurred on Jan 5", "filename": "doc.pdf", "page_number": 2},
        ]
    )

    source_docs = [
        {"filename": "doc.pdf", "page": 1, "chunk_text": "John Doe attended the meeting on Jan 5."},
    ]

    result = await _decompose_claims(llm, "John Doe was present at the meeting on Jan 5.", source_docs)

    assert len(result) == 2
    assert result[0]["claim_text"] == "John Doe was present"
    assert result[1]["claim_text"] == "Meeting occurred on Jan 5"
    llm.complete.assert_called_once()


async def test_decompose_claims_llm_failure():
    """LLM raises an exception -- should return empty list."""
    llm = AsyncMock()
    llm.complete.side_effect = RuntimeError("API error")

    result = await _decompose_claims(llm, "some response", [])

    assert result == []


async def test_decompose_claims_invalid_json():
    """LLM returns unparseable garbage -- should return empty list."""
    llm = AsyncMock()
    llm.complete.return_value = "This is not JSON at all, just random text."

    result = await _decompose_claims(llm, "some response", [])

    assert result == []


# ---------------------------------------------------------------------------
# _verify_single_claim tests
# ---------------------------------------------------------------------------


async def test_verify_single_claim_supported():
    """Retriever returns evidence, LLM says 'supported' -- status='verified'."""
    llm = AsyncMock()
    llm.complete.return_value = "This claim is supported by the evidence. Confidence: 0.9"

    retriever = AsyncMock()
    retriever.retrieve_text.return_value = [
        {"source_file": "doc.pdf", "page_number": 1, "chunk_text": "supporting evidence text"},
    ]

    claim = {"claim_text": "John Doe was present", "filename": "doc.pdf", "page_number": 1, "claim_index": 0}

    result = await _verify_single_claim(llm, retriever, claim, None, [])

    assert result["verification_status"] == "verified"
    retriever.retrieve_text.assert_called_once()
    llm.complete.assert_called_once()


async def test_verify_single_claim_flagged():
    """LLM says claim cannot be verified -- status='flagged'."""
    llm = AsyncMock()
    llm.complete.return_value = "The evidence does not confirm this assertion. Confidence: 0.2"

    retriever = AsyncMock()
    retriever.retrieve_text.return_value = [
        {"source_file": "other.pdf", "page_number": 5, "chunk_text": "unrelated text"},
    ]

    claim = {"claim_text": "Fabricated claim", "filename": "doc.pdf", "page_number": 1, "claim_index": 0}

    result = await _verify_single_claim(llm, retriever, claim, None, [])

    assert result["verification_status"] == "flagged"


async def test_verify_single_claim_error():
    """Retriever raises an exception -- status='unverified'."""
    llm = AsyncMock()

    retriever = AsyncMock()
    retriever.retrieve_text.side_effect = RuntimeError("connection error")

    claim = {"claim_text": "Some claim", "filename": "doc.pdf", "page_number": 1, "claim_index": 0}

    result = await _verify_single_claim(llm, retriever, claim, None, [])

    assert result["verification_status"] == "unverified"
    llm.complete.assert_not_called()


# ---------------------------------------------------------------------------
# build_system_prompt tests
# ---------------------------------------------------------------------------


def test_build_system_prompt_returns_message_list():
    """build_system_prompt must return [SystemMessage, ...messages]."""
    user_msg = HumanMessage(content="Who is John Doe?")
    state = {"messages": [user_msg], "_case_context": ""}

    result = build_system_prompt(state)

    assert isinstance(result, list)
    assert len(result) == 2
    assert isinstance(result[0], SystemMessage)
    assert result[1] is user_msg


def test_build_system_prompt_includes_case_context():
    """Case context should be injected into the system message."""
    state = {"messages": [], "_case_context": "Key parties: Alice, Bob", "original_query": "test"}

    result = build_system_prompt(state)

    assert isinstance(result[0], SystemMessage)
    assert "Key parties: Alice, Bob" in result[0].content


def test_build_system_prompt_empty_messages_raises():
    """With no messages and no original_query, should raise ValueError."""
    state = {"messages": [], "_case_context": ""}

    import pytest

    with pytest.raises(ValueError, match="Cannot invoke investigation agent"):
        build_system_prompt(state)


# ---------------------------------------------------------------------------
# post_agent_extract tests
# ---------------------------------------------------------------------------


async def test_post_agent_extract_extracts_response_from_ai_message():
    """Should extract response from the last AIMessage without tool_calls."""
    from langchain_core.messages import AIMessage, HumanMessage

    state = {
        "messages": [
            HumanMessage(content="Who is John Doe?"),
            AIMessage(content="Based on the evidence, John Doe is a key figure."),
        ],
    }

    with patch("app.dependencies.get_entity_extractor") as mock_get_ee:
        mock_ee = MagicMock()
        mock_ee.extract.return_value = []
        mock_get_ee.return_value = mock_ee

        result = await post_agent_extract(state)

    assert result["response"] == "Based on the evidence, John Doe is a key figure."
    assert isinstance(result["source_documents"], list)
    assert isinstance(result["entities_mentioned"], list)


async def test_post_agent_extract_skips_ai_messages_with_tool_calls():
    """Should skip AIMessage that has tool_calls and find the final response."""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    tool_call_msg = AIMessage(
        content="",
        tool_calls=[{"id": "tc1", "name": "vector_search", "args": {"query": "test"}}],
    )
    tool_result = ToolMessage(
        content=json.dumps(
            [
                {"id": "p1", "filename": "doc.pdf", "page": 1, "text": "chunk text", "score": 0.9},
            ]
        ),
        tool_call_id="tc1",
    )
    final_response = AIMessage(content="John Doe is mentioned in doc.pdf on page 1.")

    state = {
        "messages": [
            HumanMessage(content="Who is John Doe?"),
            tool_call_msg,
            tool_result,
            final_response,
        ],
    }

    with patch("app.dependencies.get_entity_extractor") as mock_get_ee:
        mock_ee = MagicMock()
        mock_ee.extract.return_value = []
        mock_get_ee.return_value = mock_ee

        result = await post_agent_extract(state)

    assert result["response"] == "John Doe is mentioned in doc.pdf on page 1."


async def test_post_agent_extract_collects_source_documents():
    """Should collect source documents from ToolMessage results."""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    tool_result = ToolMessage(
        content=json.dumps(
            [
                {"id": "p1", "filename": "doc.pdf", "page": 1, "text": "chunk 1", "score": 0.9},
                {"id": "p2", "filename": "report.pdf", "page": 3, "text": "chunk 2", "score": 0.7},
            ]
        ),
        tool_call_id="tc1",
    )

    state = {
        "messages": [
            HumanMessage(content="test"),
            tool_result,
            AIMessage(content="Answer based on docs."),
        ],
    }

    with patch("app.dependencies.get_entity_extractor") as mock_get_ee:
        mock_ee = MagicMock()
        mock_ee.extract.return_value = []
        mock_get_ee.return_value = mock_ee

        result = await post_agent_extract(state)

    assert len(result["source_documents"]) == 2
    assert result["source_documents"][0]["id"] == "p1"
    assert result["source_documents"][0]["filename"] == "doc.pdf"
    assert result["source_documents"][0]["relevance_score"] == 0.9
    assert result["source_documents"][1]["id"] == "p2"


async def test_post_agent_extract_propagates_document_date():
    """Should carry a document_date field from tool results into source_documents."""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    tool_result = ToolMessage(
        content=json.dumps(
            [
                {
                    "id": "p1",
                    "filename": "email.eml",
                    "page": 1,
                    "text": "chunk 1",
                    "score": 0.9,
                    "document_date": "2020-02-15T10:00:00+00:00",
                },
                {
                    "id": "p2",
                    "filename": "scan.pdf",
                    "page": 1,
                    "text": "chunk 2",
                    "score": 0.7,
                    # no document_date: should propagate as None
                },
            ]
        ),
        tool_call_id="tc1",
    )

    state = {
        "messages": [
            HumanMessage(content="test"),
            tool_result,
            AIMessage(content="Answer."),
        ],
    }

    with patch("app.dependencies.get_entity_extractor") as mock_get_ee:
        mock_ee = MagicMock()
        mock_ee.extract.return_value = []
        mock_get_ee.return_value = mock_ee
        result = await post_agent_extract(state)

    assert result["source_documents"][0]["document_date"] == "2020-02-15T10:00:00+00:00"
    assert result["source_documents"][1]["document_date"] is None


async def test_post_agent_extract_deduplicates_sources():
    """Should not include duplicate document IDs in source_documents."""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    # Two tool results referencing the same document
    tool1 = ToolMessage(
        content=json.dumps([{"id": "p1", "filename": "doc.pdf", "page": 1, "text": "chunk", "score": 0.9}]),
        tool_call_id="tc1",
    )
    tool2 = ToolMessage(
        content=json.dumps([{"id": "p1", "filename": "doc.pdf", "page": 1, "text": "chunk", "score": 0.8}]),
        tool_call_id="tc2",
    )

    state = {
        "messages": [HumanMessage(content="test"), tool1, tool2, AIMessage(content="Answer.")],
    }

    with patch("app.dependencies.get_entity_extractor") as mock_get_ee:
        mock_ee = MagicMock()
        mock_ee.extract.return_value = []
        mock_get_ee.return_value = mock_ee

        result = await post_agent_extract(state)

    assert len(result["source_documents"]) == 1


async def test_post_agent_extract_empty_messages():
    """Should return empty fields when no messages."""
    state = {"messages": []}

    result = await post_agent_extract(state)

    assert result["response"] == ""
    assert result["source_documents"] == []
    assert result["entities_mentioned"] == []


async def test_post_agent_extract_extracts_entities():
    """Should extract entities from the response text."""
    from langchain_core.messages import AIMessage, HumanMessage

    state = {
        "messages": [
            HumanMessage(content="test"),
            AIMessage(content="John Doe met with Acme Corp."),
        ],
    }

    with patch("app.dependencies.get_entity_extractor") as mock_get_ee:
        mock_ee = MagicMock()
        mock_ee.extract.return_value = [
            FakeEntity(text="John Doe", type="person", score=0.9, start=0, end=8),
            FakeEntity(text="Acme Corp", type="organization", score=0.8, start=18, end=27),
        ]
        mock_get_ee.return_value = mock_ee

        result = await post_agent_extract(state)

    assert len(result["entities_mentioned"]) == 2
    assert result["entities_mentioned"][0]["name"] == "John Doe"
    assert result["entities_mentioned"][1]["name"] == "Acme Corp"


# ---------------------------------------------------------------------------
# audit_log_hook tests
# ---------------------------------------------------------------------------


async def test_audit_log_hook_returns_empty_dict():
    """audit_log_hook must return {} to avoid writing to managed channels."""
    with patch("app.dependencies.get_settings") as mock_settings:
        mock_settings.return_value.enable_ai_audit_logging = False

        result = await audit_log_hook({"messages": []})

    assert result == {}


async def test_audit_log_hook_fires_and_forgets():
    """audit_log_hook spawns a background task and returns immediately."""
    import asyncio

    mock_settings = MagicMock()
    mock_settings.enable_ai_audit_logging = True
    mock_settings.llm_model = "test-model"

    mock_session = AsyncMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.dependencies.get_settings", return_value=mock_settings),
        patch("app.dependencies.get_session_factory", return_value=mock_factory),
    ):
        result = await audit_log_hook({"messages": []})

    assert result == {}
    # Give background task a chance to run
    await asyncio.sleep(0.05)


# ---------------------------------------------------------------------------
# classify_tier tests
# ---------------------------------------------------------------------------


def testclassify_tier_question_mark_fast():
    """Short query with ? should be fast tier."""
    assert classify_tier("Who is John Doe?") == "fast"


def testclassify_tier_no_question_mark_with_interrogative():
    """Short query starting with interrogative word, no ? — still fast."""
    assert classify_tier("who is the main lawyer") == "fast"


def testclassify_tier_who_are():
    assert classify_tier("who are the key parties") == "fast"


def testclassify_tier_what_is():
    assert classify_tier("what is the settlement amount") == "fast"


def testclassify_tier_when_did():
    assert classify_tier("when did the contract expire") == "fast"


def testclassify_tier_list_the():
    assert classify_tier("list the defendants") == "fast"


def testclassify_tier_which():
    assert classify_tier("which documents mention Epstein") == "fast"


def testclassify_tier_deep_compare():
    assert classify_tier("compare the testimonies of witness A and witness B") == "deep"


def testclassify_tier_deep_long_query():
    long_query = " ".join(["word"] * 35)
    assert classify_tier(long_query) == "deep"


def testclassify_tier_deep_analyze():
    assert classify_tier("analyze the relationship between the parties") == "deep"


def testclassify_tier_standard_medium_length():
    """Medium-length query without fast markers or deep markers → standard."""
    assert classify_tier("tell me about the financial transactions in this case") == "standard"


def testclassify_tier_standard_imperative_no_marker():
    """Imperative without recognized fast opener → standard."""
    assert classify_tier("describe the events leading up to the settlement") == "standard"


# ---------------------------------------------------------------------------
# audit_log_hook — hard tool budget enforcement
# ---------------------------------------------------------------------------


async def test_audit_log_hook_under_budget():
    """Under budget with tool_calls -> no intervention, returns {}."""
    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_core.messages import ToolMessage as LCToolMessage

    messages = [
        HumanMessage(content="test"),
        AIMessage(content="", tool_calls=[{"id": "tc1", "name": "vector_search", "args": {}}]),
        LCToolMessage(content="result1", tool_call_id="tc1"),
        AIMessage(content="", tool_calls=[{"id": "tc2", "name": "graph_query", "args": {}}]),
        LCToolMessage(content="result2", tool_call_id="tc2"),
        AIMessage(content="", tool_calls=[{"id": "tc3", "name": "entity_lookup", "args": {}}]),
        LCToolMessage(content="result3", tool_call_id="tc3"),
        AIMessage(content="", tool_calls=[{"id": "tc4", "name": "vector_search", "args": {}}]),
    ]

    with patch("app.dependencies.get_settings") as mock_settings:
        mock_settings.return_value.enable_ai_audit_logging = False
        result = await audit_log_hook({"messages": messages, "_tier": "fast"})

    # 3 ToolMessages < budget of 5, so no intervention
    assert result == {}


async def test_audit_log_hook_over_budget_strips_tools():
    """Over budget + AIMessage with tool_calls -> returns budget-exhausted ToolMessages."""
    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_core.messages import ToolMessage as LCToolMessage

    tool_messages = [LCToolMessage(content=f"result{i}", tool_call_id=f"tc{i}") for i in range(6)]
    ai_with_calls = [
        AIMessage(content="", tool_calls=[{"id": f"tc{i}", "name": "vector_search", "args": {}}]) for i in range(6)
    ]
    messages = [HumanMessage(content="test")]
    for ai, tm in zip(ai_with_calls, tool_messages):
        messages.append(ai)
        messages.append(tm)
    messages.append(
        AIMessage(
            content="",
            tool_calls=[
                {"id": "tc_extra1", "name": "graph_query", "args": {}},
                {"id": "tc_extra2", "name": "entity_lookup", "args": {}},
            ],
        )
    )

    with patch("app.dependencies.get_settings") as mock_settings:
        mock_settings.return_value.enable_ai_audit_logging = False
        result = await audit_log_hook({"messages": messages, "_tier": "fast"})

    assert "messages" in result
    assert len(result["messages"]) == 2
    for msg in result["messages"]:
        assert isinstance(msg, LCToolMessage)
        assert "budget exhausted" in msg.content.lower()
    assert result["messages"][0].tool_call_id == "tc_extra1"
    assert result["messages"][1].tool_call_id == "tc_extra2"


async def test_audit_log_hook_over_budget_no_tools():
    """Over budget but AIMessage has no tool_calls -> no intervention."""
    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_core.messages import ToolMessage as LCToolMessage

    tool_messages = [LCToolMessage(content=f"result{i}", tool_call_id=f"tc{i}") for i in range(6)]
    ai_with_calls = [
        AIMessage(content="", tool_calls=[{"id": f"tc{i}", "name": "vector_search", "args": {}}]) for i in range(6)
    ]
    messages = [HumanMessage(content="test")]
    for ai, tm in zip(ai_with_calls, tool_messages):
        messages.append(ai)
        messages.append(tm)
    messages.append(AIMessage(content="Here is my final answer."))

    with patch("app.dependencies.get_settings") as mock_settings:
        mock_settings.return_value.enable_ai_audit_logging = False
        result = await audit_log_hook({"messages": messages, "_tier": "fast"})

    assert result == {}
