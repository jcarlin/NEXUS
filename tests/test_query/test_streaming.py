"""Tests for the streaming refactor (graph.astream with custom channel)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def _reset_sse_status():
    """Reset sse-starlette's AppStatus between tests.

    AppStatus.should_exit_event is a module-level asyncio.Event that gets
    bound to the first test's event loop and fails in subsequent tests.
    """
    try:
        from sse_starlette.sse import AppStatus

        AppStatus.should_exit_event = asyncio.Event()
    except Exception:
        pass


@pytest.fixture()
async def stream_client():
    """Async test client with graph.astream mocked."""
    from app import main as main_module

    async def _noop_lifespan(app):
        yield

    with patch.object(main_module, "lifespan", _noop_lifespan):
        test_app = main_module.create_app()

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_graph = AsyncMock()

        from app import dependencies

        async def mock_get_db():
            yield mock_db

        test_app.dependency_overrides[dependencies.get_db] = mock_get_db
        test_app.dependency_overrides[dependencies.get_query_graph] = lambda: mock_graph

        from uuid import UUID

        from app.auth.middleware import get_current_user, get_matter_id
        from app.common.rate_limit import rate_limit_queries

        test_app.dependency_overrides[rate_limit_queries] = lambda: None
        from datetime import UTC, datetime

        from app.auth.schemas import UserRecord

        test_app.dependency_overrides[get_current_user] = lambda: UserRecord(
            id=UUID("00000000-0000-0000-0000-000000000099"),
            email="test@nexus.dev",
            full_name="Test",
            role="admin",
            is_active=True,
            created_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        test_app.dependency_overrides[get_matter_id] = lambda: UUID("00000000-0000-0000-0000-000000000001")

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac, mock_db, mock_graph


def _make_astream(events):
    """Create an async generator from a list of event tuples.

    Supports both 2-tuples ``(stream_mode, chunk)`` for v1 and
    3-tuples ``(namespace, stream_mode, chunk)`` for agentic (subgraphs=True).
    """

    async def astream(*args, **kwargs):
        for event in events:
            yield event

    return astream


def _mock_settings(**overrides):
    """Create a mock Settings with common defaults."""
    from unittest.mock import MagicMock

    s = MagicMock()
    s.enable_agentic_pipeline = overrides.get("enable_agentic_pipeline", False)
    s.enable_case_setup_agent = False
    return s


@pytest.mark.asyncio
async def test_stream_emits_status_events(stream_client):
    """The stream should emit status events for each node update."""
    client, mock_db, mock_graph = stream_client

    events = [
        ("updates", {"classify": {"query_type": "factual"}}),
        ("updates", {"rewrite": {"rewritten_query": "test"}}),
        ("updates", {"retrieve": {"text_results": [], "graph_results": []}}),
        ("updates", {"rerank": {"fused_context": [], "source_documents": []}}),
        ("updates", {"check_relevance": {"_relevance": "relevant"}}),
        ("updates", {"graph_lookup": {"graph_results": []}}),
        ("updates", {"synthesize": {"response": "answer", "entities_mentioned": []}}),
        ("updates", {"generate_follow_ups": {"follow_up_questions": []}}),
    ]
    mock_graph.astream = _make_astream(events)

    with patch("app.dependencies.get_settings", return_value=_mock_settings(enable_agentic_pipeline=False)):
        response = await client.post(
            "/api/v1/query/stream",
            json={"query": "test question"},
        )
    assert response.status_code == 200

    lines = response.text.strip().split("\n")
    status_events = [line for line in lines if line.startswith("event: status")]
    # Should have at least one status event per node
    assert len(status_events) >= 8


@pytest.mark.asyncio
async def test_stream_emits_sources_after_rerank(stream_client):
    """The stream should emit a sources event after the rerank node."""
    client, mock_db, mock_graph = stream_client

    source_docs = [
        {
            "id": "p1",
            "filename": "doc.pdf",
            "page": 1,
            "chunk_text": "test",
            "relevance_score": 0.9,
            "preview_url": None,
            "download_url": None,
        }
    ]

    events = [
        ("updates", {"classify": {"query_type": "factual"}}),
        ("updates", {"rewrite": {"rewritten_query": "test"}}),
        ("updates", {"retrieve": {"text_results": []}}),
        ("updates", {"rerank": {"source_documents": source_docs, "fused_context": []}}),
        ("updates", {"check_relevance": {"_relevance": "relevant"}}),
        ("updates", {"graph_lookup": {"graph_results": []}}),
        ("updates", {"synthesize": {"response": "answer", "entities_mentioned": []}}),
        ("updates", {"generate_follow_ups": {"follow_up_questions": []}}),
    ]
    mock_graph.astream = _make_astream(events)

    with patch("app.dependencies.get_settings", return_value=_mock_settings(enable_agentic_pipeline=False)):
        response = await client.post(
            "/api/v1/query/stream",
            json={"query": "test question"},
        )

    lines = response.text.strip().split("\n")
    sources_lines = [line for line in lines if line.startswith("event: sources")]
    assert len(sources_lines) == 1

    # Find the data line after the sources event
    for i, line in enumerate(lines):
        if line.startswith("event: sources"):
            # Next non-empty line should be data
            for j in range(i + 1, len(lines)):
                if lines[j].startswith("data: "):
                    data = json.loads(lines[j][6:])
                    assert "documents" in data
                    assert len(data["documents"]) == 1
                    break
            break


@pytest.mark.asyncio
async def test_stream_emits_tokens(stream_client):
    """The stream should emit token events from the custom channel."""
    client, mock_db, mock_graph = stream_client

    events = [
        ("updates", {"classify": {"query_type": "factual"}}),
        ("updates", {"rewrite": {"rewritten_query": "test"}}),
        ("updates", {"retrieve": {"text_results": []}}),
        ("updates", {"rerank": {"source_documents": [], "fused_context": []}}),
        ("updates", {"check_relevance": {"_relevance": "relevant"}}),
        ("updates", {"graph_lookup": {"graph_results": []}}),
        ("custom", {"type": "token", "text": "Hello"}),
        ("custom", {"type": "token", "text": " world"}),
        ("updates", {"synthesize": {"response": "Hello world", "entities_mentioned": []}}),
        ("updates", {"generate_follow_ups": {"follow_up_questions": []}}),
    ]
    mock_graph.astream = _make_astream(events)

    with patch("app.dependencies.get_settings", return_value=_mock_settings(enable_agentic_pipeline=False)):
        response = await client.post(
            "/api/v1/query/stream",
            json={"query": "test question"},
        )

    lines = response.text.strip().split("\n")
    token_events = [line for line in lines if line.startswith("event: token")]
    assert len(token_events) == 2


@pytest.mark.asyncio
async def test_stream_emits_done_event(stream_client):
    """The stream should emit a done event with thread_id, follow_ups, and entities."""
    client, mock_db, mock_graph = stream_client

    follow_ups = ["What else?", "Who was involved?", "When did this happen?"]
    entities = [{"name": "Test", "type": "person", "kg_id": None, "connections": 0}]

    events = [
        ("updates", {"classify": {"query_type": "factual"}}),
        ("updates", {"rewrite": {"rewritten_query": "test"}}),
        ("updates", {"retrieve": {"text_results": []}}),
        ("updates", {"rerank": {"source_documents": [], "fused_context": []}}),
        ("updates", {"check_relevance": {"_relevance": "relevant"}}),
        ("updates", {"graph_lookup": {"graph_results": []}}),
        ("updates", {"synthesize": {"response": "answer", "entities_mentioned": entities}}),
        ("updates", {"generate_follow_ups": {"follow_up_questions": follow_ups}}),
    ]
    mock_graph.astream = _make_astream(events)

    with patch("app.dependencies.get_settings", return_value=_mock_settings(enable_agentic_pipeline=False)):
        response = await client.post(
            "/api/v1/query/stream",
            json={"query": "test question"},
        )

    lines = response.text.strip().split("\n")
    done_lines = [line for line in lines if line.startswith("event: done")]
    assert len(done_lines) == 1

    # Find the data for the done event
    for i, line in enumerate(lines):
        if line.startswith("event: done"):
            for j in range(i + 1, len(lines)):
                if lines[j].startswith("data: "):
                    data = json.loads(lines[j][6:])
                    assert "thread_id" in data
                    assert data["follow_ups"] == follow_ups
                    assert data["entities"] == entities
                    break
            break


@pytest.mark.asyncio
async def test_v1_generator_exit_handled(stream_client):
    """V1 pipeline should handle GeneratorExit without propagating errors."""
    client, mock_db, mock_graph = stream_client

    async def astream_raises_generator_exit(*args, **kwargs):
        yield ("updates", {"classify": {"query_type": "factual"}})
        yield ("updates", {"rewrite": {"rewritten_query": "test"}})
        raise GeneratorExit()

    mock_graph.astream = astream_raises_generator_exit

    with patch("app.dependencies.get_settings", return_value=_mock_settings(enable_agentic_pipeline=False)):
        response = await client.post(
            "/api/v1/query/stream",
            json={"query": "test question"},
        )

    # Stream should close gracefully — no 500 error
    assert response.status_code == 200

    lines = response.text.strip().split("\n")
    # Should have some status events from before the disconnect
    status_events = [line for line in lines if line.startswith("event: status")]
    assert len(status_events) >= 1

    # Should NOT have a done event (client disconnected before completion)
    done_events = [line for line in lines if line.startswith("event: done")]
    assert len(done_events) == 0

    # Chat persistence should NOT have been called
    mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_stream_emits_agentic_status_events(stream_client):
    """Agentic pipeline node names map to correct SSE status events."""
    client, mock_db, mock_graph = stream_client

    # Agentic generator uses subgraphs=True → 3-tuples (namespace, stream_mode, chunk)
    events = [
        (
            (),
            "updates",
            {
                "case_context_resolve": {
                    "_case_context": "ctx",
                    "_term_map": {},
                    "_tier": "standard",
                    "_skip_verification": False,
                }
            },
        ),
        ((), "updates", {"investigation_agent": {"messages": []}}),
        (
            (),
            "updates",
            {"post_agent_extract": {"response": "answer", "source_documents": [], "entities_mentioned": []}},
        ),
        ((), "updates", {"verify_citations": {"cited_claims": []}}),
        ((), "updates", {"generate_follow_ups": {"follow_up_questions": ["Q1?", "Q2?"]}}),
    ]
    mock_graph.astream = _make_astream(events)

    with patch("app.dependencies.get_settings", return_value=_mock_settings(enable_agentic_pipeline=True)):
        response = await client.post(
            "/api/v1/query/stream",
            json={"query": "test question"},
        )
    assert response.status_code == 200

    lines = response.text.strip().split("\n")
    status_events = [line for line in lines if line.startswith("event: status")]
    # Should have status events for each node
    assert len(status_events) >= 5

    # Check that agentic stage names appear in the data
    data_lines = [line for line in lines if line.startswith("data: ") and "stage" in line]
    stage_names = [json.loads(line[6:])["stage"] for line in data_lines]
    assert "resolving_context" in stage_names
    assert "investigating" in stage_names
    assert "extracting_results" in stage_names
    assert "verifying_citations" in stage_names
    assert "generating_follow_ups" in stage_names


async def test_agentic_stream_skips_none_updates(stream_client):
    """Subgraph internals can produce None update values — must not crash."""
    client, mock_db, mock_graph = stream_client

    events = [
        # Subgraph internal node emits None update
        (("agent:investigation_agent",), "updates", {"agent": None}),
        # Normal root-level node with real data
        (
            (),
            "updates",
            {"post_agent_extract": {"response": "answer", "source_documents": [], "entities_mentioned": []}},
        ),
        ((), "updates", {"generate_follow_ups": {"follow_up_questions": []}}),
    ]
    mock_graph.astream = _make_astream(events)

    with patch("app.dependencies.get_settings", return_value=_mock_settings(enable_agentic_pipeline=True)):
        response = await client.post(
            "/api/v1/query/stream",
            json={"query": "test question"},
        )
    # Should not crash with AttributeError on NoneType
    assert response.status_code == 200

    lines = response.text.strip().split("\n")
    data_lines = [line for line in lines if line.startswith("data: ") and "stage" in line]
    stage_names = [json.loads(line[6:])["stage"] for line in data_lines]
    # The None update should be skipped — no status event for "agent"
    assert "agent" not in stage_names
    # Real nodes still emitted
    assert "extracting_results" in stage_names
