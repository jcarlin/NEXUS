"""Tests for document comparison API endpoints (T3-4).

Covers GET /documents/compare and GET /documents/versions/{id}.
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


def _fake_doc_row(doc_id=None, **overrides) -> dict:
    base = {
        "id": doc_id or uuid4(),
        "job_id": uuid4(),
        "filename": "report.pdf",
        "document_type": "deposition",
        "page_count": 12,
        "chunk_count": 30,
        "entity_count": 8,
        "minio_path": "raw/abc/report.pdf",
        "file_size_bytes": 204800,
        "content_hash": "sha256-xyz",
        "metadata_": {"source": "batch_001"},
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# GET /documents/compare
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compare_documents_success(client: AsyncClient) -> None:
    left_id = uuid4()
    right_id = uuid4()
    left_row = _fake_doc_row(doc_id=left_id, filename="v1.pdf")
    right_row = _fake_doc_row(doc_id=right_id, filename="v2.pdf")

    with (
        patch(
            "app.documents.service.DocumentService.get_document_text",
            new_callable=AsyncMock,
            side_effect=["line one\nline two\n", "line one\nline three\n"],
        ),
        patch(
            "app.documents.service.DocumentService.get_document",
            new_callable=AsyncMock,
            side_effect=[left_row, right_row],
        ),
    ):
        resp = await client.get(
            "/api/v1/documents/compare",
            params={"left_id": str(left_id), "right_id": str(right_id)},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["left_id"] == str(left_id)
    assert body["right_id"] == str(right_id)
    assert body["left_filename"] == "v1.pdf"
    assert body["right_filename"] == "v2.pdf"
    assert len(body["blocks"]) > 0
    assert body["truncated"] is False


@pytest.mark.asyncio
async def test_compare_documents_left_not_found(client: AsyncClient) -> None:
    left_id = uuid4()
    right_id = uuid4()

    with patch(
        "app.documents.service.DocumentService.get_document_text",
        new_callable=AsyncMock,
        side_effect=LookupError("not found"),
    ):
        resp = await client.get(
            "/api/v1/documents/compare",
            params={"left_id": str(left_id), "right_id": str(right_id)},
        )

    assert resp.status_code == 404
    assert str(left_id) in resp.json()["detail"]


@pytest.mark.asyncio
async def test_compare_documents_right_not_found(client: AsyncClient) -> None:
    left_id = uuid4()
    right_id = uuid4()

    with patch(
        "app.documents.service.DocumentService.get_document_text",
        new_callable=AsyncMock,
        side_effect=["some text", LookupError("not found")],
    ):
        resp = await client.get(
            "/api/v1/documents/compare",
            params={"left_id": str(left_id), "right_id": str(right_id)},
        )

    assert resp.status_code == 404
    assert str(right_id) in resp.json()["detail"]


@pytest.mark.asyncio
async def test_compare_requires_auth(unauthed_client: AsyncClient) -> None:
    resp = await unauthed_client.get(
        "/api/v1/documents/compare",
        params={"left_id": str(uuid4()), "right_id": str(uuid4())},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_compare_missing_params(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/documents/compare")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_compare_parsed_text_not_found(client: AsyncClient) -> None:
    left_id = uuid4()
    right_id = uuid4()

    with patch(
        "app.documents.service.DocumentService.get_document_text",
        new_callable=AsyncMock,
        side_effect=FileNotFoundError("No parsed text"),
    ):
        resp = await client.get(
            "/api/v1/documents/compare",
            params={"left_id": str(left_id), "right_id": str(right_id)},
        )

    assert resp.status_code == 404
    assert "Parsed text" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /documents/versions/{version_group_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_version_group_success(client: AsyncClient) -> None:
    members = [
        {
            "id": uuid4(),
            "filename": "contract_v1.pdf",
            "version_number": 1,
            "is_final_version": False,
            "created_at": datetime.now(UTC),
        },
        {
            "id": uuid4(),
            "filename": "contract_v2.pdf",
            "version_number": 2,
            "is_final_version": True,
            "created_at": datetime.now(UTC),
        },
    ]

    with patch(
        "app.documents.service.DocumentService.get_version_group",
        new_callable=AsyncMock,
        return_value=members,
    ):
        resp = await client.get("/api/v1/documents/versions/vg-123")

    assert resp.status_code == 200
    body = resp.json()
    assert body["version_group_id"] == "vg-123"
    assert len(body["members"]) == 2
    assert body["members"][0]["filename"] == "contract_v1.pdf"
    assert body["members"][1]["is_final_version"] is True


@pytest.mark.asyncio
async def test_version_group_not_found(client: AsyncClient) -> None:
    with patch(
        "app.documents.service.DocumentService.get_version_group",
        new_callable=AsyncMock,
        return_value=[],
    ):
        resp = await client.get("/api/v1/documents/versions/nonexistent")

    assert resp.status_code == 404
