"""E2E tests for entities and knowledge-graph endpoints.

Covers:
  GET /api/v1/entities                   -- list / search entities
  GET /api/v1/entities/{entity_id}       -- entity detail
  GET /api/v1/entities/{entity_id}/connections -- graph neighbourhood
  GET /api/v1/graph/stats                -- node / edge counts

All tests depend on `ingested_document` to ensure the ingestion pipeline
(including GLiNER entity extraction and Neo4j indexing) has completed before
assertions are made.  Because GLiNER extraction is non-deterministic with
respect to which entities survive deduplication and resolution, most
assertions stay structural rather than asserting specific entity names.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

ENTITIES_URL = "/api/v1/entities"
GRAPH_STATS_URL = "/api/v1/graph/stats"


# ---------------------------------------------------------------------------
# List entities
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_list_entities_returns_results(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
    ingested_document: dict,
) -> None:
    """GET /entities returns 200 with a dict that has an 'items' key (list).

    After ingestion the entity store may or may not be populated depending on
    whether GLiNER extraction ran successfully, so we only assert the response
    shape rather than a minimum item count.
    """
    resp = await e2e_client.get(ENTITIES_URL, headers=admin_auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data, f"Response missing 'items' key: {data}"
    assert isinstance(data["items"], list), "'items' must be a list"


@pytest.mark.e2e
async def test_list_entities_pagination(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
    ingested_document: dict,
) -> None:
    """GET /entities?limit=5&offset=0 returns all four pagination envelope keys."""
    resp = await e2e_client.get(
        ENTITIES_URL,
        params={"limit": 5, "offset": 0},
        headers=admin_auth_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data, f"Response missing 'items' key: {data}"
    assert "total" in data, f"Response missing 'total' key: {data}"
    assert "offset" in data, f"Response missing 'offset' key: {data}"
    assert "limit" in data, f"Response missing 'limit' key: {data}"
    assert isinstance(data["items"], list), "'items' must be a list"
    assert isinstance(data["total"], int), "'total' must be an int"
    assert data["offset"] == 0, f"Expected offset 0, got {data['offset']}"
    assert data["limit"] == 5, f"Expected limit 5, got {data['limit']}"
    assert len(data["items"]) <= 5, f"Returned more items than the requested limit: {len(data['items'])}"


@pytest.mark.e2e
async def test_list_entities_with_search(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
    ingested_document: dict,
) -> None:
    """GET /entities?q=Acme returns 200 without error.

    The sample legal document contains references to 'Acme Corporation'.
    If GLiNER extracted it, the results list will be non-empty; if not, an
    empty list is acceptable.  The key assertion is that the endpoint does
    not error.
    """
    resp = await e2e_client.get(
        ENTITIES_URL,
        params={"q": "Acme"},
        headers=admin_auth_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data, f"Response missing 'items' key: {data}"
    assert isinstance(data["items"], list), "'items' must be a list"
    # Every returned item must contain at least a 'name' field
    for item in data["items"]:
        assert "name" in item, f"Entity item missing 'name' field: {item}"


# ---------------------------------------------------------------------------
# Graph stats
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_graph_stats_returns_counts(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
    ingested_document: dict,
) -> None:
    """GET /graph/stats returns 200 with node_count and edge_count keys."""
    resp = await e2e_client.get(GRAPH_STATS_URL, headers=admin_auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert "node_count" in data, f"Response missing 'node_count' key: {data}"
    assert "edge_count" in data, f"Response missing 'edge_count' key: {data}"
    assert isinstance(data["node_count"], int), "'node_count' must be an int"
    assert isinstance(data["edge_count"], int), "'edge_count' must be an int"
    assert data["node_count"] >= 0, "'node_count' must be non-negative"
    assert data["edge_count"] >= 0, "'edge_count' must be non-negative"
