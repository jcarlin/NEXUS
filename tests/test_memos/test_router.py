"""Tests for the memos router endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.schemas import UserRecord
from app.memos.schemas import MemoFormat, MemoResponse, MemoSection

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
async def memo_client():
    """Yield an httpx AsyncClient with the memos router mounted (flag enabled)."""
    from app import main as main_module
    from app.config import Settings

    async def _noop_lifespan(app):
        yield

    test_settings = Settings(
        enable_memo_drafting=True,
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


def _fake_memo_response(**overrides) -> MemoResponse:
    """Build a fake MemoResponse for test patches."""
    defaults = {
        "id": uuid4(),
        "matter_id": _TEST_MATTER_ID,
        "thread_id": None,
        "title": "Test Memo",
        "sections": [MemoSection(heading="Summary", content="Test content.")],
        "format": MemoFormat.MARKDOWN,
        "created_by": _TEST_USER.id,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return MemoResponse(**defaults)


# ---------------------------------------------------------------------------
# POST /api/v1/memos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_memo_success(memo_client: AsyncClient) -> None:
    """POST /memos returns 201 with a generated memo."""
    memo = _fake_memo_response()

    with (
        patch(
            "app.memos.service.MemoService.generate_memo",
            new_callable=AsyncMock,
            return_value=memo,
        ),
        patch("app.memos.router.get_llm"),
    ):
        response = await memo_client.post(
            "/api/v1/memos",
            json={
                "query": "What happened?",
                "matter_id": str(_TEST_MATTER_ID),
            },
        )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Memo"
    assert len(data["sections"]) == 1


@pytest.mark.asyncio
async def test_create_memo_missing_query_and_thread(memo_client: AsyncClient) -> None:
    """POST /memos returns 422 when neither thread_id nor query is provided."""
    response = await memo_client.post(
        "/api/v1/memos",
        json={
            "matter_id": str(_TEST_MATTER_ID),
        },
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/memos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_memos_success(memo_client: AsyncClient) -> None:
    """GET /memos returns paginated list."""
    memo = _fake_memo_response()

    with patch(
        "app.memos.service.MemoService.list_memos",
        new_callable=AsyncMock,
        return_value=([memo], 1),
    ):
        response = await memo_client.get("/api/v1/memos")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1


@pytest.mark.asyncio
async def test_list_memos_empty(memo_client: AsyncClient) -> None:
    """GET /memos returns empty list when no memos exist."""
    with patch(
        "app.memos.service.MemoService.list_memos",
        new_callable=AsyncMock,
        return_value=([], 0),
    ):
        response = await memo_client.get("/api/v1/memos")

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["items"] == []


# ---------------------------------------------------------------------------
# GET /api/v1/memos/{memo_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_memo_not_found(memo_client: AsyncClient) -> None:
    """GET /memos/{id} returns 404 for non-existent memo."""
    with patch(
        "app.memos.service.MemoService.get_memo",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await memo_client.get(f"/api/v1/memos/{uuid4()}")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_memo_success(memo_client: AsyncClient) -> None:
    """GET /memos/{id} returns the memo when found."""
    memo_id = uuid4()
    memo = _fake_memo_response(id=memo_id)

    with patch(
        "app.memos.service.MemoService.get_memo",
        new_callable=AsyncMock,
        return_value=memo,
    ):
        response = await memo_client.get(f"/api/v1/memos/{memo_id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(memo_id)


# ---------------------------------------------------------------------------
# DELETE /api/v1/memos/{memo_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_memo_success(memo_client: AsyncClient) -> None:
    """DELETE /memos/{id} returns 204 on success."""
    with patch(
        "app.memos.service.MemoService.delete_memo",
        new_callable=AsyncMock,
        return_value=True,
    ):
        response = await memo_client.delete(f"/api/v1/memos/{uuid4()}")

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_memo_not_found(memo_client: AsyncClient) -> None:
    """DELETE /memos/{id} returns 404 when memo does not exist."""
    with patch(
        "app.memos.service.MemoService.delete_memo",
        new_callable=AsyncMock,
        return_value=False,
    ):
        response = await memo_client.delete(f"/api/v1/memos/{uuid4()}")

    assert response.status_code == 404
