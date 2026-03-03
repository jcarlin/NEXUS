"""Bulk import data model, adapter protocol, and helpers.

Defines the ``ImportDocument`` schema for pre-parsed documents and the
``DatasetAdapter`` protocol that all import adapters must satisfy.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class ImportDocument(BaseModel):
    """A single document ready for import (text already extracted)."""

    source_id: str = ""
    filename: str
    text: str
    content_hash: str = ""
    source: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    page_count: int = 1
    doc_type: str = "document"
    email_headers: dict[str, str] | None = None


# ---------------------------------------------------------------------------
# Adapter protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class DatasetAdapter(Protocol):
    """Interface for dataset import adapters.

    Mirrors the ``EmbeddingProvider`` pattern in ``app/common/embedder.py``.
    """

    @property
    def name(self) -> str:
        """Short identifier for this adapter (e.g. ``"directory"``)."""
        ...

    def iter_documents(self, *, limit: int | None = None) -> Iterator[ImportDocument]:
        """Yield ``ImportDocument`` instances from the data source.

        If *limit* is set, yield at most *limit* documents.
        """
        ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def compute_content_hash(text: str) -> str:
    """Return a truncated SHA-256 hex digest (16 chars) of *text*."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Cost estimation constants
# ---------------------------------------------------------------------------

# Average chunks per document (empirical from legal corpus)
AVG_CHUNKS_PER_DOC = 4.5

# OpenAI text-embedding-3-large pricing: $0.13 per 1M tokens
EMBEDDING_COST_PER_M_TOKENS = 0.13

# Average tokens per chunk
AVG_TOKENS_PER_CHUNK = 350


# ---------------------------------------------------------------------------
# Sync DB helpers for bulk import orchestration
# ---------------------------------------------------------------------------


def _get_sync_engine():
    """Create a sync engine from settings."""
    from sqlalchemy import create_engine

    from app.config import Settings

    settings = Settings()
    return create_engine(settings.postgres_url_sync, pool_pre_ping=True)


def check_resume(engine, content_hash: str, matter_id: str) -> bool:
    """Return True if a document with this content hash already exists."""
    from sqlalchemy import text

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT id FROM documents WHERE content_hash = :hash" " AND matter_id = :matter_id LIMIT 1"),
            {"hash": content_hash, "matter_id": matter_id},
        )
        return result.first() is not None


def create_bulk_import_job(
    engine,
    matter_id: str,
    adapter_type: str,
    source_path: str,
    total: int,
) -> str:
    """Insert a bulk_import_jobs row (sync) and return its UUID string."""
    import json
    import uuid

    from sqlalchemy import text

    job_id = str(uuid.uuid4())
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO bulk_import_jobs
                    (id, matter_id, adapter_type, source_path, status,
                     total_documents, processed_documents, failed_documents,
                     skipped_documents, metadata_, created_at, updated_at)
                VALUES
                    (:id, :matter_id, :adapter_type, :source_path, 'processing',
                     :total, 0, 0, 0, :metadata_, now(), now())
                """
            ),
            {
                "id": job_id,
                "matter_id": matter_id,
                "adapter_type": adapter_type,
                "source_path": source_path,
                "total": total,
                "metadata_": json.dumps({}),
            },
        )
        conn.commit()
    return job_id


def create_job_row(
    engine,
    job_id: str,
    filename: str,
    matter_id: str,
    dataset_id: str | None = None,
) -> None:
    """Create a job row in the jobs table (sync)."""
    import json

    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO jobs (id, filename, status, stage, progress, error,
                                  parent_job_id, matter_id, dataset_id,
                                  metadata_, created_at, updated_at)
                VALUES (:id, :filename, 'pending', 'uploading', '{}', NULL,
                        NULL, :matter_id, :dataset_id, :metadata_, now(), now())
                """
            ),
            {
                "id": job_id,
                "filename": filename,
                "matter_id": matter_id,
                "dataset_id": dataset_id,
                "metadata_": json.dumps({}),
            },
        )
        conn.commit()


