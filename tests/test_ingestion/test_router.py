"""Tests for the ingestion API endpoints.

These tests run against the FastAPI app with mocked backends (no Docker required).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

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
    now = datetime.now(UTC)
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
        mock_task.apply_async = MagicMock()
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
    mock_task.apply_async.assert_called_once()


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
    now = datetime.now(UTC)
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
async def test_list_jobs_with_task_type_filter(client: AsyncClient) -> None:
    """GET /jobs?task_type=entity_resolution passes task_type to service."""
    with patch(
        "app.ingestion.service.IngestionService.list_jobs",
        new_callable=AsyncMock,
        return_value=([], 0),
    ) as mock_list:
        response = await client.get("/api/v1/jobs?task_type=entity_resolution")

    assert response.status_code == 200
    # Verify task_type was forwarded
    call_kwargs = mock_list.call_args
    assert call_kwargs.kwargs.get("task_type") == "entity_resolution"


@pytest.mark.asyncio
async def test_list_jobs_returns_task_type_fields(client: AsyncClient) -> None:
    """GET /jobs returns task_type and label fields in response."""
    now = datetime.now(UTC)
    fake_jobs = [
        {
            "id": uuid4(),
            "filename": None,
            "status": "extracting",
            "stage": "loading_entities",
            "progress": {},
            "error": None,
            "parent_job_id": None,
            "matter_id": uuid4(),
            "metadata_": {},
            "task_type": "entity_resolution",
            "label": "Entity resolution: person",
            "created_at": now,
            "updated_at": now,
        }
    ]

    with patch(
        "app.ingestion.service.IngestionService.list_jobs",
        new_callable=AsyncMock,
        return_value=(fake_jobs, 1),
    ):
        response = await client.get("/api/v1/jobs")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["task_type"] == "entity_resolution"
    assert item["label"] == "Entity resolution: person"
    assert item["filename"] is None


@pytest.mark.asyncio
async def test_batch_requires_files(client: AsyncClient) -> None:
    """POST /ingest/batch without files should return 422."""
    response = await client.post("/api/v1/ingest/batch")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_webhook_requires_body(client: AsyncClient) -> None:
    """POST /ingest/webhook without a JSON body should return 422."""
    response = await client.post("/api/v1/ingest/webhook")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /ingest/reindex
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reindex_dispatches_jobs(client: AsyncClient) -> None:
    """POST /ingest/reindex with valid doc_ids creates jobs and dispatches tasks."""
    doc_id = uuid4()
    fake_job_id = uuid4()
    now = datetime.now(UTC)
    fake_job = {
        "id": fake_job_id,
        "filename": "test.pdf",
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
        patch("app.ingestion.router.process_document") as mock_task,
        patch(
            "app.ingestion.service.IngestionService.get_documents_for_reindex",
            new_callable=AsyncMock,
            return_value=[{"id": doc_id, "filename": "test.pdf", "minio_path": "raw/abc/test.pdf"}],
        ),
        patch(
            "app.ingestion.service.IngestionService.create_job",
            new_callable=AsyncMock,
            return_value=fake_job,
        ),
    ):
        mock_task.apply_async = MagicMock()

        response = await client.post(
            "/api/v1/ingest/reindex",
            json={"doc_ids": [str(doc_id)]},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total_files"] == 1
    assert len(body["job_ids"]) == 1
    mock_task.apply_async.assert_called_once()
    # Verify the real minio_path was used, not reindex/{doc_id}
    call_args = mock_task.apply_async.call_args
    assert call_args[1]["args"][1] == "raw/abc/test.pdf"
    assert call_args[1]["queue"] == "bulk"


@pytest.mark.asyncio
async def test_reindex_404_when_no_docs(client: AsyncClient) -> None:
    """POST /ingest/reindex with no matching docs returns 404."""
    with patch(
        "app.ingestion.service.IngestionService.get_documents_for_reindex",
        new_callable=AsyncMock,
        return_value=[],
    ):
        response = await client.post(
            "/api/v1/ingest/reindex",
            json={"doc_ids": [str(uuid4())]},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reindex_empty_list_422(client: AsyncClient) -> None:
    """POST /ingest/reindex with empty doc_ids returns 422."""
    response = await client.post(
        "/api/v1/ingest/reindex",
        json={"doc_ids": []},
    )
    assert response.status_code == 422
