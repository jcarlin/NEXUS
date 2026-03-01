"""Tests for the POST /ingest/batch endpoint."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_batch_returns_200_with_multiple_files(client: AsyncClient) -> None:
    """POST /ingest/batch with multiple files should return 200 with job_ids."""
    mock_storage = MagicMock()
    mock_storage.upload_bytes = AsyncMock(return_value="raw/test/file.txt")

    now = datetime.now(UTC)
    fake_jobs = []
    for i in range(3):
        fake_jobs.append(
            {
                "id": uuid4(),
                "filename": f"file{i}.txt",
                "status": "pending",
                "stage": "uploading",
                "progress": {},
                "error": None,
                "parent_job_id": None,
                "metadata_": {},
                "created_at": now,
                "updated_at": now,
            }
        )

    call_count = 0

    async def fake_create_job(**kwargs):
        nonlocal call_count
        result = fake_jobs[call_count]
        call_count += 1
        return result

    with (
        patch("app.ingestion.router.get_minio", return_value=mock_storage),
        patch("app.ingestion.router.process_document") as mock_task,
        patch(
            "app.ingestion.service.IngestionService.create_job",
            side_effect=fake_create_job,
        ),
    ):
        mock_task.delay = MagicMock()

        response = await client.post(
            "/api/v1/ingest/batch",
            files=[
                ("files", ("file0.txt", b"content 0", "text/plain")),
                ("files", ("file1.txt", b"content 1", "text/plain")),
                ("files", ("file2.txt", b"content 2", "text/plain")),
            ],
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total_files"] == 3
    assert len(body["job_ids"]) == 3
    assert len(body["filenames"]) == 3
    assert mock_task.delay.call_count == 3


@pytest.mark.asyncio
async def test_batch_rejects_no_files(client: AsyncClient) -> None:
    """POST /ingest/batch with no files should return 422."""
    response = await client.post("/api/v1/ingest/batch")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_batch_returns_filenames(client: AsyncClient) -> None:
    """The batch response should include the original filenames."""
    mock_storage = MagicMock()
    mock_storage.upload_bytes = AsyncMock()

    now = datetime.now(UTC)
    fake_job = {
        "id": uuid4(),
        "filename": "report.pdf",
        "status": "pending",
        "stage": "uploading",
        "progress": {},
        "error": None,
        "parent_job_id": None,
        "metadata_": {},
        "created_at": now,
        "updated_at": now,
    }

    with (
        patch("app.ingestion.router.get_minio", return_value=mock_storage),
        patch("app.ingestion.router.process_document") as mock_task,
        patch(
            "app.ingestion.service.IngestionService.create_job",
            new_callable=AsyncMock,
            return_value=fake_job,
        ),
    ):
        mock_task.delay = MagicMock()
        response = await client.post(
            "/api/v1/ingest/batch",
            files=[("files", ("report.pdf", b"pdf content", "application/pdf"))],
        )

    body = response.json()
    assert "report.pdf" in body["filenames"]


@pytest.mark.asyncio
async def test_batch_with_zip(client: AsyncClient) -> None:
    """ZIP files submitted via batch should be accepted (processed by task layer)."""
    mock_storage = MagicMock()
    mock_storage.upload_bytes = AsyncMock()

    now = datetime.now(UTC)
    fake_job = {
        "id": uuid4(),
        "filename": "archive.zip",
        "status": "pending",
        "stage": "uploading",
        "progress": {},
        "error": None,
        "parent_job_id": None,
        "metadata_": {},
        "created_at": now,
        "updated_at": now,
    }

    with (
        patch("app.ingestion.router.get_minio", return_value=mock_storage),
        patch("app.ingestion.router.process_document") as mock_task,
        patch(
            "app.ingestion.service.IngestionService.create_job",
            new_callable=AsyncMock,
            return_value=fake_job,
        ),
    ):
        mock_task.delay = MagicMock()
        response = await client.post(
            "/api/v1/ingest/batch",
            files=[("files", ("archive.zip", b"PK fake zip", "application/zip"))],
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total_files"] == 1
    assert "archive.zip" in body["filenames"]


@pytest.mark.asyncio
async def test_batch_mixed_formats(client: AsyncClient) -> None:
    """Batch with mixed file types should accept all of them."""
    mock_storage = MagicMock()
    mock_storage.upload_bytes = AsyncMock()

    now = datetime.now(UTC)
    jobs_created = 0

    async def make_fake_job(**kwargs):
        nonlocal jobs_created
        jobs_created += 1
        return {
            "id": uuid4(),
            "filename": kwargs.get("filename", f"file{jobs_created}"),
            "status": "pending",
            "stage": "uploading",
            "progress": {},
            "error": None,
            "parent_job_id": None,
            "metadata_": {},
            "created_at": now,
            "updated_at": now,
        }

    with (
        patch("app.ingestion.router.get_minio", return_value=mock_storage),
        patch("app.ingestion.router.process_document") as mock_task,
        patch(
            "app.ingestion.service.IngestionService.create_job",
            side_effect=make_fake_job,
        ),
    ):
        mock_task.delay = MagicMock()
        response = await client.post(
            "/api/v1/ingest/batch",
            files=[
                ("files", ("doc.pdf", b"pdf", "application/pdf")),
                ("files", ("data.csv", b"a,b\n1,2", "text/csv")),
            ],
        )

    assert response.status_code == 200
    assert response.json()["total_files"] == 2
