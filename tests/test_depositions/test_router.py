"""Tests for the depositions router endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.schemas import UserRecord
from app.depositions.schemas import (
    DepositionPrepResponse,
    QuestionCategory,
    SuggestedQuestion,
    WitnessProfile,
)

# ---------------------------------------------------------------------------
# Fixtures
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


@pytest.fixture()
async def depo_client():
    """Yield an httpx AsyncClient with the depositions router mounted (flag enabled)."""
    from app import main as main_module
    from app.config import Settings

    async def _noop_lifespan(app):
        yield

    test_settings = Settings(
        enable_deposition_prep=True,
        anthropic_api_key="test",
        openai_api_key="test",
    )

    with (
        patch.object(main_module, "lifespan", _noop_lifespan),
        patch("app.main.get_settings", return_value=test_settings),
    ):
        test_app = main_module.create_app()

        from app.auth.middleware import get_current_user, get_matter_id
        from app.common.rate_limit import rate_limit_ingests, rate_limit_queries

        test_app.dependency_overrides[rate_limit_queries] = lambda: None
        test_app.dependency_overrides[rate_limit_ingests] = lambda: None
        test_app.dependency_overrides[get_current_user] = lambda: _TEST_USER
        test_app.dependency_overrides[get_matter_id] = lambda: _TEST_MATTER_ID

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://testserver",
        ) as client:
            yield client


@pytest.fixture()
async def disabled_client():
    """Yield an httpx AsyncClient with the depositions flag disabled."""
    from app import main as main_module
    from app.config import Settings

    async def _noop_lifespan(app):
        yield

    test_settings = Settings(
        enable_deposition_prep=False,
        anthropic_api_key="test",
        openai_api_key="test",
    )

    with (
        patch.object(main_module, "lifespan", _noop_lifespan),
        patch("app.main.get_settings", return_value=test_settings),
    ):
        test_app = main_module.create_app()

        from app.auth.middleware import get_current_user, get_matter_id
        from app.common.rate_limit import rate_limit_ingests, rate_limit_queries

        test_app.dependency_overrides[rate_limit_queries] = lambda: None
        test_app.dependency_overrides[rate_limit_ingests] = lambda: None
        test_app.dependency_overrides[get_current_user] = lambda: _TEST_USER
        test_app.dependency_overrides[get_matter_id] = lambda: _TEST_MATTER_ID

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://testserver",
        ) as client:
            yield client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_witness() -> WitnessProfile:
    return WitnessProfile(
        name="John Doe",
        entity_type="person",
        document_count=5,
        connection_count=3,
        roles=["defendant"],
    )


def _fake_prep_response() -> DepositionPrepResponse:
    return DepositionPrepResponse(
        witness=_fake_witness(),
        questions=[
            SuggestedQuestion(
                question="What is your relationship with Acme Corp?",
                category=QuestionCategory.relationship,
                basis_document_ids=["doc-1"],
                rationale="Clarify employment.",
            ),
        ],
        document_summaries=[{"document_id": "doc-1", "filename": "doc.pdf", "summary": "Key doc."}],
    )


# ---------------------------------------------------------------------------
# GET /api/v1/depositions/witnesses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_witnesses_success(depo_client: AsyncClient) -> None:
    """GET /depositions/witnesses returns witness list."""
    witnesses = [_fake_witness()]
    with patch(
        "app.depositions.service.DepositionService.list_witnesses",
        new_callable=AsyncMock,
        return_value=(witnesses, 1),
    ):
        response = await depo_client.get("/api/v1/depositions/witnesses")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["witnesses"]) == 1
    assert data["witnesses"][0]["name"] == "John Doe"


@pytest.mark.asyncio
async def test_list_witnesses_requires_auth() -> None:
    """GET /depositions/witnesses returns 401 without auth."""
    from app import main as main_module
    from app.config import Settings

    async def _noop_lifespan(app):
        yield

    test_settings = Settings(
        enable_deposition_prep=True,
        anthropic_api_key="test",
        openai_api_key="test",
    )

    with (
        patch.object(main_module, "lifespan", _noop_lifespan),
        patch("app.main.get_settings", return_value=test_settings),
    ):
        test_app = main_module.create_app()

        # No auth overrides
        from app.common.rate_limit import rate_limit_ingests, rate_limit_queries

        test_app.dependency_overrides[rate_limit_queries] = lambda: None
        test_app.dependency_overrides[rate_limit_ingests] = lambda: None

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/api/v1/depositions/witnesses")

    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_list_witnesses_requires_matter() -> None:
    """GET /depositions/witnesses returns error without matter header."""
    from app import main as main_module
    from app.config import Settings

    async def _noop_lifespan(app):
        yield

    test_settings = Settings(
        enable_deposition_prep=True,
        anthropic_api_key="test",
        openai_api_key="test",
    )

    with (
        patch.object(main_module, "lifespan", _noop_lifespan),
        patch("app.main.get_settings", return_value=test_settings),
    ):
        test_app = main_module.create_app()

        from app.auth.middleware import get_current_user
        from app.common.rate_limit import rate_limit_ingests, rate_limit_queries

        test_app.dependency_overrides[rate_limit_queries] = lambda: None
        test_app.dependency_overrides[rate_limit_ingests] = lambda: None
        test_app.dependency_overrides[get_current_user] = lambda: _TEST_USER
        # No matter_id override

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/api/v1/depositions/witnesses")

    assert response.status_code in (400, 422)


# ---------------------------------------------------------------------------
# POST /api/v1/depositions/prep
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prep_success(depo_client: AsyncClient) -> None:
    """POST /depositions/prep returns a deposition prep package."""
    prep = _fake_prep_response()
    with (
        patch(
            "app.depositions.service.DepositionService.generate_prep_package",
            new_callable=AsyncMock,
            return_value=prep,
        ),
        patch("app.depositions.router.get_llm"),
    ):
        response = await depo_client.post(
            "/api/v1/depositions/prep",
            json={"witness_name": "John Doe", "max_questions": 10},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["witness"]["name"] == "John Doe"
    assert len(data["questions"]) == 1
    assert data["questions"][0]["category"] == "relationship"


@pytest.mark.asyncio
async def test_prep_requires_auth() -> None:
    """POST /depositions/prep returns 401 without auth."""
    from app import main as main_module
    from app.config import Settings

    async def _noop_lifespan(app):
        yield

    test_settings = Settings(
        enable_deposition_prep=True,
        anthropic_api_key="test",
        openai_api_key="test",
    )

    with (
        patch.object(main_module, "lifespan", _noop_lifespan),
        patch("app.main.get_settings", return_value=test_settings),
    ):
        test_app = main_module.create_app()
        from app.common.rate_limit import rate_limit_ingests, rate_limit_queries

        test_app.dependency_overrides[rate_limit_queries] = lambda: None
        test_app.dependency_overrides[rate_limit_ingests] = lambda: None

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/api/v1/depositions/prep",
                json={"witness_name": "John Doe"},
            )

    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_prep_requires_matter() -> None:
    """POST /depositions/prep returns error without matter header."""
    from app import main as main_module
    from app.config import Settings

    async def _noop_lifespan(app):
        yield

    test_settings = Settings(
        enable_deposition_prep=True,
        anthropic_api_key="test",
        openai_api_key="test",
    )

    with (
        patch.object(main_module, "lifespan", _noop_lifespan),
        patch("app.main.get_settings", return_value=test_settings),
    ):
        test_app = main_module.create_app()
        from app.auth.middleware import get_current_user
        from app.common.rate_limit import rate_limit_ingests, rate_limit_queries

        test_app.dependency_overrides[rate_limit_queries] = lambda: None
        test_app.dependency_overrides[rate_limit_ingests] = lambda: None
        test_app.dependency_overrides[get_current_user] = lambda: _TEST_USER

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/api/v1/depositions/prep",
                json={"witness_name": "John Doe"},
            )

    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_prep_validation_error_empty_name(depo_client: AsyncClient) -> None:
    """POST /depositions/prep returns 422 for empty witness name."""
    response = await depo_client.post(
        "/api/v1/depositions/prep",
        json={"witness_name": ""},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_prep_flag_disabled_404(disabled_client: AsyncClient) -> None:
    """POST /depositions/prep returns 404 when feature flag is disabled."""
    response = await disabled_client.post(
        "/api/v1/depositions/prep",
        json={"witness_name": "John Doe"},
    )
    assert response.status_code == 404
