"""Tests for pipeline event emission from ingestion tasks.

Validates that process_document, process_zip, and import_text_document
emit the correct TASK_RECEIVED, STAGE_STARTED, STAGE_COMPLETED,
TASK_COMPLETED, TASK_RETRIED, and TASK_FAILED events via record_event().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import SoftTimeLimitExceeded

import app.feature_flags.service  # noqa: F401 — pre-import before Settings gets patched
from app.ingestion.tasks import import_text_document, process_document, process_zip

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_settings() -> MagicMock:
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
    s.defer_ner_to_queue = False
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


@dataclass
class _FakeParseResult:
    pages: list = field(default_factory=list)
    page_count: int = 3


@dataclass
class _FakeChunk:
    text: str = "chunk text"
    chunk_index: int = 0
    token_count: int = 10
    metadata: dict = field(default_factory=lambda: {"page_number": 1})


_STAGE_NAMES = [
    "parse",
    "ocr_correct",
    "chunk",
    "create_document",
    "contextualize",
    "summarize",
    "embed_and_extract",
    "index",
    "complete",
]

_STAGE_FN_NAMES = [
    "_stage_parse",
    "_stage_ocr_correct",
    "_stage_chunk",
    "_stage_create_document",
    "_stage_contextualize",
    "_stage_summarize",
    "_stage_embed_and_extract",
    "_stage_index",
    "_stage_complete",
]


def _set_ctx_fields(ctx):
    """Populate ctx fields that stages normally set, so the task can complete."""
    ctx.parse_result = _FakeParseResult()
    ctx.chunks = [_FakeChunk(), _FakeChunk()]
    ctx.all_entities = [{"name": "Alice", "type": "person"}]


def _base_process_doc_patches(mock_engine):
    """Return the common patch dict for process_document tests."""
    p = {
        "app.config.Settings": MagicMock(return_value=_make_mock_settings()),
        "app.ingestion.tasks._get_sync_engine": MagicMock(return_value=mock_engine),
        "app.feature_flags.service.load_overrides_sync_safe": MagicMock(),
        "app.ingestion.tasks._store_celery_task_id": MagicMock(),
        "app.ingestion.tasks._store_task_metadata": MagicMock(),
        "app.ingestion.tasks._get_job_matter_id": MagicMock(return_value="matter-1"),
        "app.ingestion.tasks._get_job_dataset_id": MagicMock(return_value=None),
        "app.ingestion.tasks._is_job_cancelled": MagicMock(return_value=False),
        "app.ingestion.tasks._mark_job_completed": MagicMock(),
        "app.ingestion.tasks._update_stage": MagicMock(),
        "app.ingestion.tasks.record_event": MagicMock(),
    }
    return p


def _add_stage_patches(patches):
    """Add all 9 stage function patches. _stage_parse populates ctx."""

    def _fake_parse(ctx):
        _set_ctx_fields(ctx)

    for name in _STAGE_FN_NAMES:
        if name == "_stage_parse":
            patches[f"app.ingestion.tasks.{name}"] = _fake_parse
        else:
            patches[f"app.ingestion.tasks.{name}"] = lambda ctx: None


def _apply_patches(patches: dict):
    """Start all patches, return list of active patchers."""
    active = [patch(k, v) for k, v in patches.items()]
    for p in active:
        p.start()
    return active


def _stop_patches(active: list):
    for p in active:
        p.stop()


# ---------------------------------------------------------------------------
# process_document events
# ---------------------------------------------------------------------------


def test_process_document_emits_task_received():
    """TASK_RECEIVED is emitted before stages begin."""
    mock_engine = MagicMock()
    patches = _base_process_doc_patches(mock_engine)
    _add_stage_patches(patches)
    active = _apply_patches(patches)

    try:
        process_document.__wrapped__("job-001", "raw/job-001/test.pdf")
        mock_record = patches["app.ingestion.tasks.record_event"]

        first_call = mock_record.call_args_list[0]
        assert first_call[0][1] == "job-001"
        assert first_call[0][2] == "TASK_RECEIVED"
        assert first_call[1]["detail"]["filename"] == "test.pdf"
    finally:
        _stop_patches(active)


def test_process_document_emits_stage_events():
    """Each of the 9 stages emits STAGE_STARTED + STAGE_COMPLETED."""
    mock_engine = MagicMock()
    patches = _base_process_doc_patches(mock_engine)
    _add_stage_patches(patches)
    active = _apply_patches(patches)

    try:
        process_document.__wrapped__("job-001", "raw/job-001/test.pdf")
        mock_record = patches["app.ingestion.tasks.record_event"]

        started = [c for c in mock_record.call_args_list if c[0][2] == "STAGE_STARTED"]
        completed = [c for c in mock_record.call_args_list if c[0][2] == "STAGE_COMPLETED"]

        assert len(started) == 9
        assert len(completed) == 9

        for i, name in enumerate(_STAGE_NAMES):
            assert started[i][1]["detail"]["stage"] == name
            assert completed[i][1]["detail"]["stage"] == name

        for c in completed:
            assert "duration_ms" in c[1]
            assert isinstance(c[1]["duration_ms"], int)
    finally:
        _stop_patches(active)


def test_process_document_emits_task_completed():
    """TASK_COMPLETED is emitted after all stages with duration and result details."""
    mock_engine = MagicMock()
    patches = _base_process_doc_patches(mock_engine)
    _add_stage_patches(patches)
    active = _apply_patches(patches)

    try:
        process_document.__wrapped__("job-001", "raw/job-001/test.pdf")
        mock_record = patches["app.ingestion.tasks.record_event"]

        completed_calls = [c for c in mock_record.call_args_list if c[0][2] == "TASK_COMPLETED"]
        assert len(completed_calls) == 1

        tc = completed_calls[0]
        assert tc[1]["detail"]["filename"] == "test.pdf"
        assert tc[1]["detail"]["page_count"] == 3
        assert tc[1]["detail"]["chunk_count"] == 2
        assert tc[1]["detail"]["entity_count"] == 1
        assert "duration_ms" in tc[1]
        assert isinstance(tc[1]["duration_ms"], int)
    finally:
        _stop_patches(active)


def test_process_document_emits_task_failed_on_timeout():
    """SoftTimeLimitExceeded emits TASK_FAILED with error=timeout."""
    mock_engine = MagicMock()
    patches = _base_process_doc_patches(mock_engine)
    patches["app.ingestion.tasks._mark_job_failed_with_category"] = MagicMock()
    patches["app.ingestion.tasks._stage_parse"] = MagicMock(side_effect=SoftTimeLimitExceeded())
    active = _apply_patches(patches)

    try:
        result = process_document.__wrapped__("job-001", "raw/job-001/test.pdf")
        assert result["status"] == "failed"

        mock_record = patches["app.ingestion.tasks.record_event"]
        failed_calls = [c for c in mock_record.call_args_list if c[0][2] == "TASK_FAILED"]
        assert len(failed_calls) == 1
        assert failed_calls[0][1]["detail"]["error"] == "timeout"
        assert failed_calls[0][1]["detail"]["stage"] == "parse"
    finally:
        _stop_patches(active)


def test_process_document_emits_task_retried():
    """Retryable error emits TASK_RETRIED with retry count."""
    mock_engine = MagicMock()
    patches = _base_process_doc_patches(mock_engine)
    patches["app.ingestion.tasks._mark_job_failed_with_category"] = MagicMock()
    patches["app.ingestion.tasks._classify_error"] = MagicMock(return_value="UNKNOWN")
    patches["app.ingestion.tasks._stage_parse"] = MagicMock(side_effect=RuntimeError("transient"))
    active = _apply_patches(patches)

    # In default context: self.request.retries=0, self.max_retries=3 → retry branch taken.
    # Mock self.retry to raise a sentinel so we can catch it.
    retry_exc = Exception("retry sentinel")
    task_obj = process_document._get_current_object()
    try:
        with patch.object(task_obj, "retry", side_effect=retry_exc):
            with pytest.raises(Exception, match="retry sentinel"):
                process_document.__wrapped__("job-001", "raw/job-001/test.pdf")

        mock_record = patches["app.ingestion.tasks.record_event"]
        retried_calls = [c for c in mock_record.call_args_list if c[0][2] == "TASK_RETRIED"]
        assert len(retried_calls) == 1
        assert retried_calls[0][1]["detail"]["retry"] == 1
        assert retried_calls[0][1]["detail"]["stage"] == "parse"
    finally:
        _stop_patches(active)


def test_process_document_emits_task_failed_final():
    """When retries exhausted, emits TASK_FAILED (not TASK_RETRIED)."""
    mock_engine = MagicMock()
    patches = _base_process_doc_patches(mock_engine)
    patches["app.ingestion.tasks._mark_job_failed_with_category"] = MagicMock()
    patches["app.ingestion.tasks._classify_error"] = MagicMock(return_value="UNKNOWN")
    patches["app.ingestion.tasks._stage_parse"] = MagicMock(side_effect=RuntimeError("fatal"))
    active = _apply_patches(patches)

    # Set max_retries=0 so retries are exhausted immediately (request.retries=0 >= max_retries=0)
    task_obj = process_document._get_current_object()
    try:
        with patch.object(task_obj, "max_retries", 0):
            with pytest.raises(RuntimeError, match="fatal"):
                process_document.__wrapped__("job-001", "raw/job-001/test.pdf")

        mock_record = patches["app.ingestion.tasks.record_event"]
        failed_calls = [c for c in mock_record.call_args_list if c[0][2] == "TASK_FAILED"]
        retried_calls = [c for c in mock_record.call_args_list if c[0][2] == "TASK_RETRIED"]
        assert len(failed_calls) == 1
        assert len(retried_calls) == 0
        assert failed_calls[0][1]["detail"]["error"] == "fatal"
    finally:
        _stop_patches(active)


# ---------------------------------------------------------------------------
# process_zip events
# ---------------------------------------------------------------------------


def test_process_zip_emits_events():
    """process_zip emits TASK_RECEIVED + TASK_COMPLETED with child_jobs count."""
    import io
    import zipfile

    mock_engine = MagicMock()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w"):
        pass

    patches = {
        "app.config.Settings": MagicMock(return_value=_make_mock_settings()),
        "app.ingestion.tasks._get_sync_engine": MagicMock(return_value=mock_engine),
        "app.feature_flags.service.load_overrides_sync_safe": MagicMock(),
        "app.ingestion.tasks._get_job_matter_id": MagicMock(return_value="matter-1"),
        "app.ingestion.tasks._update_stage": MagicMock(),
        "app.ingestion.tasks._download_from_minio": MagicMock(return_value=buf.getvalue()),
        "app.ingestion.tasks.record_event": MagicMock(),
    }
    active = _apply_patches(patches)

    try:
        result = process_zip.__wrapped__("job-zip", "raw/job-zip/test.zip")
        assert result["status"] == "complete"

        mock_record = patches["app.ingestion.tasks.record_event"]
        event_types = [c[0][2] for c in mock_record.call_args_list]

        assert event_types[0] == "TASK_RECEIVED"
        assert event_types[-1] == "TASK_COMPLETED"
    finally:
        _stop_patches(active)


# ---------------------------------------------------------------------------
# import_text_document events
# ---------------------------------------------------------------------------


def test_import_text_emits_events():
    """import_text_document emits TASK_RECEIVED + TASK_COMPLETED."""
    mock_engine = MagicMock()

    patches = {
        "app.config.Settings": MagicMock(return_value=_make_mock_settings()),
        "app.ingestion.tasks._get_sync_engine": MagicMock(return_value=mock_engine),
        "app.feature_flags.service.load_overrides_sync_safe": MagicMock(),
        "app.ingestion.tasks._store_celery_task_id": MagicMock(),
        "app.ingestion.tasks._upload_to_minio": MagicMock(),
        "app.ingestion.tasks._create_document_record_early": MagicMock(return_value="doc-001"),
        "app.ingestion.tasks._finalize_document_record": MagicMock(),
        "app.ingestion.tasks._update_stage": MagicMock(),
        "app.ingestion.tasks.record_event": MagicMock(),
        "app.ingestion.bulk_import.check_resume": MagicMock(return_value=False),
    }
    active = _apply_patches(patches)

    from app.ingestion.chunker import TextChunker

    fake_chunks = [_FakeChunk(chunk_index=0), _FakeChunk(chunk_index=1)]

    with (
        patch.object(TextChunker, "chunk", return_value=fake_chunks),
        patch("app.ingestion.tasks._embed_chunks", return_value=[[0.1] * 1024, [0.2] * 1024]),
        patch("asyncio.run", side_effect=lambda coro: [[0.1] * 1024, [0.2] * 1024]),
        patch("app.entities.extractor.EntityExtractor") as mock_extractor_cls,
        patch("qdrant_client.QdrantClient") as mock_qdrant_cls,
    ):
        mock_extractor_cls.return_value.extract.return_value = []
        mock_qdrant_cls.return_value = MagicMock()

        try:
            result = import_text_document.__wrapped__(
                "job-import",
                "Hello world test document text",
                "test.txt",
                "abc123hash",
                matter_id="matter-1",
            )
            assert result["status"] == "complete"

            mock_record = patches["app.ingestion.tasks.record_event"]
            event_types = [c[0][2] for c in mock_record.call_args_list]

            assert event_types[0] == "TASK_RECEIVED"
            assert event_types[-1] == "TASK_COMPLETED"

            tc = [c for c in mock_record.call_args_list if c[0][2] == "TASK_COMPLETED"][0]
            assert tc[1]["detail"]["filename"] == "test.txt"
        finally:
            _stop_patches(active)


def test_import_text_emits_dedup_completed():
    """Dedup-skipped import emits TASK_COMPLETED with skipped=True."""
    mock_engine = MagicMock()

    patches = {
        "app.config.Settings": MagicMock(return_value=_make_mock_settings()),
        "app.ingestion.tasks._get_sync_engine": MagicMock(return_value=mock_engine),
        "app.feature_flags.service.load_overrides_sync_safe": MagicMock(),
        "app.ingestion.tasks._store_celery_task_id": MagicMock(),
        "app.ingestion.tasks._update_stage": MagicMock(),
        "app.ingestion.tasks.record_event": MagicMock(),
        "app.ingestion.bulk_import.check_resume": MagicMock(return_value=True),
    }
    active = _apply_patches(patches)

    try:
        result = import_text_document.__wrapped__(
            "job-dedup",
            "Duplicate text",
            "dup.txt",
            "existing_hash",
            matter_id="matter-1",
        )
        assert result["skipped"] is True

        mock_record = patches["app.ingestion.tasks.record_event"]
        event_types = [c[0][2] for c in mock_record.call_args_list]

        assert "TASK_RECEIVED" in event_types
        assert "TASK_COMPLETED" in event_types

        tc = [c for c in mock_record.call_args_list if c[0][2] == "TASK_COMPLETED"][0]
        assert tc[1]["detail"]["skipped"] is True
    finally:
        _stop_patches(active)
