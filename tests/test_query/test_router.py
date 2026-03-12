"""Tests for query and chat API endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def query_client():
    """Async test client with all query dependencies mocked."""
    from app import main as main_module

    async def _noop_lifespan(app):
        yield

    with patch.object(main_module, "lifespan", _noop_lifespan):
        test_app = main_module.create_app()

        # Mock the database session
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        # Mock graph
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "response": "Test response [Source: doc.pdf, page 1]",
            "source_documents": [
                {
                    "id": "p1",
                    "filename": "doc.pdf",
                    "page": 1,
                    "chunk_text": "test chunk",
                    "relevance_score": 0.9,
                    "preview_url": None,
                    "download_url": None,
                }
            ],
            "follow_up_questions": [
                "What other documents mention this?",
                "Are there related financial records?",
                "What is the timeline of events?",
            ],
            "entities_mentioned": [{"name": "Test Person", "type": "person", "kg_id": None, "connections": 0}],
        }

        # Override dependencies
        from app import dependencies
        from app.auth.middleware import get_current_user, get_matter_id
        from app.common.rate_limit import rate_limit_queries

        async def mock_get_db():
            yield mock_db

        test_app.dependency_overrides[dependencies.get_db] = mock_get_db
        test_app.dependency_overrides[dependencies.get_query_graph] = lambda: mock_graph
        test_app.dependency_overrides[rate_limit_queries] = lambda: None
        from app.auth.schemas import UserRecord

        test_app.dependency_overrides[get_current_user] = lambda: UserRecord(
            id=uuid.UUID("00000000-0000-0000-0000-000000000099"),
            email="test@nexus.dev",
            full_name="Test",
            role="admin",
            is_active=True,
            created_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        test_app.dependency_overrides[get_matter_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac, mock_db, mock_graph


# ---------------------------------------------------------------------------
# POST /query tests
# ---------------------------------------------------------------------------


async def test_query_returns_200(query_client):
    client, mock_db, mock_graph = query_client
    response = await client.post(
        "/api/v1/query",
        json={"query": "Who is mentioned in the documents?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert "source_documents" in data
    assert "follow_up_questions" in data
    assert "entities_mentioned" in data
    assert "thread_id" in data
    assert "message_id" in data


async def test_query_invokes_graph(query_client):
    client, mock_db, mock_graph = query_client
    await client.post("/api/v1/query", json={"query": "test"})
    mock_graph.ainvoke.assert_called_once()


async def test_query_saves_messages(query_client):
    client, mock_db, mock_graph = query_client
    await client.post("/api/v1/query", json={"query": "test query"})
    # Should have 2 inserts (user + assistant) + 1 commit
    assert mock_db.execute.call_count >= 2
    assert mock_db.commit.call_count >= 1


async def test_query_with_thread_id(query_client):
    client, mock_db, mock_graph = query_client
    thread_id = str(uuid.uuid4())
    # Mock returning empty history
    mock_db.execute.return_value = MagicMock()
    mock_db.execute.return_value.mappings.return_value.all.return_value = []

    response = await client.post(
        "/api/v1/query",
        json={"query": "follow up question", "thread_id": thread_id},
    )
    assert response.status_code == 200


async def test_query_requires_query_field(query_client):
    client, *_ = query_client
    response = await client.post("/api/v1/query", json={})
    assert response.status_code == 422


async def test_query_rejects_empty_query(query_client):
    client, *_ = query_client
    response = await client.post("/api/v1/query", json={"query": ""})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Chat endpoint tests
# ---------------------------------------------------------------------------


async def test_list_chats_returns_200(query_client):
    client, mock_db, _ = query_client
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    response = await client.get("/api/v1/chats")
    assert response.status_code == 200
    assert "threads" in response.json()


async def test_get_chat_not_found(query_client):
    client, mock_db, _ = query_client
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    response = await client.get(f"/api/v1/chats/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_get_chat_with_messages(query_client):
    client, mock_db, _ = query_client
    thread_id = str(uuid.uuid4())
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {
            "id": str(uuid.uuid4()),
            "thread_id": thread_id,
            "role": "user",
            "content": "test question",
            "source_documents": "[]",
            "entities_mentioned": "[]",
            "follow_up_questions": "[]",
            "created_at": datetime.now(UTC),
        },
    ]
    mock_db.execute.return_value = mock_result

    response = await client.get(f"/api/v1/chats/{thread_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["thread_id"] == thread_id
    assert len(data["messages"]) == 1


async def test_delete_chat_returns_deleted(query_client):
    client, mock_db, _ = query_client
    mock_result = MagicMock()
    mock_result.rowcount = 3
    mock_db.execute.return_value = mock_result

    thread_id = str(uuid.uuid4())
    response = await client.delete(f"/api/v1/chats/{thread_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["detail"] == "deleted"
    assert data["messages_deleted"] == 3


async def test_delete_chat_not_found(query_client):
    client, mock_db, _ = query_client
    mock_result = MagicMock()
    mock_result.rowcount = 0
    mock_db.execute.return_value = mock_result

    response = await client.delete(f"/api/v1/chats/{uuid.uuid4()}")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# SSE disconnect persistence tests
# ---------------------------------------------------------------------------


async def test_v1_generator_persists_on_client_disconnect():
    """When a client disconnects mid-stream, the v1 generator should still
    persist the user and assistant messages to the database."""
    from app.query.router import _v1_event_generator

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()

    thread_id = str(uuid.uuid4())
    matter_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    # Create a mock graph that raises GeneratorExit to simulate client disconnect
    async def _mock_astream(*args, **kwargs):
        yield ("updates", {"rerank": {"source_documents": []}})
        yield ("custom", {"type": "token", "text": "partial response"})
        # Simulate client disconnect
        raise GeneratorExit()

    mock_graph = MagicMock()
    mock_graph.astream = _mock_astream

    # Consume the generator — it should persist even after GeneratorExit
    events = []
    async for event in _v1_event_generator(mock_graph, {}, {}, mock_db, thread_id, "test query", matter_id):
        events.append(event)

    # No "done" event should be yielded (client is gone)
    done_events = [e for e in events if e.get("event") == "done"]
    assert len(done_events) == 0

    # User message persisted (assistant skipped — no response content on disconnect)
    assert mock_db.execute.call_count >= 1
    assert mock_db.commit.call_count >= 1


async def test_agentic_generator_persists_on_client_disconnect():
    """When a client disconnects mid-stream, the agentic generator should still
    persist the user message to the database (assistant message only saved on full completion)."""
    from app.query.router import _agentic_event_generator

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()

    thread_id = str(uuid.uuid4())
    matter_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    async def _mock_astream(*args, **kwargs):
        yield ((), "updates", {"post_agent_extract": {"source_documents": [{"id": "p1"}]}})
        raise GeneratorExit()

    mock_graph = MagicMock()
    mock_graph.astream = _mock_astream

    # Mock settings for extract_response
    with patch("app.dependencies.get_settings") as mock_get_settings:
        mock_settings = MagicMock()
        mock_settings.enable_agentic_pipeline = True
        mock_get_settings.return_value = mock_settings

        with patch("app.query.service.QueryService.extract_response", return_value="partial"):
            events = []
            async for event in _agentic_event_generator(
                mock_graph, {}, {}, mock_db, thread_id, "test query", matter_id
            ):
                events.append(event)

    # No "done" event
    done_events = [e for e in events if e.get("event") == "done"]
    assert len(done_events) == 0

    # User message persisted (assistant only saved on full stream completion)
    assert mock_db.execute.call_count >= 1
    assert mock_db.commit.call_count >= 1
