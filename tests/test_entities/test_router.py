"""Tests for the entity API endpoints (M3 — working implementations)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


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

    with patch("app.dependencies._graph_service", mock_gs):
        response = await client.get("/api/v1/entities")

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

    with patch("app.dependencies._graph_service", mock_gs):
        response = await client.get("/api/v1/entities/Alice")

    assert response.status_code == 200
    assert response.json()["name"] == "Alice"


@pytest.mark.asyncio
async def test_get_entity_not_found(client: AsyncClient) -> None:
    """GET /entities/{name} for unknown entity should return 404."""
    mock_gs = AsyncMock()
    mock_gs.get_entity_by_name = AsyncMock(return_value=None)

    with patch("app.dependencies._graph_service", mock_gs):
        response = await client.get("/api/v1/entities/NonExistent")

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

    with patch("app.dependencies._graph_service", mock_gs):
        response = await client.get("/api/v1/graph/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["total_nodes"] == 100
    assert body["total_edges"] == 250


@pytest.mark.asyncio
async def test_graph_explore_rejects_write_queries(client: AsyncClient) -> None:
    """GET /graph/explore should reject queries with write keywords."""
    mock_gs = AsyncMock()

    with patch("app.dependencies._graph_service", mock_gs):
        response = await client.get(
            "/api/v1/graph/explore",
            params={"cypher": "CREATE (n:Entity {name: 'hack'})"},
        )

    assert response.status_code == 400
    assert "Write operations" in response.json()["detail"]
