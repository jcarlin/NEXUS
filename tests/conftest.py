"""Shared pytest fixtures for NEXUS tests.

The test client is created WITHOUT starting backing services (Postgres, Redis,
Qdrant, Neo4j, MinIO).  Dependency overrides and mocks are used so that the
FastAPI app can be exercised purely in-process.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.schemas import UserRecord
from app.config import Settings

# ---------------------------------------------------------------------------
# Fake user / matter used by all existing tests
# ---------------------------------------------------------------------------

_TEST_USER = UserRecord(
    id=UUID("00000000-0000-0000-0000-000000000099"),
    email="test@nexus.dev",
    full_name="Test User",
    role="admin",
    is_active=True,
    password_hash="$2b$12$fake",
    api_key_hash=None,
    created_at=datetime(2025, 1, 1, tzinfo=UTC),
    updated_at=datetime(2025, 1, 1, tzinfo=UTC),
)

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
# Session-scoped app — created once, reused by all tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def _test_app():
    """Build the FastAPI app once per session with noop lifespan."""
    from app import main as main_module

    async def _noop_lifespan(app):
        yield

    with patch.object(main_module, "lifespan", _noop_lifespan):
        app = main_module.create_app()

    from app.auth.middleware import get_current_user, get_matter_id
    from app.common.rate_limit import rate_limit_ingests, rate_limit_queries

    app.dependency_overrides[rate_limit_queries] = lambda: None
    app.dependency_overrides[rate_limit_ingests] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_matter_id] = lambda: _TEST_MATTER_ID

    return app


# ---------------------------------------------------------------------------
# Async HTTP clients backed by the shared app
# ---------------------------------------------------------------------------


@pytest.fixture()
async def client(_test_app) -> AsyncIterator[AsyncClient]:
    """Function-scoped client — reuses session app, resets overrides after each test."""
    saved = dict(_test_app.dependency_overrides)
    transport = ASGITransport(app=_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    _test_app.dependency_overrides = saved


@pytest.fixture()
async def unauthed_client(_test_app) -> AsyncIterator[AsyncClient]:
    """Client without auth overrides — restores after test."""
    saved = dict(_test_app.dependency_overrides)
    from app.auth.middleware import get_current_user, get_matter_id

    _test_app.dependency_overrides.pop(get_current_user, None)
    _test_app.dependency_overrides.pop(get_matter_id, None)
    transport = ASGITransport(app=_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    _test_app.dependency_overrides = saved
