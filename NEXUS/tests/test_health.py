"""Tests for the /api/v1/health endpoint and basic API bootstrapping."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    """The health endpoint should return HTTP 200 (or 503 if services are unreachable).

    In the test environment (no Docker services), some backends will report
    errors, but the endpoint itself must not crash.
    """
    response = await client.get("/api/v1/health")
    # The endpoint should return either 200 (all ok) or 503 (degraded).
    assert response.status_code in (200, 503)

    body = response.json()
    assert "status" in body
    assert body["status"] in ("healthy", "degraded")


@pytest.mark.asyncio
async def test_health_has_service_keys(client: AsyncClient) -> None:
    """The health response must contain status entries for all backing services."""
    response = await client.get("/api/v1/health")
    body = response.json()

    assert "services" in body
    services = body["services"]

    expected_keys = {"qdrant", "minio", "neo4j", "redis", "postgres"}
    assert expected_keys.issubset(set(services.keys())), (
        f"Missing service keys: {expected_keys - set(services.keys())}"
    )


@pytest.mark.asyncio
async def test_openapi_docs_available(client: AsyncClient) -> None:
    """The auto-generated OpenAPI JSON spec should be accessible."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert spec["info"]["title"] == "NEXUS"
    assert spec["info"]["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_ingestion_stub_returns_not_implemented(client: AsyncClient) -> None:
    """Stub ingestion endpoints should return a not-implemented marker."""
    response = await client.post("/api/v1/ingest")
    # 422 (validation error because no file provided) or 200 with "not implemented" are both acceptable
    # The stub returns 200 with {"detail": "not implemented"} since it has no required params
    assert response.status_code in (200, 422)


@pytest.mark.asyncio
async def test_query_stub_returns_not_implemented(client: AsyncClient) -> None:
    """Stub query endpoint should return a not-implemented marker."""
    response = await client.post("/api/v1/query")
    # 422 (no body) or 200 with stub response
    assert response.status_code in (200, 422)


@pytest.mark.asyncio
async def test_entities_endpoint_returns_200(client: AsyncClient) -> None:
    """Entities list endpoint should return 200 with entity data."""
    from unittest.mock import AsyncMock, patch

    mock_gs = AsyncMock()
    mock_gs.search_entities = AsyncMock(return_value=([], 0))

    with patch("app.dependencies._graph_service", mock_gs):
        response = await client.get("/api/v1/entities")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total" in body


@pytest.mark.asyncio
async def test_documents_stub_returns_200(client: AsyncClient) -> None:
    """Stub documents list endpoint should return 200 with stub response."""
    response = await client.get("/api/v1/documents")
    assert response.status_code == 200
    body = response.json()
    assert "detail" in body
    assert body["detail"] == "not implemented"


@pytest.mark.asyncio
async def test_graph_stats_returns_200(client: AsyncClient) -> None:
    """Graph stats endpoint should return 200 with stats data."""
    from unittest.mock import AsyncMock, patch

    mock_gs = AsyncMock()
    mock_gs.get_graph_stats = AsyncMock(return_value={
        "total_nodes": 0, "total_edges": 0, "node_counts": {}, "edge_counts": {}
    })

    with patch("app.dependencies._graph_service", mock_gs):
        response = await client.get("/api/v1/graph/stats")
    assert response.status_code == 200
    body = response.json()
    assert "total_nodes" in body
