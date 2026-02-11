"""Tests for PostgresCheckpointer integration with the query pipeline."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture()
async def checkpointer_client():
    """Async test client with checkpointer and graph mocked."""
    from app import main as main_module

    async def _noop_lifespan(app):
        yield

    with patch.object(main_module, "lifespan", _noop_lifespan):
        test_app = main_module.create_app()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "response": "Test response",
            "source_documents": [],
            "follow_up_questions": [],
            "entities_mentioned": [],
        })

        from app import dependencies

        async def mock_get_db():
            yield mock_db

        test_app.dependency_overrides[dependencies.get_db] = mock_get_db
        test_app.dependency_overrides[dependencies.get_query_graph] = lambda: mock_graph
        # Override rate limiter to no-op
        from app.common.rate_limit import rate_limit_queries
        test_app.dependency_overrides[rate_limit_queries] = lambda: None

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac, mock_db, mock_graph


@pytest.mark.asyncio
async def test_graph_compiled_with_checkpointer():
    """get_query_graph() should compile with a checkpointer."""
    mock_checkpointer = MagicMock()
    mock_graph_builder = MagicMock()
    mock_compiled = MagicMock()
    mock_graph_builder.compile.return_value = mock_compiled

    with (
        patch("app.dependencies.get_checkpointer", return_value=mock_checkpointer),
        patch("app.dependencies.get_llm", return_value=MagicMock()),
        patch("app.dependencies.get_retriever", return_value=MagicMock()),
        patch("app.dependencies.get_graph_service", return_value=MagicMock()),
        patch("app.dependencies.get_entity_extractor", return_value=MagicMock()),
        patch("app.query.graph.build_graph", return_value=mock_graph_builder),
    ):
        # Reset the singleton so it rebuilds
        import app.dependencies as deps
        deps._query_graph = None

        try:
            result = deps.get_query_graph()
            mock_graph_builder.compile.assert_called_once_with(checkpointer=mock_checkpointer)
            assert result is mock_compiled
        finally:
            deps._query_graph = None


@pytest.mark.asyncio
async def test_query_passes_thread_id_config(checkpointer_client):
    """POST /query should pass thread_id in the config to ainvoke."""
    client, mock_db, mock_graph = checkpointer_client
    thread_id = str(uuid.uuid4())

    await client.post(
        "/api/v1/query",
        json={"query": "test question", "thread_id": thread_id},
    )

    mock_graph.ainvoke.assert_called_once()
    call_args = mock_graph.ainvoke.call_args
    config = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("config")
    assert config["configurable"]["thread_id"] == thread_id


@pytest.mark.asyncio
async def test_query_generates_thread_id_when_missing(checkpointer_client):
    """POST /query without thread_id should auto-generate a UUID in config."""
    client, mock_db, mock_graph = checkpointer_client

    await client.post("/api/v1/query", json={"query": "test question"})

    mock_graph.ainvoke.assert_called_once()
    call_args = mock_graph.ainvoke.call_args
    config = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("config")
    thread_id = config["configurable"]["thread_id"]
    # Should be a valid UUID
    uuid.UUID(thread_id)
