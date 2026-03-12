"""Tests for the entity API endpoints (M3 — working implementations)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.dependencies import get_graph_service


@pytest.mark.asyncio
async def test_list_entities(client: AsyncClient) -> None:
    """GET /entities should return paginated entity list."""
    mock_gs = AsyncMock()
    mock_gs.search_entities = AsyncMock(
        return_value=(
            [{"name": "Alice", "type": "person", "mention_count": 3}],
            1,
        )
    )

    app = client._transport.app
    app.dependency_overrides[get_graph_service] = lambda: mock_gs
    try:
        response = await client.get("/api/v1/entities")
    finally:
        app.dependency_overrides.pop(get_graph_service, None)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["name"] == "Alice"


@pytest.mark.asyncio
async def test_get_entity(client: AsyncClient) -> None:
    """GET /entities/{name} should return entity details."""
    mock_gs = AsyncMock()
    mock_gs.get_entity_by_name = AsyncMock(
        return_value={"name": "Alice", "type": "person", "mention_count": 5, "aliases": []}
    )

    app = client._transport.app
    app.dependency_overrides[get_graph_service] = lambda: mock_gs
    try:
        response = await client.get("/api/v1/entities/Alice")
    finally:
        app.dependency_overrides.pop(get_graph_service, None)

    assert response.status_code == 200
    assert response.json()["name"] == "Alice"


@pytest.mark.asyncio
async def test_get_entity_not_found(client: AsyncClient) -> None:
    """GET /entities/{name} for unknown entity should return 404."""
    mock_gs = AsyncMock()
    mock_gs.get_entity_by_name = AsyncMock(return_value=None)

    app = client._transport.app
    app.dependency_overrides[get_graph_service] = lambda: mock_gs
    try:
        response = await client.get("/api/v1/entities/NonExistent")
    finally:
        app.dependency_overrides.pop(get_graph_service, None)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_graph_stats(client: AsyncClient) -> None:
    """GET /graph/stats should return node and edge counts."""
    mock_gs = AsyncMock()
    mock_gs.get_graph_stats = AsyncMock(
        return_value={
            "total_nodes": 100,
            "total_edges": 250,
            "node_counts": {"Entity": 80, "Document": 20},
            "edge_counts": {"MENTIONED_IN": 200, "PART_OF": 50},
        }
    )

    app = client._transport.app
    app.dependency_overrides[get_graph_service] = lambda: mock_gs
    try:
        response = await client.get("/api/v1/graph/stats")
    finally:
        app.dependency_overrides.pop(get_graph_service, None)

    assert response.status_code == 200
    body = response.json()
    assert body["total_nodes"] == 100
    assert body["total_edges"] == 250


@pytest.mark.asyncio
async def test_graph_explore_rejects_write_queries(client: AsyncClient) -> None:
    """GET /graph/explore should reject queries with write keywords."""
    mock_gs = AsyncMock()

    app = client._transport.app
    app.dependency_overrides[get_graph_service] = lambda: mock_gs
    try:
        response = await client.get(
            "/api/v1/graph/explore",
            params={"cypher": "CREATE (n:Entity {name: 'hack'})"},
        )
    finally:
        app.dependency_overrides.pop(get_graph_service, None)

    assert response.status_code == 400
    assert "Write operations" in response.json()["detail"]


@pytest.mark.asyncio
async def test_graph_timeline(client: AsyncClient) -> None:
    """GET /graph/timeline/{entity} should return timeline events with co-mentioned entities."""
    mock_gs = AsyncMock()
    mock_gs.get_entity_timeline = AsyncMock(
        return_value=[
            {
                "date": "2024-01-15T00:00:00",
                "description": "Mentioned in report.pdf (page 3) [pdf]",
                "entities": ["Bob", "Acme Corp"],
                "document_source": "report.pdf",
            }
        ]
    )

    app = client._transport.app
    app.dependency_overrides[get_graph_service] = lambda: mock_gs
    try:
        response = await client.get("/api/v1/graph/timeline/Alice")
    finally:
        app.dependency_overrides.pop(get_graph_service, None)

    assert response.status_code == 200
    body = response.json()
    assert body["entity"] == "Alice"
    assert len(body["events"]) == 1
    assert body["events"][0]["entities"] == ["Bob", "Acme Corp"]
