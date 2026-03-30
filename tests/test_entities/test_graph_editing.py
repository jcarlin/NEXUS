"""Tests for interactive graph editing endpoints (T3-5).

Tests cover CRUD operations on entities and relationships via the API,
including role-based access control and matter scoping.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.schemas import UserRecord
from app.dependencies import get_graph_service

_TEST_MATTER_ID = UUID("00000000-0000-0000-0000-000000000001")
_OTHER_MATTER_ID = UUID("00000000-0000-0000-0000-000000000099")

_REVIEWER_USER = UserRecord(
    id=UUID("00000000-0000-0000-0000-000000000088"),
    email="reviewer@nexus.dev",
    full_name="Reviewer User",
    role="reviewer",
    is_active=True,
    password_hash="$2b$12$fake",
    api_key_hash=None,
    created_at=datetime(2025, 1, 1, tzinfo=UTC),
    updated_at=datetime(2025, 1, 1, tzinfo=UTC),
)


@pytest.fixture()
async def reviewer_client(_test_app) -> AsyncIterator[AsyncClient]:
    """Client with reviewer role (non-admin, non-attorney)."""
    from app.auth.middleware import get_current_user, get_matter_id

    saved = dict(_test_app.dependency_overrides)
    _test_app.dependency_overrides[get_current_user] = lambda: _REVIEWER_USER
    _test_app.dependency_overrides[get_matter_id] = lambda: _TEST_MATTER_ID
    transport = ASGITransport(app=_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    _test_app.dependency_overrides = saved


def _mock_gs() -> AsyncMock:
    """Create a mock GraphService with default stubs."""
    gs = AsyncMock()
    gs.get_entity_by_name = AsyncMock(
        return_value={"name": "Alice", "type": "person", "mention_count": 5, "aliases": []}
    )
    return gs


def _apply_gs(client: AsyncClient, mock_gs: AsyncMock) -> None:
    """Override GraphService dependency on the test app."""
    app = client._transport.app  # type: ignore[union-attr]
    app.dependency_overrides[get_graph_service] = lambda: mock_gs


def _cleanup_gs(client: AsyncClient) -> None:
    """Remove GraphService override."""
    app = client._transport.app  # type: ignore[union-attr]
    app.dependency_overrides.pop(get_graph_service, None)


# ---------------------------------------------------------------------------
# Rename entity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rename_entity(client: AsyncClient) -> None:
    """PATCH /matters/{id}/entities/{name}/rename should rename the entity."""
    mock = _mock_gs()
    mock.rename_entity = AsyncMock(
        return_value={"id": "Alice Smith", "name": "Alice Smith", "type": "person", "mention_count": 5, "aliases": []}
    )
    _apply_gs(client, mock)
    try:
        resp = await client.patch(
            f"/api/v1/matters/{_TEST_MATTER_ID}/entities/Alice/rename",
            json={"new_name": "Alice Smith"},
        )
    finally:
        _cleanup_gs(client)

    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Alice Smith"
    mock.rename_entity.assert_awaited_once_with(
        matter_id=str(_TEST_MATTER_ID),
        old_name="Alice",
        new_name="Alice Smith",
    )


@pytest.mark.asyncio
async def test_rename_entity_unauthorized(reviewer_client: AsyncClient) -> None:
    """PATCH rename with reviewer role should return 403."""
    mock = _mock_gs()
    _apply_gs(reviewer_client, mock)
    try:
        resp = await reviewer_client.patch(
            f"/api/v1/matters/{_TEST_MATTER_ID}/entities/Alice/rename",
            json={"new_name": "Alice Smith"},
        )
    finally:
        _cleanup_gs(reviewer_client)

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Update entity type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_entity_type(client: AsyncClient) -> None:
    """PATCH /matters/{id}/entities/{name}/type should update entity type."""
    mock = _mock_gs()
    mock.update_entity_type = AsyncMock(
        return_value={"id": "Alice", "name": "Alice", "type": "organization", "mention_count": 5, "aliases": []}
    )
    _apply_gs(client, mock)
    try:
        resp = await client.patch(
            f"/api/v1/matters/{_TEST_MATTER_ID}/entities/Alice/type",
            json={"new_type": "organization"},
        )
    finally:
        _cleanup_gs(client)

    assert resp.status_code == 200
    assert resp.json()["type"] == "organization"
    mock.update_entity_type.assert_awaited_once_with(
        matter_id=str(_TEST_MATTER_ID),
        name="Alice",
        new_type="organization",
    )


# ---------------------------------------------------------------------------
# Delete entity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_entity(client: AsyncClient) -> None:
    """DELETE /matters/{id}/entities/{name} should delete the entity."""
    mock = _mock_gs()
    mock.delete_entity = AsyncMock(return_value=True)
    _apply_gs(client, mock)
    try:
        resp = await client.delete(
            f"/api/v1/matters/{_TEST_MATTER_ID}/entities/Alice",
        )
    finally:
        _cleanup_gs(client)

    assert resp.status_code == 200
    assert "deleted" in resp.json()["detail"]
    mock.delete_entity.assert_awaited_once_with(
        matter_id=str(_TEST_MATTER_ID),
        name="Alice",
    )


# ---------------------------------------------------------------------------
# Merge entities
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_entities(client: AsyncClient) -> None:
    """POST /matters/{id}/entities/merge should merge source into target."""
    mock = _mock_gs()
    # get_entity_by_name called for source and target
    mock.get_entity_by_name = AsyncMock(
        side_effect=[
            {"name": "Bob", "type": "person", "mention_count": 2, "aliases": []},
            {"name": "Robert", "type": "person", "mention_count": 3, "aliases": []},
        ]
    )
    mock.merge_entities = AsyncMock(return_value=True)
    _apply_gs(client, mock)
    try:
        resp = await client.post(
            f"/api/v1/matters/{_TEST_MATTER_ID}/entities/merge",
            json={"source_name": "Bob", "target_name": "Robert"},
        )
    finally:
        _cleanup_gs(client)

    assert resp.status_code == 200
    assert "merged" in resp.json()["detail"]
    mock.merge_entities.assert_awaited_once_with(
        canonical_name="Robert",
        alias_name="Bob",
        entity_type="person",
        matter_id=str(_TEST_MATTER_ID),
    )


# ---------------------------------------------------------------------------
# Create relationship
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_relationship(client: AsyncClient) -> None:
    """POST /matters/{id}/relationships should create a new edge."""
    mock = _mock_gs()
    mock.create_relationship = AsyncMock(
        return_value={"source": "Alice", "target": "Bob", "relationship_type": "WORKS_WITH"}
    )
    _apply_gs(client, mock)
    try:
        resp = await client.post(
            f"/api/v1/matters/{_TEST_MATTER_ID}/relationships",
            json={
                "source_name": "Alice",
                "target_name": "Bob",
                "relationship_type": "WORKS_WITH",
            },
        )
    finally:
        _cleanup_gs(client)

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "Alice"
    assert body["relationship_type"] == "WORKS_WITH"


# ---------------------------------------------------------------------------
# Delete relationship
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_relationship(client: AsyncClient) -> None:
    """DELETE /matters/{id}/relationships should remove the edge."""
    mock = _mock_gs()
    mock.delete_relationship = AsyncMock(return_value=True)
    _apply_gs(client, mock)
    try:
        resp = await client.request(
            "DELETE",
            f"/api/v1/matters/{_TEST_MATTER_ID}/relationships",
            json={
                "source_name": "Alice",
                "target_name": "Bob",
                "relationship_type": "WORKS_WITH",
            },
        )
    finally:
        _cleanup_gs(client)

    assert resp.status_code == 200
    assert "deleted" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Rename non-existent entity → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rename_nonexistent_entity(client: AsyncClient) -> None:
    """PATCH rename for an entity that doesn't exist should return 404."""
    mock = _mock_gs()
    mock.rename_entity = AsyncMock(return_value=None)
    _apply_gs(client, mock)
    try:
        resp = await client.patch(
            f"/api/v1/matters/{_TEST_MATTER_ID}/entities/Ghost/rename",
            json={"new_name": "Phantom"},
        )
    finally:
        _cleanup_gs(client)

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Merge same entity → 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_same_entity(client: AsyncClient) -> None:
    """POST merge with identical source and target should return 400."""
    mock = _mock_gs()
    _apply_gs(client, mock)
    try:
        resp = await client.post(
            f"/api/v1/matters/{_TEST_MATTER_ID}/entities/merge",
            json={"source_name": "Alice", "target_name": "Alice"},
        )
    finally:
        _cleanup_gs(client)

    assert resp.status_code == 400
    assert "different" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Matter scoping — operations use matter_id from URL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_matter_scoping(client: AsyncClient) -> None:
    """Editing operations should pass the URL matter_id to the service layer."""
    mock = _mock_gs()
    mock.rename_entity = AsyncMock(
        return_value={"id": "Bob", "name": "Bob", "type": "person", "mention_count": 1, "aliases": []}
    )
    _apply_gs(client, mock)
    try:
        resp = await client.patch(
            f"/api/v1/matters/{_OTHER_MATTER_ID}/entities/Alice/rename",
            json={"new_name": "Bob"},
        )
    finally:
        _cleanup_gs(client)

    assert resp.status_code == 200
    # Verify the service was called with the URL matter_id, not the default
    mock.rename_entity.assert_awaited_once_with(
        matter_id=str(_OTHER_MATTER_ID),
        old_name="Alice",
        new_name="Bob",
    )