def complete_bulk_job(
    engine,
    bulk_job_id: str,
    status: str = "complete",
    error: str | None = None,
) -> None:
    """Mark a bulk import job as complete or failed."""
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(
            text(
                """
                UPDATE bulk_import_jobs
                SET status = :status,
                    error = :error,
                    completed_at = now(),
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {"id": bulk_job_id, "status": status, "error": error},
        )
        conn.commit()


def increment_skipped(engine, bulk_job_id: str) -> None:
    """Atomically increment the skipped counter on a bulk import job."""
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(
            text(
                """
                UPDATE bulk_import_jobs
                SET skipped_documents = skipped_documents + 1,
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {"id": bulk_job_id},
        )
        conn.commit()


def dispatch_post_ingestion_hooks(matter_id: str) -> list[str]:
    """Dispatch post-ingestion Celery tasks by name string.

    Uses ``celery_app.send_task()`` to dispatch by name, so tasks that
    don't exist yet are logged and skipped rather than causing import errors.

    Returns list of successfully dispatched task names.
    """
    import structlog

    from workers.celery_app import celery_app

    logger = structlog.get_logger(__name__)
    dispatched: list[str] = []
    hooks = [
        ("entities.resolve_entities", {}),
        ("ingestion.detect_inclusive_emails", {"matter_id": matter_id}),
        ("agents.hot_document_scan", {"matter_id": matter_id}),
        ("agents.entity_resolution_agent", {"matter_id": matter_id}),
    ]

    for task_name, kwargs in hooks:
        try:
            celery_app.send_task(task_name, kwargs=kwargs)
            dispatched.append(task_name)
            logger.info("post_ingestion.dispatched", task=task_name)
        except Exception:
            logger.warning(
                "post_ingestion.skipped",
                task=task_name,
                exc_info=True,
            )

    return dispatched


def build_adapter(adapter_type: str, source_config: dict) -> DatasetAdapter:
    """Build and return a DatasetAdapter from registry + config.

    Raises ``ValueError`` for invalid adapter types or missing config.
    """
    from pathlib import Path

    from app.ingestion.adapters import ADAPTER_REGISTRY

    if adapter_type not in ADAPTER_REGISTRY:
        raise ValueError(f"Unknown adapter type: '{adapter_type}'. " f"Valid: {list(ADAPTER_REGISTRY.keys())}")

    adapter_cls = ADAPTER_REGISTRY[adapter_type]

    if adapter_type == "directory":
        data_dir = source_config.get("data_dir")
        if not data_dir:
            raise ValueError("'data_dir' is required for the directory adapter")
        path = Path(data_dir)
        if not path.exists():
            raise ValueError(f"Directory '{data_dir}' does not exist")
        return adapter_cls(data_dir=path)  # type: ignore[call-arg]
    elif adapter_type == "huggingface_csv":
        file_path = source_config.get("file_path")
        if not file_path:
            raise ValueError("'file_path' is required for the huggingface_csv adapter")
        path = Path(file_path)
        if not path.exists():
            raise ValueError(f"File '{file_path}' does not exist")
        return adapter_cls(file_path=path)  # type: ignore[call-arg]
    elif adapter_type in ("edrm_xml", "concordance_dat"):
        file_path = source_config.get("file_path")
        if not file_path:
            raise ValueError(f"'file_path' is required for the {adapter_type} adapter")
        path = Path(file_path)
        if not path.exists():
            raise ValueError(f"File '{file_path}' does not exist")
        content_dir = source_config.get("content_dir")
        content_path = Path(content_dir) if content_dir else None
        if adapter_type == "edrm_xml":
            return adapter_cls(  # type: ignore[call-arg]
                xml_path=path,
                content_dir=content_path,
            )
        else:
            return adapter_cls(  # type: ignore[call-arg]
                dat_path=path,
                content_dir=content_path,
            )
    else:
        raise ValueError(f"Unknown adapter type: '{adapter_type}'")
