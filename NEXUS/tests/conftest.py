"""Shared pytest fixtures for NEXUS tests.

The test client is created WITHOUT starting backing services (Postgres, Redis,
Qdrant, Neo4j, MinIO).  Dependency overrides and mocks are used so that the
FastAPI app can be exercised purely in-process.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings


# ---------------------------------------------------------------------------
# Test settings (no real service connections)
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_settings() -> Settings:
    """Return a ``Settings`` instance with safe test defaults."""
    return Settings(
        anthropic_api_key="test-key",
        openai_api_key="test-key",
        llm_provider="anthropic",
        postgres_url="postgresql+asyncpg://nexus:test@localhost:5432/nexus_test",
        postgres_url_sync="postgresql://nexus:test@localhost:5432/nexus_test",
        redis_url="redis://localhost:6379/15",
        qdrant_url="http://localhost:6333",
        neo4j_uri="bolt://localhost:7687",
        neo4j_password="test",
        minio_endpoint="localhost:9000",
        minio_access_key="test",
        minio_secret_key="test",
    )


# ---------------------------------------------------------------------------
# Async HTTP client backed by the FastAPI ASGI app
# ---------------------------------------------------------------------------

@pytest.fixture()
async def client() -> AsyncIterator[AsyncClient]:
    """Yield an ``httpx.AsyncClient`` wired directly to the NEXUS app.

    All external service dependencies are patched out so that tests run
    without Docker infrastructure.
    """
    # Patch the lifespan so it does not try to connect to real services.
    from app import main as main_module

    async def _noop_lifespan(app):
        yield

    with patch.object(main_module, "lifespan", _noop_lifespan):
        # Re-create the app with the patched lifespan
        test_app = main_module.create_app()

        # Override rate limiters to no-op so tests aren't blocked
        from app.common.rate_limit import rate_limit_ingests, rate_limit_queries

        test_app.dependency_overrides[rate_limit_queries] = lambda: None
        test_app.dependency_overrides[rate_limit_ingests] = lambda: None

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac
