"""Tests for GET /api/v1/bulk-imports/{import_id}/jobs endpoint."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

_MATTER_ID = UUID("00000000-0000-0000-0000-000000000001")


def _mock_job_row(*, status: str = "complete", filename: str = "test.pdf") -> dict:
    now = datetime.now(UTC)
    return {
        "id": uuid4(),
        "filename": filename,
        "status": status,
        "stage": "complete" if status == "complete" else "uploading",
        "progress": "{}",
        "error": None,
        "parent_job_id": None,
        "matter_id": _MATTER_ID,
        "metadata_": "{}",
        "task_type": "ingestion",
        "label": None,
        "created_at": now,
        "updated_at": now,
    }


def _mock_bulk_import_row(import_id: UUID) -> dict:
    now = datetime.now(UTC)
    return {
        "id": import_id,
        "matter_id": _MATTER_ID,
        "adapter_type": "directory",
        "source_path": "/tmp/test",
        "status": "complete",
        "total_documents": 10,
        "processed_documents": 10,
        "failed_documents": 0,
        "skipped_documents": 0,
        "error": None,
        "created_at": now,
        "updated_at": now,
        "completed_at": now,
    }


@pytest.mark.asyncio
async def test_list_bulk_import_jobs_empty(client: AsyncClient) -> None:
    """Should return empty paginated response when no jobs exist."""
    import_id = uuid4()
    with (
        patch(
            "app.ingestion.service.IngestionService.get_bulk_import_job",
            new_callable=AsyncMock,
            return_value=_mock_bulk_import_row(import_id),
        ),
        patch(
            "app.ingestion.service.IngestionService.list_jobs_by_bulk_import",
            new_callable=AsyncMock,
            return_value=([], 0),
        ),
    ):
        response = await client.get(f"/api/v1/bulk-imports/{import_id}/jobs")

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["offset"] == 0
    assert body["limit"] == 50


@pytest.mark.asyncio
async def test_list_bulk_import_jobs_with_data(client: AsyncClient) -> None:
    """Should return job items for a bulk import."""
    import_id = uuid4()
    job_rows = [_mock_job_row(filename="doc1.pdf"), _mock_job_row(filename="doc2.pdf")]

    with (
        patch(
            "app.ingestion.service.IngestionService.get_bulk_import_job",
            new_callable=AsyncMock,
            return_value=_mock_bulk_import_row(import_id),
        ),
        patch(
            "app.ingestion.service.IngestionService.list_jobs_by_bulk_import",
            new_callable=AsyncMock,
            return_value=(job_rows, 2),
        ),
    ):
        response = await client.get(f"/api/v1/bulk-imports/{import_id}/jobs")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    filenames = {item["filename"] for item in body["items"]}
    assert filenames == {"doc1.pdf", "doc2.pdf"}


@pytest.mark.asyncio
async def test_list_bulk_import_jobs_pagination(client: AsyncClient) -> None:
    """Should pass offset and limit to the service."""
    import_id = uuid4()
    with (
        patch(
            "app.ingestion.service.IngestionService.get_bulk_import_job",
            new_callable=AsyncMock,
            return_value=_mock_bulk_import_row(import_id),
        ),
        patch(
            "app.ingestion.service.IngestionService.list_jobs_by_bulk_import",
            new_callable=AsyncMock,
            return_value=([], 0),
        ) as mock_list,
    ):
        response = await client.get(f"/api/v1/bulk-imports/{import_id}/jobs?offset=5&limit=10")

    assert response.status_code == 200
    call_kwargs = mock_list.call_args.kwargs
    assert call_kwargs["offset"] == 5
    assert call_kwargs["limit"] == 10


@pytest.mark.asyncio
async def test_list_bulk_import_jobs_status_filter(client: AsyncClient) -> None:
    """Should pass status filter to the service."""
    import_id = uuid4()
    with (
        patch(
            "app.ingestion.service.IngestionService.get_bulk_import_job",
            new_callable=AsyncMock,
            return_value=_mock_bulk_import_row(import_id),
        ),
        patch(
            "app.ingestion.service.IngestionService.list_jobs_by_bulk_import",
            new_callable=AsyncMock,
            return_value=([], 0),
        ) as mock_list,
    ):
        response = await client.get(f"/api/v1/bulk-imports/{import_id}/jobs?status=failed")

    assert response.status_code == 200
    call_kwargs = mock_list.call_args.kwargs
    assert call_kwargs["status"] == "failed"


@pytest.mark.asyncio
async def test_list_bulk_import_jobs_404(client: AsyncClient) -> None:
    """Should return 404 for non-existent bulk import."""
    import_id = uuid4()
    with patch(
        "app.ingestion.service.IngestionService.get_bulk_import_job",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.get(f"/api/v1/bulk-imports/{import_id}/jobs")

    assert response.status_code == 404
