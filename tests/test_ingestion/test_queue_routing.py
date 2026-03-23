"""Tests for Celery queue routing, time limit handling, and task configuration.

Validates that:
- process_document dispatches to the correct queue based on context
- SoftTimeLimitExceeded is caught and sets job to failed
- _store_celery_task_id writes the task ID to the job row
- Celery app has correct queue, routing, and time limit configuration
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from httpx import AsyncClient

from app.ingestion.tasks import process_document

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_settings() -> MagicMock:
    """Create a mock Settings object with safe defaults for tests."""
    s = MagicMock()
    s.minio_use_ssl = False
    s.minio_endpoint = "localhost:9000"
    s.minio_access_key = "test"
    s.minio_secret_key = "test"
    s.minio_bucket = "test"
    s.postgres_url_sync = "postgresql://test:test@localhost/test"
    s.qdrant_url = "http://localhost:6333"
    s.neo4j_uri = "bolt://localhost:7687"
    s.neo4j_user = "neo4j"
    s.neo4j_password = "test"
    s.chunk_size = 512
    s.chunk_overlap = 64
    s.enable_visual_embeddings = False
    s.enable_sparse_embeddings = False
    s.enable_relationship_extraction = False
    s.enable_email_threading = False
    s.enable_near_duplicate_detection = False
    s.enable_hot_doc_detection = False
    s.gliner_model = "test-model"
    s.embedding_provider = "openai"
    s.openai_api_key = "test-key"
    s.embedding_model = "text-embedding-3-large"
    s.embedding_dimensions = 1024
    s.embedding_batch_size = 100
    return s


# ---------------------------------------------------------------------------
# Tests: Celery app configuration
# ---------------------------------------------------------------------------


def test_celery_app_has_four_queues():
    """Celery app should define default, bulk, ner, and background queues."""
    from workers.celery_app import celery_app

    queue_names = {q.name for q in celery_app.conf.task_queues}
    assert queue_names == {"default", "bulk", "ner", "background"}


def test_celery_app_default_queue():
    """Default queue should be 'default'."""
    from workers.celery_app import celery_app

    assert celery_app.conf.task_default_queue == "default"


def test_celery_app_task_routes():
    """Background modules should route to the 'background' queue."""
    from workers.celery_app import celery_app

    routes = celery_app.conf.task_routes
    assert routes["app.entities.tasks.*"]["queue"] == "background"
    assert routes["app.analysis.tasks.*"]["queue"] == "background"
    assert routes["app.cases.tasks.*"]["queue"] == "background"
    assert routes["app.exports.tasks.*"]["queue"] == "background"


def test_celery_app_time_limits():
    """Global time limits should be set (30 min soft, 35 min hard)."""
    from workers.celery_app import celery_app

    assert celery_app.conf.task_soft_time_limit == 1800
    assert celery_app.conf.task_hard_time_limit == 2100


def test_celery_app_rate_limits():
    """LLM-bound tasks should have rate limits configured."""
    from workers.celery_app import celery_app

    annotations = celery_app.conf.task_annotations
    assert annotations["app.analysis.tasks.scan_document_sentiment"]["rate_limit"] == "10/m"
    assert annotations["app.cases.tasks.run_case_setup"]["rate_limit"] == "2/m"


def test_celery_app_result_expiry():
    """Results should expire after 24 hours."""
    from workers.celery_app import celery_app

    assert celery_app.conf.result_expires == 86400


# ---------------------------------------------------------------------------
# Tests: Queue routing at dispatch time
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_ingest_routes_to_default_queue(client: AsyncClient) -> None:
    """POST /ingest single file should dispatch to the 'default' queue."""
    mock_storage = MagicMock()
    mock_storage.upload_bytes = AsyncMock(return_value="raw/test/file.txt")

    from datetime import UTC, datetime

    now = datetime.now(UTC)
    fake_job = {
        "id": uuid4(),
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
            files={"file": ("test.txt", b"Hello world", "text/plain")},
        )

    assert response.status_code == 200
    mock_task.apply_async.assert_called_once()
    call_kwargs = mock_task.apply_async.call_args
    assert call_kwargs[1]["queue"] == "default"


@pytest.mark.asyncio
async def test_reindex_routes_to_bulk_queue(client: AsyncClient) -> None:
    """POST /ingest/reindex should always dispatch to the 'bulk' queue."""
    doc_id = uuid4()
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    fake_job = {
        "id": uuid4(),
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
    call_kwargs = mock_task.apply_async.call_args
    assert call_kwargs[1]["queue"] == "bulk"


@pytest.mark.asyncio
async def test_small_batch_routes_to_default_queue(client: AsyncClient) -> None:
    """POST /ingest/batch with <=10 files should dispatch to 'default' queue."""
    mock_storage = MagicMock()
    mock_storage.upload_bytes = AsyncMock()

    from datetime import UTC, datetime

    now = datetime.now(UTC)

    async def make_job(**kwargs):
        return {
            "id": uuid4(),
            "filename": kwargs.get("filename", "file.txt"),
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
        patch("app.ingestion.service.IngestionService.create_job", side_effect=make_job),
    ):
        mock_task.apply_async = MagicMock()
        response = await client.post(
            "/api/v1/ingest/batch",
            files=[
                ("files", ("a.txt", b"content", "text/plain")),
                ("files", ("b.txt", b"content", "text/plain")),
            ],
        )

    assert response.status_code == 200
    # Both dispatches should use "default" since <= 10 files
    for call in mock_task.apply_async.call_args_list:
        assert call[1]["queue"] == "default"


# ---------------------------------------------------------------------------
# Tests: SoftTimeLimitExceeded handling
# ---------------------------------------------------------------------------


def test_soft_time_limit_sets_job_to_failed():
    """When SoftTimeLimitExceeded is raised, the job should be marked failed with timeout error."""
    mock_engine = MagicMock()

    with (
        patch("app.config.Settings", return_value=_make_mock_settings()),
        patch("app.ingestion.tasks._get_sync_engine", return_value=mock_engine),
        patch("app.ingestion.tasks._store_celery_task_id"),
        patch("app.ingestion.tasks._get_job_matter_id", return_value=None),
        patch("app.ingestion.tasks._get_job_dataset_id", return_value=None),
        patch("app.ingestion.tasks._is_job_cancelled", return_value=False),
        patch("app.ingestion.tasks._stage_parse", side_effect=SoftTimeLimitExceeded()),
        patch("app.ingestion.tasks._update_stage") as mock_update_stage,
    ):
        # __wrapped__ bypasses Celery decorator; 2 args (no self)
        result = process_document.__wrapped__("job-001", "raw/job-001/test.pdf")

    assert result["status"] == "failed"
    assert result["error"] == "timeout"
    # The timeout handler calls _update_stage with "failed" stage
    update_calls = [c for c in mock_update_stage.call_args_list if c.args[2] == "failed"]
    assert len(update_calls) >= 1


def test_soft_time_limit_disposes_engine():
    """Engine.dispose() should be called after SoftTimeLimitExceeded."""
    mock_engine = MagicMock()

    with (
        patch("app.config.Settings", return_value=_make_mock_settings()),
        patch("app.ingestion.tasks._get_sync_engine", return_value=mock_engine),
        patch("app.ingestion.tasks._store_celery_task_id"),
        patch("app.ingestion.tasks._get_job_matter_id", return_value=None),
        patch("app.ingestion.tasks._get_job_dataset_id", return_value=None),
        patch("app.ingestion.tasks._is_job_cancelled", return_value=False),
        patch("app.ingestion.tasks._stage_parse", side_effect=SoftTimeLimitExceeded()),
        patch("app.ingestion.tasks._update_stage"),
    ):
        process_document.__wrapped__("job-001", "raw/job-001/test.pdf")

    mock_engine.dispose.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: _store_celery_task_id
# ---------------------------------------------------------------------------


def test_store_celery_task_id_writes_to_db():
    """_store_celery_task_id should execute an UPDATE with the task ID."""
    from app.ingestion.tasks import _store_celery_task_id

    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    _store_celery_task_id(mock_engine, "job-123", "celery-task-456")

    mock_conn.execute.assert_called_once()
    mock_conn.commit.assert_called_once()
    # Check the params passed to execute
    call_args = mock_conn.execute.call_args
    params = call_args[0][1]
    assert params["job_id"] == "job-123"
    assert params["celery_task_id"] == "celery-task-456"
