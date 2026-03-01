"""Tests for presigned upload endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_presigned_upload_returns_url(client: AsyncClient) -> None:
    """POST /ingest/presigned-upload returns a presigned URL and object key."""
    mock_storage = MagicMock()
    mock_storage.get_presigned_put_url = AsyncMock(return_value="https://minio:9000/bucket/raw/abc/test.pdf?signed=1")

    with patch("app.ingestion.router.get_minio", return_value=mock_storage):
        resp = await client.post(
            "/api/v1/ingest/presigned-upload",
            json={
                "filename": "test.pdf",
                "content_type": "application/pdf",
                "matter_id": "00000000-0000-0000-0000-000000000001",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "upload_url" in data
    assert "object_key" in data
    assert data["object_key"].startswith("raw/")
    assert data["object_key"].endswith("/test.pdf")
    assert data["expires_in"] == 3600


@pytest.mark.asyncio
async def test_presigned_upload_rejects_empty_filename(client: AsyncClient) -> None:
    """POST /ingest/presigned-upload with empty filename returns 422."""
    resp = await client.post(
        "/api/v1/ingest/presigned-upload",
        json={
            "filename": "",
            "content_type": "application/pdf",
            "matter_id": "00000000-0000-0000-0000-000000000001",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_presigned_upload_requires_filename(client: AsyncClient) -> None:
    """POST /ingest/presigned-upload without filename returns 422."""
    resp = await client.post(
        "/api/v1/ingest/presigned-upload",
        json={
            "matter_id": "00000000-0000-0000-0000-000000000001",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_presigned_upload_default_content_type(client: AsyncClient) -> None:
    """POST /ingest/presigned-upload uses default content_type when omitted."""
    mock_storage = MagicMock()
    mock_storage.get_presigned_put_url = AsyncMock(return_value="https://minio:9000/bucket/raw/abc/file.bin?signed=1")

    with patch("app.ingestion.router.get_minio", return_value=mock_storage):
        resp = await client.post(
            "/api/v1/ingest/presigned-upload",
            json={
                "filename": "file.bin",
                "matter_id": "00000000-0000-0000-0000-000000000001",
            },
        )

    assert resp.status_code == 200
    # Verify storage was called with the default content type
    mock_storage.get_presigned_put_url.assert_called_once()
    call_kwargs = mock_storage.get_presigned_put_url.call_args
    assert call_kwargs.kwargs.get("content_type") == "application/octet-stream"
