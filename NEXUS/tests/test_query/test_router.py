"""Tests for query and chat API endpoints."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
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
            "entities_mentioned": [
                {"name": "Test Person", "type": "person", "kg_id": None, "connections": 0}
            ],
        }

        # Override dependencies
        from app import dependencies

        async def mock_get_db():
            yield mock_db

        test_app.dependency_overrides[dependencies.get_db] = mock_get_db
        test_app.dependency_overrides[dependencies.get_query_graph] = lambda: mock_graph
        test_app.dependency_overrides[dependencies.get_llm] = lambda: AsyncMock()
        test_app.dependency_overrides[dependencies.get_retriever] = lambda: AsyncMock()
        test_app.dependency_overrides[dependencies.get_graph_service] = lambda: AsyncMock()
        test_app.dependency_overrides[dependencies.get_entity_extractor] = lambda: MagicMock()

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
            "created_at": datetime.now(timezone.utc),
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
