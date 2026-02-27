"""Tests for the document API endpoints.

These tests run against the FastAPI app with mocked backends (no Docker required).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_doc_row(doc_id=None, **overrides) -> dict:
    """Return a dict mimicking a raw DB row from the documents table."""
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
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# GET /documents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_documents_returns_200(client: AsyncClient) -> None:
    """GET /documents should return a paginated response."""
    with patch(
        "app.documents.service.DocumentService.list_documents",
        new_callable=AsyncMock,
        return_value=([], 0),
    ):
        response = await client.get("/api/v1/documents")

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert "offset" in body
    assert "limit" in body


@pytest.mark.asyncio
async def test_list_documents_with_type_filter(client: AsyncClient) -> None:
    """GET /documents?document_type=email should forward the filter."""
    row = _fake_doc_row(document_type="email")

    with patch(
        "app.documents.service.DocumentService.list_documents",
        new_callable=AsyncMock,
        return_value=([row], 1),
    ) as mock_list:
        response = await client.get("/api/v1/documents?document_type=email")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1

    # Verify the filter was passed through
    mock_list.assert_called_once()
    call_kwargs = mock_list.call_args
    assert call_kwargs[1].get("document_type") == "email" or \
        (len(call_kwargs[0]) > 1 and call_kwargs[0][1] == "email")


# ---------------------------------------------------------------------------
# GET /documents/{doc_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_document_found(client: AsyncClient) -> None:
    """GET /documents/{id} should return document details."""
    doc_id = uuid4()
    row = _fake_doc_row(doc_id=doc_id)

    with patch(
        "app.documents.service.DocumentService.get_document",
        new_callable=AsyncMock,
        return_value=row,
    ):
        response = await client.get(f"/api/v1/documents/{doc_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(doc_id)
    assert body["filename"] == "report.pdf"
    assert "file_size_bytes" in body
    assert "content_hash" in body
    assert "job_id" in body


@pytest.mark.asyncio
async def test_get_document_not_found(client: AsyncClient) -> None:
    """GET /documents/{id} should return 404 for nonexistent document."""
    with patch(
        "app.documents.service.DocumentService.get_document",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.get(f"/api/v1/documents/{uuid4()}")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /documents/{doc_id}/preview
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_document_preview_returns_url(client: AsyncClient) -> None:
    """GET /documents/{id}/preview should return a presigned URL."""
    doc_id = uuid4()
    row = _fake_doc_row(doc_id=doc_id)

    mock_storage = MagicMock()
    mock_storage.get_presigned_url = AsyncMock(
        return_value="http://minio:9000/documents/pages/preview.png?sig=abc"
    )

    with (
        patch(
            "app.documents.service.DocumentService.get_document",
            new_callable=AsyncMock,
            return_value=row,
        ),
        patch("app.dependencies._storage_client", mock_storage),
    ):
        response = await client.get(f"/api/v1/documents/{doc_id}/preview?page=2")

    assert response.status_code == 200
    body = response.json()
    assert body["doc_id"] == str(doc_id)
    assert body["page"] == 2
    assert "image_url" in body
    assert body["image_url"].startswith("http")


@pytest.mark.asyncio
async def test_document_preview_not_found(client: AsyncClient) -> None:
    """GET /documents/{id}/preview should return 404 for missing document."""
    with patch(
        "app.documents.service.DocumentService.get_document",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.get(f"/api/v1/documents/{uuid4()}/preview")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /documents/{doc_id}/download
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_document_download_returns_url(client: AsyncClient) -> None:
    """GET /documents/{id}/download should return a presigned URL."""
    doc_id = uuid4()
    row = _fake_doc_row(doc_id=doc_id)

    mock_storage = MagicMock()
    mock_storage.get_presigned_url = AsyncMock(
        return_value="http://minio:9000/documents/raw/abc/report.pdf?sig=xyz"
    )

    with (
        patch(
            "app.documents.service.DocumentService.get_document",
            new_callable=AsyncMock,
            return_value=row,
        ),
        patch("app.dependencies._storage_client", mock_storage),
    ):
        response = await client.get(f"/api/v1/documents/{doc_id}/download")

    assert response.status_code == 200
    body = response.json()
    assert body["doc_id"] == str(doc_id)
    assert body["filename"] == "report.pdf"
    assert "download_url" in body
    assert body["download_url"].startswith("http")


@pytest.mark.asyncio
async def test_document_download_not_found(client: AsyncClient) -> None:
    """GET /documents/{id}/download should return 404 for missing document."""
    with patch(
        "app.documents.service.DocumentService.get_document",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.get(f"/api/v1/documents/{uuid4()}/download")

    assert response.status_code == 404
