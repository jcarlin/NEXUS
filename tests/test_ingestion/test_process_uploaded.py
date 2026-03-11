"""Tests for POST /api/v1/ingest/process-uploaded endpoint."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_process_uploaded_rejects_empty_files(client: AsyncClient) -> None:
    """POST /ingest/process-uploaded with empty files list should return 422."""
    response = await client.post(
        "/api/v1/ingest/process-uploaded",
        json={"files": []},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_process_uploaded_rejects_missing_body(client: AsyncClient) -> None:
    """POST /ingest/process-uploaded without body should return 422."""
    response = await client.post("/api/v1/ingest/process-uploaded")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_process_uploaded_creates_jobs(client: AsyncClient) -> None:
    """POST /ingest/process-uploaded should create jobs and dispatch tasks."""
    fake_job_id = uuid4()
    now = datetime.now(UTC)
    fake_job = {
        "id": fake_job_id,
        "filename": "doc.pdf",
        "status": "pending",
        "stage": "uploading",
        "progress": {},
        "error": None,
        "parent_job_id": None,
        "matter_id": None,
        "metadata_": {},
        "created_at": now,
        "updated_at": now,
    }

    with (
        patch("app.ingestion.router.process_document") as mock_task,
        patch(
            "app.ingestion.service.IngestionService.create_job",
            new_callable=AsyncMock,
        ) as mock_create,
    ):
        mock_task.apply_async = MagicMock()
        mock_create.return_value = fake_job

        response = await client.post(
            "/api/v1/ingest/process-uploaded",
            json={
                "files": [
                    {"object_key": "raw/abc/doc.pdf", "filename": "doc.pdf"},
                ]
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total_files"] == 1
    assert len(body["job_ids"]) == 1
    assert body["filenames"] == ["doc.pdf"]
    mock_task.apply_async.assert_called_once()
    mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_process_uploaded_multiple_files(client: AsyncClient) -> None:
    """POST /ingest/process-uploaded with multiple files creates multiple jobs."""
    now = datetime.now(UTC)

    def make_job(filename: str) -> dict:
        return {
            "id": uuid4(),
            "filename": filename,
            "status": "pending",
            "stage": "uploading",
            "progress": {},
            "error": None,
            "parent_job_id": None,
            "matter_id": None,
            "metadata_": {},
            "created_at": now,
            "updated_at": now,
        }

    with (
        patch("app.ingestion.router.process_document") as mock_task,
        patch(
            "app.ingestion.service.IngestionService.create_job",
            new_callable=AsyncMock,
        ) as mock_create,
    ):
        mock_task.apply_async = MagicMock()
        mock_create.side_effect = [make_job("a.pdf"), make_job("b.pdf")]

        response = await client.post(
            "/api/v1/ingest/process-uploaded",
            json={
                "files": [
                    {"object_key": "raw/1/a.pdf", "filename": "a.pdf"},
                    {"object_key": "raw/2/b.pdf", "filename": "b.pdf"},
                ]
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total_files"] == 2
    assert mock_task.apply_async.call_count == 2


@pytest.mark.asyncio
async def test_process_uploaded_with_dataset_id(client: AsyncClient) -> None:
    """POST /ingest/process-uploaded should forward dataset_id to create_job."""
    dataset_id = uuid4()
    now = datetime.now(UTC)
    fake_job = {
        "id": uuid4(),
        "filename": "doc.pdf",
        "status": "pending",
        "stage": "uploading",
        "progress": {},
        "error": None,
        "parent_job_id": None,
        "matter_id": None,
        "metadata_": {},
        "created_at": now,
        "updated_at": now,
    }

    with (
        patch("app.ingestion.router.process_document") as mock_task,
        patch(
            "app.ingestion.service.IngestionService.create_job",
            new_callable=AsyncMock,
        ) as mock_create,
    ):
        mock_task.apply_async = MagicMock()
        mock_create.return_value = fake_job

        response = await client.post(
            f"/api/v1/ingest/process-uploaded?dataset_id={dataset_id}",
            json={
                "files": [
                    {"object_key": "raw/abc/doc.pdf", "filename": "doc.pdf"},
                ]
            },
        )

    assert response.status_code == 200
    # Verify dataset_id was passed through
    call_kwargs = mock_create.call_args
    assert call_kwargs.kwargs["dataset_id"] == dataset_id
