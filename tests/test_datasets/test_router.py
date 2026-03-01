"""Tests for the dataset router endpoints.

These tests run against the FastAPI app with mocked backends (no Docker required).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from httpx import AsyncClient

from app.datasets.schemas import DatasetResponse, DatasetTreeNode
from app.dependencies import get_db

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MATTER_ID = UUID("00000000-0000-0000-0000-000000000001")
_DATASET_ID = UUID("00000000-0000-0000-0000-000000000010")
_PARENT_ID = UUID("00000000-0000-0000-0000-000000000020")
_DOC_ID = UUID("00000000-0000-0000-0000-000000000030")
_NOW = datetime(2025, 1, 1, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dataset_response(**overrides) -> DatasetResponse:
    """Build a DatasetResponse with sensible defaults."""
    defaults = dict(
        id=_DATASET_ID,
        matter_id=_MATTER_ID,
        name="Test Dataset",
        description="A test dataset",
        parent_id=None,
        document_count=0,
        children_count=0,
        created_by=None,
        created_at=_NOW,
        updated_at=_NOW,
    )
    defaults.update(overrides)
    return DatasetResponse(**defaults)


async def _mock_db_gen():
    """Async generator that yields a mock AsyncSession."""
    mock = AsyncMock()
    yield mock


def _override_db(app):
    """Override get_db on the test app and return it."""
    app.dependency_overrides[get_db] = _mock_db_gen
    return app


# ---------------------------------------------------------------------------
# POST /datasets — create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_dataset(client: AsyncClient) -> None:
    """POST /datasets with valid body should return 201 with the new dataset."""
    mock_response = _make_dataset_response()
    app = client._transport.app
    _override_db(app)

    try:
        with patch(
            "app.datasets.router.DatasetService.create_dataset",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = await client.post(
                "/api/v1/datasets",
                json={"name": "Test Dataset", "description": "A test dataset"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Dataset"
    assert "id" in data
    assert data["id"] == str(_DATASET_ID)


@pytest.mark.asyncio
async def test_create_nested_dataset(client: AsyncClient) -> None:
    """POST /datasets with parent_id should return 201 for a nested dataset."""
    mock_response = _make_dataset_response(parent_id=_PARENT_ID)
    app = client._transport.app
    _override_db(app)

    try:
        with patch(
            "app.datasets.router.DatasetService.create_dataset",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = await client.post(
                "/api/v1/datasets",
                json={
                    "name": "Test Dataset",
                    "description": "A test dataset",
                    "parent_id": str(_PARENT_ID),
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 201
    data = response.json()
    assert data["parent_id"] == str(_PARENT_ID)


# ---------------------------------------------------------------------------
# GET /datasets — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_datasets(client: AsyncClient) -> None:
    """GET /datasets should return a paginated response."""
    items = [_make_dataset_response(), _make_dataset_response(id=_PARENT_ID, name="Second")]
    app = client._transport.app
    _override_db(app)

    try:
        with patch(
            "app.datasets.router.DatasetService.list_datasets",
            new_callable=AsyncMock,
            return_value=(items, 2),
        ):
            response = await client.get("/api/v1/datasets")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert "offset" in body
    assert "limit" in body


# ---------------------------------------------------------------------------
# GET /datasets/tree
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_dataset_tree(client: AsyncClient) -> None:
    """GET /datasets/tree should return the tree structure."""
    child = DatasetTreeNode(
        id=_PARENT_ID,
        name="Child",
        description="",
        document_count=3,
    )
    root = DatasetTreeNode(
        id=_DATASET_ID,
        name="Root",
        description="",
        document_count=5,
        children=[child],
    )
    app = client._transport.app
    _override_db(app)

    try:
        with patch(
            "app.datasets.router.DatasetService.get_dataset_tree",
            new_callable=AsyncMock,
            return_value=([root], 2),
        ):
            response = await client.get("/api/v1/datasets/tree")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["total_datasets"] == 2
    assert len(body["roots"]) == 1
    assert body["roots"][0]["name"] == "Root"
    assert len(body["roots"][0]["children"]) == 1
    assert body["roots"][0]["children"][0]["name"] == "Child"


# ---------------------------------------------------------------------------
# GET /datasets/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_dataset(client: AsyncClient) -> None:
    """GET /datasets/{id} should return 200 with dataset details."""
    mock_response = _make_dataset_response(document_count=10, children_count=2)
    app = client._transport.app
    _override_db(app)

    try:
        with patch(
            "app.datasets.router.DatasetService.get_dataset",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = await client.get(f"/api/v1/datasets/{_DATASET_ID}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(_DATASET_ID)
    assert data["document_count"] == 10
    assert data["children_count"] == 2


@pytest.mark.asyncio
async def test_get_dataset_not_found(client: AsyncClient) -> None:
    """GET /datasets/{id} should return 404 for nonexistent dataset."""
    app = client._transport.app
    _override_db(app)

    try:
        with patch(
            "app.datasets.router.DatasetService.get_dataset",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = await client.get(f"/api/v1/datasets/{_DATASET_ID}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /datasets/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_dataset(client: AsyncClient) -> None:
    """PATCH /datasets/{id} should return 200 with updated dataset."""
    updated = _make_dataset_response(name="Renamed", description="Updated desc")
    app = client._transport.app
    _override_db(app)

    try:
        with patch(
            "app.datasets.router.DatasetService.update_dataset",
            new_callable=AsyncMock,
            return_value=updated,
        ):
            response = await client.patch(
                f"/api/v1/datasets/{_DATASET_ID}",
                json={"name": "Renamed", "description": "Updated desc"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Renamed"
    assert data["description"] == "Updated desc"


# ---------------------------------------------------------------------------
# DELETE /datasets/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_dataset(client: AsyncClient) -> None:
    """DELETE /datasets/{id} should return 204 on successful deletion."""
    app = client._transport.app
    _override_db(app)

    try:
        with patch(
            "app.datasets.router.DatasetService.delete_dataset",
            new_callable=AsyncMock,
            return_value=True,
        ):
            response = await client.delete(f"/api/v1/datasets/{_DATASET_ID}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 204


# ---------------------------------------------------------------------------
# POST /datasets/{id}/documents — assign documents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assign_documents(client: AsyncClient) -> None:
    """POST /datasets/{id}/documents should return 200 with assigned count."""
    app = client._transport.app
    _override_db(app)

    try:
        with patch(
            "app.datasets.router.DatasetService.assign_documents",
            new_callable=AsyncMock,
            return_value=3,
        ):
            response = await client.post(
                f"/api/v1/datasets/{_DATASET_ID}/documents",
                json={"document_ids": [str(_DOC_ID), str(_PARENT_ID), str(_DATASET_ID)]},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    data = response.json()
    assert data["assigned"] == 3


# ---------------------------------------------------------------------------
# POST /documents/{id}/tags — add tag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_tag(client: AsyncClient) -> None:
    """POST /documents/{id}/tags should return 201 with tag info."""
    app = client._transport.app
    _override_db(app)

    try:
        with patch(
            "app.datasets.router.DatasetService.add_tag",
            new_callable=AsyncMock,
            return_value=True,
        ):
            response = await client.post(
                f"/api/v1/documents/{_DOC_ID}/tags",
                json={"tag_name": "privileged"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 201
    data = response.json()
    assert data["tag_name"] == "privileged"
    assert data["created"] is True
