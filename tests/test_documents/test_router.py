"""Tests for the document API endpoints.

These tests run against the FastAPI app with mocked backends (no Docker required).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.dependencies import get_minio

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
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
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
    assert call_kwargs[1].get("document_type") == "email" or (len(call_kwargs[0]) > 1 and call_kwargs[0][1] == "email")


@pytest.mark.asyncio
async def test_list_documents_with_file_extension_filter(client: AsyncClient) -> None:
    """GET /documents?file_extension=pdf should forward the filter."""
    row = _fake_doc_row(filename="contract.pdf")

    with patch(
        "app.documents.service.DocumentService.list_documents",
        new_callable=AsyncMock,
        return_value=([row], 1),
    ) as mock_list:
        response = await client.get("/api/v1/documents?file_extension=pdf")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1

    # Verify the filter was passed through
    mock_list.assert_called_once()
    call_kwargs = mock_list.call_args[1]
    assert call_kwargs.get("file_extension") == "pdf"


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
async def test_get_document_includes_sentiment_scoring_bates(client: AsyncClient) -> None:
    """GET /documents/{id} should return sentiment, scoring, and bates fields."""
    doc_id = uuid4()
    row = _fake_doc_row(
        doc_id=doc_id,
        sentiment_positive=0.85,
        sentiment_negative=0.12,
        sentiment_pressure=0.3,
        sentiment_opportunity=0.5,
        sentiment_rationalization=0.1,
        sentiment_intent=0.6,
        sentiment_concealment=0.05,
        hot_doc_score=0.92,
        context_gap_score=0.4,
        context_gaps=["missing financials", "no deposition"],
        anomaly_score=0.7,
        bates_begin="NEXUS-000100",
        bates_end="NEXUS-000112",
    )

    with patch(
        "app.documents.service.DocumentService.get_document",
        new_callable=AsyncMock,
        return_value=row,
    ):
        response = await client.get(f"/api/v1/documents/{doc_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["sentiment_positive"] == 0.85
    assert body["sentiment_negative"] == 0.12
    assert body["sentiment_pressure"] == 0.3
    assert body["sentiment_intent"] == 0.6
    assert body["sentiment_concealment"] == 0.05
    assert body["hot_doc_score"] == 0.92
    assert body["context_gap_score"] == 0.4
    assert body["context_gaps"] == ["missing financials", "no deposition"]
    assert body["anomaly_score"] == 0.7
    assert body["bates_begin"] == "NEXUS-000100"
    assert body["bates_end"] == "NEXUS-000112"


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
    mock_storage.get_presigned_url = AsyncMock(return_value="http://minio:9000/documents/pages/preview.png?sig=abc")

    app = client._transport.app
    app.dependency_overrides[get_minio] = lambda: mock_storage
    try:
        with patch(
            "app.documents.service.DocumentService.get_document",
            new_callable=AsyncMock,
            return_value=row,
        ):
            response = await client.get(f"/api/v1/documents/{doc_id}/preview?page=2")
    finally:
        app.dependency_overrides.pop(get_minio, None)

    assert response.status_code == 200
    body = response.json()
    assert body["doc_id"] == str(doc_id)
    assert body["page"] == 2
    assert "image_url" in body
    assert body["image_url"].startswith("http")


@pytest.mark.asyncio
async def test_document_preview_not_found(client: AsyncClient) -> None:
    """GET /documents/{id}/preview should return 404 for missing document."""
    with (
        patch(
            "app.documents.service.DocumentService.get_document",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.documents.service.DocumentService.get_document_by_job",
            new_callable=AsyncMock,
            return_value=None,
        ),
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
    mock_storage.get_presigned_url = AsyncMock(return_value="http://minio:9000/documents/raw/abc/report.pdf?sig=xyz")

    app = client._transport.app
    app.dependency_overrides[get_minio] = lambda: mock_storage
    try:
        with patch(
            "app.documents.service.DocumentService.get_document",
            new_callable=AsyncMock,
            return_value=row,
        ):
            response = await client.get(f"/api/v1/documents/{doc_id}/download")
    finally:
        app.dependency_overrides.pop(get_minio, None)

    assert response.status_code == 200
    body = response.json()
    assert body["doc_id"] == str(doc_id)
    assert body["filename"] == "report.pdf"
    assert "download_url" in body
    assert body["download_url"].startswith("http")


@pytest.mark.asyncio
async def test_document_download_not_found(client: AsyncClient) -> None:
    """GET /documents/{id}/download should return 404 for missing document."""
    with (
        patch(
            "app.documents.service.DocumentService.get_document",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.documents.service.DocumentService.get_document_by_job",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        response = await client.get(f"/api/v1/documents/{uuid4()}/download")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Job-ID fallback (Qdrant payloads store job_id as doc_id)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_fallback_to_job_id(client: AsyncClient) -> None:
    """GET /documents/{job_id}/download should resolve via job_id fallback."""
    job_id = uuid4()
    doc_id = uuid4()
    row = _fake_doc_row(doc_id=doc_id, job_id=job_id)

    mock_storage = MagicMock()
    mock_storage.get_presigned_url = AsyncMock(return_value="http://minio:9000/raw/abc/report.pdf?sig=xyz")

    app = client._transport.app
    app.dependency_overrides[get_minio] = lambda: mock_storage
    try:
        with (
            patch(
                "app.documents.service.DocumentService.get_document",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.documents.service.DocumentService.get_document_by_job",
                new_callable=AsyncMock,
                return_value=row,
            ) as mock_by_job,
        ):
            response = await client.get(f"/api/v1/documents/{job_id}/download")
    finally:
        app.dependency_overrides.pop(get_minio, None)

    assert response.status_code == 200
    body = response.json()
    # Should return the real document id, not the job_id used in the URL
    assert body["doc_id"] == str(doc_id)
    assert body["filename"] == "report.pdf"
    assert "download_url" in body
    mock_by_job.assert_called_once()


@pytest.mark.asyncio
async def test_preview_fallback_to_job_id(client: AsyncClient) -> None:
    """GET /documents/{job_id}/preview should resolve via job_id fallback."""
    job_id = uuid4()
    doc_id = uuid4()
    row = _fake_doc_row(doc_id=doc_id, job_id=job_id)

    mock_storage = MagicMock()
    mock_storage.get_presigned_url = AsyncMock(return_value="http://minio:9000/pages/preview.png?sig=abc")

    app = client._transport.app
    app.dependency_overrides[get_minio] = lambda: mock_storage
    try:
        with (
            patch(
                "app.documents.service.DocumentService.get_document",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.documents.service.DocumentService.get_document_by_job",
                new_callable=AsyncMock,
                return_value=row,
            ) as mock_by_job,
        ):
            response = await client.get(f"/api/v1/documents/{job_id}/preview?page=3")
    finally:
        app.dependency_overrides.pop(get_minio, None)

    assert response.status_code == 200
    body = response.json()
    # Should return the real document id
    assert body["doc_id"] == str(doc_id)
    assert body["page"] == 3
    assert "image_url" in body
    mock_by_job.assert_called_once()

    # Verify the preview key uses job_id (page images stored under job_id)
    presigned_call = mock_storage.get_presigned_url.call_args[0][0]
    assert presigned_call == f"pages/{job_id}/page_003.png"


@pytest.mark.asyncio
async def test_preview_uses_job_id_for_page_key(client: AsyncClient) -> None:
    """Preview should use row['job_id'] for page image path, not the URL doc_id."""
    doc_id = uuid4()
    job_id = uuid4()
    row = _fake_doc_row(doc_id=doc_id, job_id=job_id)

    mock_storage = MagicMock()
    mock_storage.get_presigned_url = AsyncMock(return_value="http://minio:9000/pages/preview.png?sig=abc")

    app = client._transport.app
    app.dependency_overrides[get_minio] = lambda: mock_storage
    try:
        with patch(
            "app.documents.service.DocumentService.get_document",
            new_callable=AsyncMock,
            return_value=row,
        ):
            response = await client.get(f"/api/v1/documents/{doc_id}/preview?page=1")
    finally:
        app.dependency_overrides.pop(get_minio, None)

    assert response.status_code == 200
    # Page images are stored under job_id, not doc_id
    presigned_call = mock_storage.get_presigned_url.call_args[0][0]
    assert presigned_call == f"pages/{job_id}/page_001.png"
