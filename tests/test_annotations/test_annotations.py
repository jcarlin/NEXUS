"""Tests for the annotation API endpoints.

These tests run against the FastAPI app with mocked backends (no Docker required).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_annotation_row(annotation_id=None, **overrides) -> dict:
    """Return a dict mimicking a raw DB row from the annotations table."""
    base = {
        "id": annotation_id or uuid4(),
        "document_id": uuid4(),
        "matter_id": uuid4(),
        "user_id": uuid4(),
        "page_number": 3,
        "annotation_type": "note",
        "content": "This paragraph is relevant to the timeline.",
        "anchor": {},
        "color": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# POST /annotations — create annotation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_annotation(client: AsyncClient) -> None:
    """POST /annotations should return 201 with the created annotation."""
    ann_id = uuid4()
    doc_id = uuid4()
    row = _fake_annotation_row(annotation_id=ann_id, document_id=doc_id)

    with patch(
        "app.annotations.service.AnnotationService.create_annotation",
        new_callable=AsyncMock,
        return_value=row,
    ):
        response = await client.post(
            "/api/v1/annotations",
            json={
                "document_id": str(doc_id),
                "page_number": 3,
                "annotation_type": "note",
                "content": "This paragraph is relevant to the timeline.",
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == str(ann_id)
    assert body["content"] == "This paragraph is relevant to the timeline."
    assert body["annotation_type"] == "note"


# ---------------------------------------------------------------------------
# GET /annotations/{annotation_id} — get annotation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_annotation(client: AsyncClient) -> None:
    """GET /annotations/{id} should return annotation details."""
    ann_id = uuid4()
    row = _fake_annotation_row(annotation_id=ann_id)

    with patch(
        "app.annotations.service.AnnotationService.get_annotation",
        new_callable=AsyncMock,
        return_value=row,
    ):
        response = await client.get(f"/api/v1/annotations/{ann_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(ann_id)
    assert body["content"] == row["content"]


# ---------------------------------------------------------------------------
# PATCH /annotations/{annotation_id} — update annotation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_annotation(client: AsyncClient) -> None:
    """PATCH /annotations/{id} should update and return the annotation."""
    ann_id = uuid4()
    row = _fake_annotation_row(annotation_id=ann_id, content="Updated content.")

    with patch(
        "app.annotations.service.AnnotationService.update_annotation",
        new_callable=AsyncMock,
        return_value=row,
    ):
        response = await client.patch(
            f"/api/v1/annotations/{ann_id}",
            json={"content": "Updated content."},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(ann_id)
    assert body["content"] == "Updated content."


# ---------------------------------------------------------------------------
# DELETE /annotations/{annotation_id} — delete annotation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_annotation(client: AsyncClient) -> None:
    """DELETE /annotations/{id} should return 204."""
    ann_id = uuid4()

    with patch(
        "app.annotations.service.AnnotationService.delete_annotation",
        new_callable=AsyncMock,
        return_value=True,
    ):
        response = await client.delete(f"/api/v1/annotations/{ann_id}")

    assert response.status_code == 204


# ---------------------------------------------------------------------------
# GET /annotations — list annotations (empty)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_annotations_empty(client: AsyncClient) -> None:
    """GET /annotations should return an empty paginated list."""
    with patch(
        "app.annotations.service.AnnotationService.list_annotations",
        new_callable=AsyncMock,
        return_value=([], 0),
    ):
        response = await client.get("/api/v1/annotations")

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert "offset" in body
    assert "limit" in body


# ---------------------------------------------------------------------------
# POST /annotations — validation error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_annotation_validation(client: AsyncClient) -> None:
    """POST /annotations with missing content should return 422."""
    response = await client.post(
        "/api/v1/annotations",
        json={
            "document_id": str(uuid4()),
            # missing "content" field
        },
    )

    assert response.status_code == 422
