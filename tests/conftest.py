"""Shared pytest fixtures for NEXUS tests.

The test client is created WITHOUT starting backing services (Postgres, Redis,
Qdrant, Neo4j, MinIO).  Dependency overrides and mocks are used so that the
FastAPI app can be exercised purely in-process.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings

# ---------------------------------------------------------------------------
# Fake user / matter used by all existing tests
# ---------------------------------------------------------------------------

_TEST_USER = {
    "id": UUID("00000000-0000-0000-0000-000000000099"),
    "email": "test@nexus.dev",
    "full_name": "Test User",
    "role": "admin",
    "is_active": True,
    "password_hash": "$2b$12$fake",
    "api_key_hash": None,
    "created_at": "2025-01-01T00:00:00+00:00",
    "updated_at": "2025-01-01T00:00:00+00:00",
}

_TEST_MATTER_ID = UUID("00000000-0000-0000-0000-000000000001")


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

    Auth dependencies (``get_current_user`` and ``get_matter_id``) are
    overridden to always return a test user and default matter, so that
    existing tests don't need auth headers.
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

        # Override auth dependencies so all existing tests pass without auth headers
        from app.auth.middleware import get_current_user, get_matter_id

        test_app.dependency_overrides[get_current_user] = lambda: _TEST_USER
        test_app.dependency_overrides[get_matter_id] = lambda: _TEST_MATTER_ID

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac


@pytest.fixture()
async def unauthed_client() -> AsyncIterator[AsyncClient]:
    """Yield an ``httpx.AsyncClient`` WITHOUT auth overrides.

    Used by auth-specific tests to exercise real auth middleware.
    """
    from app import main as main_module

    async def _noop_lifespan(app):
        yield

    with patch.object(main_module, "lifespan", _noop_lifespan):
        test_app = main_module.create_app()

        from app.common.rate_limit import rate_limit_ingests, rate_limit_queries

        test_app.dependency_overrides[rate_limit_queries] = lambda: None
        test_app.dependency_overrides[rate_limit_ingests] = lambda: None

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac
