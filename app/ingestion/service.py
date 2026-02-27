"""Ingestion service layer — database operations for the jobs table.

All queries use raw ``sqlalchemy.text()`` against the tables created by
migration 001.  No ORM models are involved.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


def _row_to_dict(row) -> dict:
    """Convert a SQLAlchemy Row (from text query) into a plain dict.

    UUID and datetime values are converted to JSON-safe types so the dict
    can be passed directly into Pydantic response models.
    """
    raw = dict(row._mapping)
    for key, value in raw.items():
        if isinstance(value, UUID):
            raw[key] = value
        if isinstance(value, datetime):
            raw[key] = value
    return raw


class IngestionService:
    """Static-style methods for job CRUD.  All methods are async and
    expect a caller-managed ``AsyncSession``."""

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------

    @staticmethod
    async def create_job(
        db: AsyncSession,
        filename: str,
        minio_path: str,
        parent_job_id: UUID | None = None,
        job_id: UUID | None = None,
    ) -> dict:
        """Insert a new job row and return it as a dict.

        If *job_id* is provided it will be used as the primary key;
        otherwise a new UUID is generated.  This allows the caller to
        pre-generate an id that matches the MinIO object prefix.

        The caller's session is expected to commit after this call returns
        (e.g. via the ``get_db`` dependency's auto-commit wrapper).
        """
        if job_id is None:
            job_id = uuid4()
        now = datetime.now(UTC)

        await db.execute(
            text(
                """
                INSERT INTO jobs (id, filename, status, stage, progress, error,
                                  parent_job_id, metadata_, created_at, updated_at)
                VALUES (:id, :filename, :status, :stage, :progress, :error,
                        :parent_job_id, :metadata_, :created_at, :updated_at)
                """
            ),
            {
                "id": job_id,
                "filename": filename,
                "status": "pending",
                "stage": "uploading",
                "progress": "{}",
                "error": None,
                "parent_job_id": parent_job_id,
                "metadata_": f'{{"minio_path": "{minio_path}"}}',
                "created_at": now,
                "updated_at": now,
            },
        )
        await db.flush()

        logger.info("job.created", job_id=str(job_id), filename=filename)

        return {
            "id": job_id,
            "filename": filename,
            "status": "pending",
            "stage": "uploading",
            "progress": {},
            "error": None,
            "parent_job_id": parent_job_id,
            "metadata_": {"minio_path": minio_path},
            "created_at": now,
            "updated_at": now,
        }

    # ------------------------------------------------------------------
    # READ (single)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_job(db: AsyncSession, job_id: UUID) -> dict | None:
        """Fetch a single job by id.  Returns ``None`` if not found."""
        result = await db.execute(
            text(
                """
                SELECT id, filename, status, stage, progress, error,
                       parent_job_id, metadata_, created_at, updated_at
                FROM jobs
                WHERE id = :job_id
                """
            ),
            {"job_id": job_id},
        )
        row = result.first()
        if row is None:
            return None
        return _row_to_dict(row)

    # ------------------------------------------------------------------
    # READ (list + count)
    # ------------------------------------------------------------------

    @staticmethod
    async def list_jobs(
        db: AsyncSession,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        """Return ``(items, total_count)`` with offset/limit pagination.

        Jobs are ordered by ``created_at DESC`` (newest first).
        """
        # Total count
        count_result = await db.execute(text("SELECT count(*) FROM jobs"))
        total = count_result.scalar_one()

        # Paginated rows
        result = await db.execute(
            text(
                """
                SELECT id, filename, status, stage, progress, error,
                       parent_job_id, metadata_, created_at, updated_at
                FROM jobs
                ORDER BY created_at DESC
                OFFSET :offset
                LIMIT :limit
                """
            ),
            {"offset": offset, "limit": limit},
        )
        rows = result.all()
        items = [_row_to_dict(r) for r in rows]

        return items, total

    # ------------------------------------------------------------------
    # UPDATE (stage transition)
    # ------------------------------------------------------------------

    @staticmethod
    async def update_job_stage(
        db: AsyncSession,
        job_id: UUID,
        stage: str,
        status: str = "uploading",
        progress: dict | None = None,
        error: str | None = None,
    ) -> None:
        """Update a job's stage, status, progress, and error fields."""
        import json

        progress_json = json.dumps(progress) if progress is not None else None

        if progress_json is not None:
            await db.execute(
                text(
                    """
                    UPDATE jobs
                    SET stage = :stage,
                        status = :status,
                        progress = :progress::jsonb,
                        error = :error,
                        updated_at = now()
                    WHERE id = :job_id
                    """
                ),
                {
                    "job_id": job_id,
                    "stage": stage,
                    "status": status,
                    "progress": progress_json,
                    "error": error,
                },
            )
        else:
            await db.execute(
                text(
                    """
                    UPDATE jobs
                    SET stage = :stage,
                        status = :status,
                        error = :error,
                        updated_at = now()
                    WHERE id = :job_id
                    """
                ),
                {
                    "job_id": job_id,
                    "stage": stage,
                    "status": status,
                    "error": error,
                },
            )

        logger.info(
            "job.stage_updated",
            job_id=str(job_id),
            stage=stage,
            status=status,
        )

    # ------------------------------------------------------------------
    # CANCEL
    # ------------------------------------------------------------------

    @staticmethod
    async def cancel_job(db: AsyncSession, job_id: UUID) -> bool:
        """Mark a job as failed/cancelled.

        Returns ``True`` if a row was updated, ``False`` if the job was
        not found (or already in a terminal state).
        """
        result = await db.execute(
            text(
                """
                UPDATE jobs
                SET status = 'failed',
                    error = 'Cancelled by user',
                    updated_at = now()
                WHERE id = :job_id
                  AND status NOT IN ('complete', 'failed')
                """
            ),
            {"job_id": job_id},
        )
        updated = result.rowcount > 0

        if updated:
            logger.info("job.cancelled", job_id=str(job_id))
        else:
            logger.warning("job.cancel_noop", job_id=str(job_id))

        return updated
