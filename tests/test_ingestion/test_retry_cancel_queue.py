"""Tests for retry, cancel-with-revoke, and queue pause/resume endpoints.

Validates:
- POST /jobs/{job_id}/retry — happy path, non-failed returns 409, not found returns 404
- DELETE /jobs/{job_id} — cancel with Celery revocation
- POST /admin/queues/{queue_name}/pause — pause/resume endpoints
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job(
    status: str = "pending",
    task_type: str = "ingestion",
    minio_path: str = "raw/abc/test.pdf",
    **overrides,
) -> dict:
    """Create a fake job dict for testing."""
    now = datetime.now(UTC)
    job = {
        "id": uuid4(),
        "filename": "test.pdf",
        "status": status,
        "stage": "uploading",
        "progress": {},
        "error": None,
        "parent_job_id": None,
        "matter_id": uuid4(),
        "metadata_": {"minio_path": minio_path},
        "task_type": task_type,
        "label": None,
        "created_at": now,
        "updated_at": now,
    }
    job.update(overrides)
    return job


# ---------------------------------------------------------------------------
# Tests: POST /jobs/{job_id}/retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_failed_job(client: AsyncClient) -> None:
    """POST /jobs/{job_id}/retry on a failed job should reset and re-dispatch."""
    job_id = uuid4()
    failed_job = _make_job(id=job_id, status="failed")
    retried_row = {
        "id": job_id,
        "filename": "test.pdf",
        "metadata_": {"minio_path": "raw/abc/test.pdf"},
        "task_type": "ingestion",
        "matter_id": uuid4(),
    }

    with (
        patch(
            "app.ingestion.service.IngestionService.get_job",
            new_callable=AsyncMock,
            return_value=failed_job,
        ),
        patch(
            "app.ingestion.service.IngestionService.retry_job",
            new_callable=AsyncMock,
            return_value=retried_row,
        ),
        patch("app.ingestion.router.process_document") as mock_task,
    ):
        mock_task.apply_async = MagicMock()
        response = await client.post(f"/api/v1/jobs/{job_id}/retry")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "retried"
    assert body["job_id"] == str(job_id)
    mock_task.apply_async.assert_called_once()


@pytest.mark.asyncio
async def test_retry_non_failed_job_returns_409(client: AsyncClient) -> None:
    """POST /jobs/{job_id}/retry on a non-failed job should return 409."""
    job_id = uuid4()
    active_job = _make_job(id=job_id, status="processing")

    with (
        patch(
            "app.ingestion.service.IngestionService.get_job",
            new_callable=AsyncMock,
            return_value=active_job,
        ),
        patch(
            "app.ingestion.service.IngestionService.retry_job",
            new_callable=AsyncMock,
            return_value=None,  # retry_job returns None for non-failed jobs
        ),
    ):
        response = await client.post(f"/api/v1/jobs/{job_id}/retry")

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_retry_not_found_returns_404(client: AsyncClient) -> None:
    """POST /jobs/{job_id}/retry for nonexistent job should return 404."""
    with patch(
        "app.ingestion.service.IngestionService.get_job",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await client.post(f"/api/v1/jobs/{uuid4()}/retry")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_retry_complete_job_returns_409(client: AsyncClient) -> None:
    """POST /jobs/{job_id}/retry on a completed job should return 409."""
    job_id = uuid4()
    complete_job = _make_job(id=job_id, status="complete")

    with (
        patch(
            "app.ingestion.service.IngestionService.get_job",
            new_callable=AsyncMock,
            return_value=complete_job,
        ),
        patch(
            "app.ingestion.service.IngestionService.retry_job",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        response = await client.post(f"/api/v1/jobs/{job_id}/retry")

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Tests: DELETE /jobs/{job_id} — cancel with Celery revocation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_job_revokes_celery_task(client: AsyncClient) -> None:
    """DELETE /jobs/{job_id} should revoke the Celery task when celery_task_id exists."""
    job_id = uuid4()
    active_job = _make_job(id=job_id, status="processing")
    celery_task_id = "celery-task-abc123"

    with (
        patch(
            "app.ingestion.service.IngestionService.get_job",
            new_callable=AsyncMock,
            return_value=active_job,
        ),
        patch(
            "app.ingestion.service.IngestionService.cancel_job",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "app.ingestion.service.IngestionService.get_celery_task_id",
            new_callable=AsyncMock,
            return_value=celery_task_id,
        ),
        patch("app.ingestion.router.celery_app", create=True),
    ):
        # Mock celery_app.control.revoke (imported inside the function)
        mock_control = MagicMock()
        with patch("workers.celery_app.celery_app") as mock_app:
            mock_app.control = mock_control
            response = await client.delete(f"/api/v1/jobs/{job_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    mock_control.revoke.assert_called_once_with(celery_task_id, terminate=True, signal="SIGTERM")


@pytest.mark.asyncio
async def test_cancel_job_without_celery_task_id(client: AsyncClient) -> None:
    """DELETE /jobs/{job_id} should succeed even without a celery_task_id."""
    job_id = uuid4()
    active_job = _make_job(id=job_id, status="processing")

    with (
        patch(
            "app.ingestion.service.IngestionService.get_job",
            new_callable=AsyncMock,
            return_value=active_job,
        ),
        patch(
            "app.ingestion.service.IngestionService.cancel_job",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "app.ingestion.service.IngestionService.get_celery_task_id",
            new_callable=AsyncMock,
            return_value=None,  # No Celery task ID
        ),
    ):
        response = await client.delete(f"/api/v1/jobs/{job_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_terminal_job_returns_409(client: AsyncClient) -> None:
    """DELETE /jobs/{job_id} for an already-completed job should return 409."""
    job_id = uuid4()
    complete_job = _make_job(id=job_id, status="complete")

    with (
        patch(
            "app.ingestion.service.IngestionService.get_job",
            new_callable=AsyncMock,
            return_value=complete_job,
        ),
        patch(
            "app.ingestion.service.IngestionService.cancel_job",
            new_callable=AsyncMock,
            return_value=False,  # Already terminal
        ),
    ):
        response = await client.delete(f"/api/v1/jobs/{job_id}")

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Tests: POST /admin/queues/{queue_name}/pause + resume
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_valid_queue(client: AsyncClient) -> None:
    """POST /admin/queues/bulk/pause should call cancel_consumer."""
    with patch("workers.celery_app.celery_app") as mock_app:
        mock_app.control = MagicMock()
        response = await client.post("/api/v1/admin/queues/bulk/pause")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "paused"
    assert body["queue"] == "bulk"
    mock_app.control.cancel_consumer.assert_called_once_with("bulk")


@pytest.mark.asyncio
async def test_resume_valid_queue(client: AsyncClient) -> None:
    """POST /admin/queues/bulk/resume should call add_consumer."""
    with patch("workers.celery_app.celery_app") as mock_app:
        mock_app.control = MagicMock()
        response = await client.post("/api/v1/admin/queues/bulk/resume")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resumed"
    assert body["queue"] == "bulk"
    mock_app.control.add_consumer.assert_called_once_with("bulk")


@pytest.mark.asyncio
async def test_pause_invalid_queue_returns_400(client: AsyncClient) -> None:
    """POST /admin/queues/nonexistent/pause should return 400."""
    response = await client.post("/api/v1/admin/queues/nonexistent/pause")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_resume_invalid_queue_returns_400(client: AsyncClient) -> None:
    """POST /admin/queues/nonexistent/resume should return 400."""
    response = await client.post("/api/v1/admin/queues/nonexistent/resume")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_pause_all_valid_queues(client: AsyncClient) -> None:
    """All three queue names (default, bulk, background) should be pauseable."""
    for queue_name in ("default", "bulk", "background"):
        with patch("workers.celery_app.celery_app") as mock_app:
            mock_app.control = MagicMock()
            response = await client.post(f"/api/v1/admin/queues/{queue_name}/pause")
        assert response.status_code == 200, f"Failed for queue: {queue_name}"
