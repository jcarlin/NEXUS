"""Tests for task error handling, engine disposal, and edge cases.

Validates that process_document correctly handles failures: updating job
status, disposing the engine, and propagating errors from stage functions.
Also covers ZIP corruption and job cancellation.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.ingestion.tasks import process_document, process_zip

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
# Tests: process_document error handling
# ---------------------------------------------------------------------------


def test_process_document_updates_failed_stage_on_error():
    """When a stage function raises, process_document should call _update_stage with 'failed'."""
    mock_engine = MagicMock()

    with (
        patch("app.config.Settings", return_value=_make_mock_settings()),
        patch("app.ingestion.tasks._get_sync_engine", return_value=mock_engine),
        patch("app.ingestion.tasks._get_job_matter_id", return_value="matter-1"),
        patch("app.ingestion.tasks._is_job_cancelled", return_value=False),
        patch("app.ingestion.tasks._stage_parse", side_effect=RuntimeError("parse boom")),
        patch("app.ingestion.tasks._update_stage") as mock_update_stage,
    ):
        # Use __wrapped__ to bypass Celery decorator
        with pytest.raises(RuntimeError, match="parse boom"):
            process_document.__wrapped__("job-001", "raw/job-001/test.pdf")

        # Verify _update_stage was called with "failed" status
        failed_calls = [
            c
            for c in mock_update_stage.call_args_list
            if len(c.args) >= 4 and c.args[2] == "failed" and c.args[3] == "failed"
        ]
        assert len(failed_calls) >= 1


def test_process_document_disposes_engine_on_failure():
    """Engine.dispose() should be called even when an exception occurs."""
    mock_engine = MagicMock()

    with (
        patch("app.config.Settings", return_value=_make_mock_settings()),
        patch("app.ingestion.tasks._get_sync_engine", return_value=mock_engine),
        patch("app.ingestion.tasks._get_job_matter_id", return_value=None),
        patch("app.ingestion.tasks._is_job_cancelled", return_value=False),
        patch("app.ingestion.tasks._stage_parse", side_effect=RuntimeError("boom")),
        patch("app.ingestion.tasks._update_stage"),
    ):
        with pytest.raises(RuntimeError):
            process_document.__wrapped__("job-001", "raw/job-001/test.pdf")

    mock_engine.dispose.assert_called_once()


def test_process_document_disposes_engine_on_success():
    """Engine.dispose() should also be called on the success path."""
    mock_engine = MagicMock()

    with (
        patch("app.config.Settings", return_value=_make_mock_settings()),
        patch("app.ingestion.tasks._get_sync_engine", return_value=mock_engine),
        patch("app.ingestion.tasks._get_job_matter_id", return_value=None),
        patch("app.ingestion.tasks._is_job_cancelled", return_value=False),
        patch("app.ingestion.tasks._stage_parse"),
        patch("app.ingestion.tasks._stage_chunk"),
        patch("app.ingestion.tasks._stage_embed"),
        patch("app.ingestion.tasks._stage_extract"),
        patch("app.ingestion.tasks._stage_index"),
        patch("app.ingestion.tasks._stage_complete"),
        patch("app.ingestion.tasks._PipelineContext") as mock_ctx_cls,
    ):
        mock_ctx = MagicMock()
        mock_ctx.parse_result.page_count = 1
        mock_ctx.chunks = []
        mock_ctx.all_entities = []
        mock_ctx_cls.return_value = mock_ctx

        result = process_document.__wrapped__("job-001", "raw/job-001/test.pdf")

    mock_engine.dispose.assert_called_once()
    assert result["status"] == "complete"


def test_stage_function_error_propagates_to_task():
    """An error in any stage function should propagate up to the task's except block."""
    mock_engine = MagicMock()

    # Test that errors from _stage_chunk (mid-pipeline) also propagate
    with (
        patch("app.config.Settings", return_value=_make_mock_settings()),
        patch("app.ingestion.tasks._get_sync_engine", return_value=mock_engine),
        patch("app.ingestion.tasks._get_job_matter_id", return_value=None),
        patch("app.ingestion.tasks._is_job_cancelled", return_value=False),
        patch("app.ingestion.tasks._stage_parse"),  # succeeds
        patch("app.ingestion.tasks._stage_chunk", side_effect=ValueError("chunk error")),
        patch("app.ingestion.tasks._update_stage"),
    ):
        with pytest.raises(ValueError, match="chunk error"):
            process_document.__wrapped__("job-001", "raw/job-001/test.pdf")


def test_process_zip_handles_corrupt_zip():
    """Non-ZIP content with .zip extension should raise an error."""
    mock_engine = MagicMock()
    corrupt_zip_bytes = b"this is not a zip file at all"

    with (
        patch("app.config.Settings", return_value=_make_mock_settings()),
        patch("app.ingestion.tasks._get_sync_engine", return_value=mock_engine),
        patch("app.ingestion.tasks._get_job_matter_id", return_value=None),
        patch("app.ingestion.tasks._download_from_minio", return_value=corrupt_zip_bytes),
        patch("app.ingestion.tasks._update_stage"),
    ):
        with pytest.raises(Exception):
            process_zip.__wrapped__("job-001", "raw/job-001/archive.zip")


def test_cancelled_job_returns_early():
    """When _is_job_cancelled returns True, the task should return without processing stages."""
    mock_engine = MagicMock()

    with (
        patch("app.config.Settings", return_value=_make_mock_settings()),
        patch("app.ingestion.tasks._get_sync_engine", return_value=mock_engine),
        patch("app.ingestion.tasks._get_job_matter_id", return_value=None),
        patch("app.ingestion.tasks._is_job_cancelled", return_value=True),
        patch("app.ingestion.tasks._stage_parse") as mock_parse,
    ):
        result = process_document.__wrapped__("job-001", "raw/job-001/test.pdf")

    assert result["status"] == "cancelled"
    # _stage_parse should NOT have been called since job was cancelled
    mock_parse.assert_not_called()
    mock_engine.dispose.assert_called_once()
