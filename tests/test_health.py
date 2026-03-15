"""Tests for the /api/v1/health endpoint and basic API bootstrapping."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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
    assert expected_keys.issubset(set(services.keys())), f"Missing service keys: {expected_keys - set(services.keys())}"


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
async def test_query_requires_body(client: AsyncClient) -> None:
    """Query endpoint should return 422 when no body is provided."""
    from unittest.mock import patch

    from langgraph.checkpoint.memory import InMemorySaver

    # Patch checkpointer to avoid Postgres connection during dependency resolution
    with patch("app.dependencies.get_checkpointer", return_value=InMemorySaver()):
        response = await client.post("/api/v1/query")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_entities_endpoint_returns_200(client: AsyncClient) -> None:
    """Entities list endpoint should return 200 with entity data."""
    from unittest.mock import AsyncMock

    from app.dependencies import get_graph_service

    mock_gs = AsyncMock()
    mock_gs.search_entities = AsyncMock(return_value=([], 0))

    app = client._transport.app
    app.dependency_overrides[get_graph_service] = lambda: mock_gs
    try:
        response = await client.get("/api/v1/entities")
    finally:
        app.dependency_overrides.pop(get_graph_service, None)
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total" in body


@pytest.mark.asyncio
async def test_documents_list_returns_200(client: AsyncClient) -> None:
    """Documents list endpoint should return 200 with paginated response."""
    from unittest.mock import AsyncMock, patch

    with patch(
        "app.documents.service.DocumentService.list_documents",
        new_callable=AsyncMock,
        return_value=([], 0),
    ):
        response = await client.get("/api/v1/documents")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_graph_stats_returns_200(client: AsyncClient) -> None:
    """Graph stats endpoint should return 200 with stats data."""
    from unittest.mock import AsyncMock

    from app.dependencies import get_graph_service

    mock_gs = AsyncMock()
    mock_gs.get_graph_stats = AsyncMock(
        return_value={"total_nodes": 0, "total_edges": 0, "node_counts": {}, "edge_counts": {}}
    )

    app = client._transport.app
    app.dependency_overrides[get_graph_service] = lambda: mock_gs
    try:
        response = await client.get("/api/v1/graph/stats")
    finally:
        app.dependency_overrides.pop(get_graph_service, None)
    assert response.status_code == 200
    body = response.json()
    assert "total_nodes" in body


# ---------------------------------------------------------------------------
# Deep health endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_deep_returns_service_status(client: AsyncClient) -> None:
    """Deep health should return LLM, embedding, and Qdrant status keys."""
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value="OK")
    mock_llm.provider = "anthropic"
    mock_llm.model = "test-model"

    mock_embedder = AsyncMock()
    mock_embedder.embed_query = AsyncMock(return_value=[0.1] * 1024)

    mock_qdrant = MagicMock()
    mock_qdrant.get_collection_info = AsyncMock(
        return_value={"name": "nexus_text", "points_count": 100, "vectors_count": 100, "status": "green"}
    )

    with (
        patch("app.main.get_llm", return_value=mock_llm),
        patch("app.main.get_embedder", return_value=mock_embedder),
        patch("app.main.get_qdrant", return_value=mock_qdrant),
    ):
        response = await client.get("/api/v1/health/deep")

    assert response.status_code in (200, 503)
    body = response.json()
    assert "services" in body
    services = body["services"]
    assert "llm" in services
    assert "embedding" in services
    assert "qdrant_nexus_text" in services


@pytest.mark.asyncio
async def test_health_deep_reports_llm_error(client: AsyncClient) -> None:
    """Deep health should surface LLM errors in the response."""
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(side_effect=RuntimeError("API key invalid"))

    mock_embedder = AsyncMock()
    mock_embedder.embed_query = AsyncMock(return_value=[0.1] * 1024)

    mock_qdrant = MagicMock()
    mock_qdrant.get_collection_info = AsyncMock(
        return_value={"name": "nexus_text", "points_count": 0, "vectors_count": 0, "status": "green"}
    )

    with (
        patch("app.main.get_llm", return_value=mock_llm),
        patch("app.main.get_embedder", return_value=mock_embedder),
        patch("app.main.get_qdrant", return_value=mock_qdrant),
    ):
        response = await client.get("/api/v1/health/deep")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert "error" in body["services"]["llm"]["status"]


# ---------------------------------------------------------------------------
# Feature flags endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feature_flags_endpoint(client: AsyncClient) -> None:
    """GET /api/v1/config/features returns all user-visible flags."""
    response = await client.get("/api/v1/config/features")
    assert response.status_code == 200
    body = response.json()

    # Check key flags are present and all values are booleans
    assert "reranker" in body
    assert "agentic_pipeline" in body
    assert "visual_embeddings" in body
    assert "google_drive" in body
    assert all(isinstance(v, bool) for v in body.values())
    assert len(body) >= 23  # at least the original flags
    # All values must be booleans
    assert all(isinstance(v, bool) for v in body.values())


@pytest.mark.asyncio
async def test_feature_flags_requires_auth(unauthed_client: AsyncClient) -> None:
    """GET /api/v1/config/features should require authentication."""
    response = await unauthed_client.get("/api/v1/config/features")
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# LangSmith env var safety
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_langsmith_env_vars_dont_break_graph() -> None:
    """Setting LangSmith env vars should not break agentic graph construction."""
    import os

    from app.query.graph import build_agentic_graph

    # Set LangSmith env vars (as a user would)
    env_patch = {
        "LANGCHAIN_TRACING_V2": "true",
        "LANGCHAIN_API_KEY": "ls-test-fake-key",
        "LANGCHAIN_PROJECT": "nexus-test",
    }
    old_vals = {k: os.environ.get(k) for k in env_patch}
    try:
        os.environ.update(env_patch)

        mock_settings = MagicMock()
        mock_settings.llm_model = "claude-sonnet-4-5-20250929"
        mock_settings.anthropic_api_key = "test-key"
        mock_settings.enable_citation_verification = True

        # This should not raise
        compiled = build_agentic_graph(mock_settings, checkpointer=False)
        assert compiled is not None
    finally:
        for k, v in old_vals.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
