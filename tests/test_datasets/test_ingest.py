"""Tests for dataset ingestion endpoints.

Tests the ingest, dry-run, and status endpoints with mocked adapters and Celery.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from httpx import AsyncClient

from app.datasets.schemas import DatasetResponse
from app.dependencies import get_db
from app.ingestion.bulk_import import ImportDocument

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MATTER_ID = UUID("00000000-0000-0000-0000-000000000001")
_DATASET_ID = UUID("00000000-0000-0000-0000-000000000010")
_BULK_JOB_ID = "00000000-0000-0000-0000-000000000099"
_NOW = datetime(2025, 1, 1, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dataset_response(**overrides) -> DatasetResponse:
    defaults = dict(
        id=_DATASET_ID,
        matter_id=_MATTER_ID,
        name="Test Dataset",
        description="",
        parent_id=None,
        document_count=0,
        children_count=0,
        created_by=None,
        created_at=_NOW,
        updated_at=_NOW,
    )
    defaults.update(overrides)
    return DatasetResponse(**defaults)


async def _mock_db_gen():
    mock = AsyncMock()
    yield mock


def _override_db(app):
    app.dependency_overrides[get_db] = _mock_db_gen
    return app


def _make_test_docs(count: int = 3) -> list[ImportDocument]:
    return [
        ImportDocument(
            filename=f"doc_{i}.txt",
            text=f"Content of document {i}" * 50,
            content_hash=f"hash{i}",
            source="test",
        )
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# POST /datasets/{id}/ingest — kick off import
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_dataset(client: AsyncClient, tmp_path) -> None:
    """POST ingest should create a bulk job and dispatch the Celery task."""
    # Create a temp directory with test files
    test_dir = tmp_path / "test_docs"
    test_dir.mkdir()
    for i in range(3):
        (test_dir / f"doc_{i}.txt").write_text(f"Content of document {i}")

    app = client._transport.app
    _override_db(app)

    mock_task = MagicMock()
    mock_task.delay = MagicMock()

    try:
        with (
            patch(
                "app.datasets.router.DatasetService.get_dataset",
                new_callable=AsyncMock,
                return_value=_make_dataset_response(),
            ),
            patch(
                "app.datasets.router.run_bulk_import",
                mock_task,
            ),
            patch(
                "app.ingestion.bulk_import.create_bulk_import_job",
                return_value=_BULK_JOB_ID,
            ) as mock_create_job,
            patch(
                "app.ingestion.bulk_import._get_sync_engine",
                return_value=MagicMock(),
            ),
        ):
            response = await client.post(
                f"/api/v1/datasets/{_DATASET_ID}/ingest",
                json={
                    "adapter_type": "directory",
                    "source_path": str(test_dir),
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    data = response.json()
    assert data["bulk_job_id"] == _BULK_JOB_ID
    assert data["total_documents"] == 3
    assert data["status"] == "processing"
    mock_task.delay.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_bad_adapter_type(client: AsyncClient) -> None:
    """POST ingest with invalid adapter type should return 400."""
    app = client._transport.app
    _override_db(app)

    try:
        with patch(
            "app.datasets.router.DatasetService.get_dataset",
            new_callable=AsyncMock,
            return_value=_make_dataset_response(),
        ):
            response = await client.post(
                f"/api/v1/datasets/{_DATASET_ID}/ingest",
                json={
                    "adapter_type": "nonexistent",
                    "source_path": "/tmp/nope",
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 400
    assert "Unknown adapter" in response.json()["detail"]


@pytest.mark.asyncio
async def test_ingest_nonexistent_path(client: AsyncClient) -> None:
    """POST ingest with nonexistent path should return 400."""
    app = client._transport.app
    _override_db(app)

    try:
        with patch(
            "app.datasets.router.DatasetService.get_dataset",
            new_callable=AsyncMock,
            return_value=_make_dataset_response(),
        ):
            response = await client.post(
                f"/api/v1/datasets/{_DATASET_ID}/ingest",
                json={
                    "adapter_type": "directory",
                    "source_path": "/nonexistent/path/that/should/not/exist",
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]


@pytest.mark.asyncio
async def test_ingest_nonexistent_dataset(client: AsyncClient) -> None:
    """POST ingest for nonexistent dataset should return 404."""
    app = client._transport.app
    _override_db(app)

    try:
        with patch(
            "app.datasets.router.DatasetService.get_dataset",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = await client.post(
                f"/api/v1/datasets/{_DATASET_ID}/ingest",
                json={
                    "adapter_type": "directory",
                    "source_path": "/tmp",
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /datasets/{id}/ingest/dry-run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run(client: AsyncClient, tmp_path) -> None:
    """POST dry-run should return cost estimates without dispatching tasks."""
    test_dir = tmp_path / "dry_run_docs"
    test_dir.mkdir()
    for i in range(5):
        (test_dir / f"doc_{i}.txt").write_text(f"Test content for dry run {i}" * 100)

    app = client._transport.app
    _override_db(app)

    try:
        with patch(
            "app.datasets.router.DatasetService.get_dataset",
            new_callable=AsyncMock,
            return_value=_make_dataset_response(),
        ):
            response = await client.post(
                f"/api/v1/datasets/{_DATASET_ID}/ingest/dry-run",
                json={
                    "adapter_type": "directory",
                    "source_path": str(test_dir),
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    data = response.json()
    assert data["total_documents"] == 5
    assert data["total_characters"] > 0
    assert data["estimated_chunks"] > 0
    assert data["estimated_tokens"] > 0
    assert data["estimated_cost_usd"] >= 0


@pytest.mark.asyncio
async def test_dry_run_nonexistent_dataset(client: AsyncClient) -> None:
    """POST dry-run for nonexistent dataset should return 404."""
    app = client._transport.app
    _override_db(app)

    try:
        with patch(
            "app.datasets.router.DatasetService.get_dataset",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = await client.post(
                f"/api/v1/datasets/{_DATASET_ID}/ingest/dry-run",
                json={
                    "adapter_type": "directory",
                    "source_path": "/tmp",
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /datasets/{id}/ingest/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_ingest_jobs(client: AsyncClient) -> None:
    """GET ingest/status should return bulk job list."""
    app = client._transport.app
    _override_db(app)

    mock_row = MagicMock()
    mock_row.id = _BULK_JOB_ID
    mock_row.status = "processing"
    mock_row.adapter_type = "directory"
    mock_row.source_path = "/data/test"
    mock_row.total_documents = 100
    mock_row.processed_documents = 50
    mock_row.failed_documents = 2
    mock_row.skipped_documents = 5
    mock_row.created_at = _NOW
    mock_row.completed_at = None
    mock_row.error = None

    mock_result = MagicMock()
    mock_result.fetchall.return_value = [mock_row]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def _mock_db_with_data():
        yield mock_db

    app.dependency_overrides[get_db] = _mock_db_with_data

    try:
        with patch(
            "app.datasets.router.DatasetService.get_dataset",
            new_callable=AsyncMock,
            return_value=_make_dataset_response(),
        ):
            response = await client.get(
                f"/api/v1/datasets/{_DATASET_ID}/ingest/status",
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == _BULK_JOB_ID
    assert data[0]["status"] == "processing"
    assert data[0]["total_documents"] == 100
    assert data[0]["processed_documents"] == 50


# ---------------------------------------------------------------------------
# GET /datasets/{id}/ingest/{bulk_job_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_ingest_job(client: AsyncClient) -> None:
    """GET ingest/{bulk_job_id} should return single job progress."""
    app = client._transport.app

    mock_row = MagicMock()
    mock_row.id = _BULK_JOB_ID
    mock_row.status = "complete"
    mock_row.adapter_type = "huggingface_csv"
    mock_row.source_path = "/data/dataset.parquet"
    mock_row.total_documents = 200
    mock_row.processed_documents = 195
    mock_row.failed_documents = 3
    mock_row.skipped_documents = 2
    mock_row.created_at = _NOW
    mock_row.completed_at = _NOW
    mock_row.error = None

    mock_result = MagicMock()
    mock_result.first.return_value = mock_row

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def _mock_db_with_data():
        yield mock_db

    app.dependency_overrides[get_db] = _mock_db_with_data

    try:
        response = await client.get(
            f"/api/v1/datasets/{_DATASET_ID}/ingest/{_BULK_JOB_ID}",
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == _BULK_JOB_ID
    assert data["status"] == "complete"
    assert data["total_documents"] == 200


@pytest.mark.asyncio
async def test_get_ingest_job_not_found(client: AsyncClient) -> None:
    """GET ingest/{bulk_job_id} for nonexistent job should return 404."""
    app = client._transport.app

    mock_result = MagicMock()
    mock_result.first.return_value = None

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def _mock_db_with_data():
        yield mock_db

    app.dependency_overrides[get_db] = _mock_db_with_data

    try:
        response = await client.get(
            f"/api/v1/datasets/{_DATASET_ID}/ingest/{_BULK_JOB_ID}",
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# run_bulk_import Celery task
# ---------------------------------------------------------------------------


def test_run_bulk_import_task() -> None:
    """Test the run_bulk_import Celery task with mocked adapter."""

    test_docs = _make_test_docs(3)

    mock_adapter = MagicMock()
    mock_adapter.iter_documents.return_value = iter(test_docs)

    mock_engine = MagicMock()

    mock_import_task = MagicMock()
    mock_import_task.delay = MagicMock()

    with (
        patch(
            "app.ingestion.tasks._get_sync_engine",
            return_value=mock_engine,
        ),
        patch(
            "app.ingestion.bulk_import.build_adapter",
            return_value=mock_adapter,
        ),
        patch(
            "app.ingestion.bulk_import.check_resume",
            return_value=False,
        ),
        patch(
            "app.ingestion.bulk_import.create_job_row",
        ) as mock_create_job,
        patch(
            "app.ingestion.bulk_import.complete_bulk_job",
        ) as mock_complete,
        patch(
            "app.ingestion.bulk_import.dispatch_post_ingestion_hooks",
            return_value=[],
        ),
        patch(
            "app.ingestion.tasks.import_text_document",
            mock_import_task,
        ),
    ):
        from app.ingestion.tasks import run_bulk_import

        # Call the task function directly (not via Celery)
        mock_self = MagicMock()
        mock_self.request.id = "test-task-id"

        result = run_bulk_import.__wrapped__(
            mock_self,
            bulk_job_id=_BULK_JOB_ID,
            adapter_type="directory",
            source_config={"data_dir": "/tmp/test"},
            matter_id=str(_MATTER_ID),
            dataset_id=str(_DATASET_ID),
            options={"resume": False, "limit": None, "disable_hnsw": False},
        )

    assert result["status"] == "complete"
    assert result["dispatched"] == 3
    assert result["skipped"] == 0
    assert mock_import_task.delay.call_count == 3
    mock_complete.assert_called_once_with(mock_engine, _BULK_JOB_ID, "complete")
