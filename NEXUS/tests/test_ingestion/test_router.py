"""Tests for the ingestion API endpoints.

These tests run against the FastAPI app with mocked backends (no Docker required).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ingest_requires_file(client: AsyncClient) -> None:
    """POST /ingest without a file should return 422."""
    response = await client.post("/api/v1/ingest")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ingest_rejects_empty_file(client: AsyncClient) -> None:
    """POST /ingest with an empty file should return 400."""
    response = await client.post(
        "/api/v1/ingest",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_ingest_accepts_file(client: AsyncClient) -> None:
    """POST /ingest with valid file should return 200 with job_id."""
    mock_storage = MagicMock()
    mock_storage.upload_bytes = AsyncMock(return_value="raw/test/file.txt")

    fake_job_id = uuid4()
    now = datetime.now(timezone.utc)
    fake_job = {
        "id": fake_job_id,
        "filename": "test.txt",
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
        patch("app.ingestion.service.IngestionService.create_job", new_callable=AsyncMock) as mock_create,
    ):
        mock_task.delay = MagicMock()
        mock_create.return_value = fake_job

        response = await client.post(
            "/api/v1/ingest",
            files={"file": ("test.txt", b"Hello world content", "text/plain")},
        )

    assert response.status_code == 200
    body = response.json()
    assert "job_id" in body
    assert body["filename"] == "test.txt"
    assert body["status"] == "pending"
    mock_task.delay.assert_called_once()


@pytest.mark.asyncio
async def test_get_job_not_found(client: AsyncClient) -> None:
    """GET /jobs/{id} for nonexistent job should return 404."""
    with patch(
        "app.ingestion.service.IngestionService.get_job",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_job_found(client: AsyncClient) -> None:
    """GET /jobs/{id} for existing job should return 200 with job details."""
    now = datetime.now(timezone.utc)
    fake_job = {
        "id": uuid4(),
        "filename": "test.pdf",
        "status": "uploading",
        "stage": "parsing",
        "progress": {"pages_parsed": 5},
        "error": None,
        "parent_job_id": None,
        "metadata_": {},
        "created_at": now,
        "updated_at": now,
    }

    with patch(
        "app.ingestion.service.IngestionService.get_job",
        new_callable=AsyncMock,
        return_value=fake_job,
    ):
        response = await client.get(f"/api/v1/jobs/{fake_job['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "test.pdf"
    assert body["stage"] == "parsing"
    assert body["progress"]["pages_parsed"] == 5


@pytest.mark.asyncio
async def test_list_jobs(client: AsyncClient) -> None:
    """GET /jobs should return a paginated list."""
    with patch(
        "app.ingestion.service.IngestionService.list_jobs",
        new_callable=AsyncMock,
        return_value=([], 0),
    ):
        response = await client.get("/api/v1/jobs")

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_batch_returns_501(client: AsyncClient) -> None:
    """POST /ingest/batch should return 501 (not implemented)."""
    response = await client.post("/api/v1/ingest/batch")
    assert response.status_code == 501


@pytest.mark.asyncio
async def test_webhook_returns_501(client: AsyncClient) -> None:
    """POST /ingest/webhook should return 501 (not implemented)."""
    response = await client.post("/api/v1/ingest/webhook")
    assert response.status_code == 501
