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

from app.common.db_utils import row_to_dict
from app.ingestion.schemas import DryRunRequest, DryRunResponse

logger = structlog.get_logger(__name__)


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
        matter_id: UUID | None = None,
        dataset_id: UUID | None = None,
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
                                  parent_job_id, matter_id, dataset_id, metadata_, created_at, updated_at)
                VALUES (:id, :filename, :status, :stage, :progress, :error,
                        :parent_job_id, :matter_id, :dataset_id, :metadata_, :created_at, :updated_at)
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
                "matter_id": matter_id,
                "dataset_id": dataset_id,
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
            "matter_id": matter_id,
            "metadata_": {"minio_path": minio_path},
            "created_at": now,
            "updated_at": now,
        }

    # ------------------------------------------------------------------
    # READ (single)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_job(
        db: AsyncSession,
        job_id: UUID,
        matter_id: UUID | None = None,
    ) -> dict | None:
        """Fetch a single job by id.  Returns ``None`` if not found."""
        where = "WHERE id = :job_id"
        params: dict = {"job_id": job_id}
        if matter_id is not None:
            where += " AND matter_id = :matter_id"
            params["matter_id"] = matter_id

        result = await db.execute(
            text(
                f"""
                SELECT id, filename, status, stage, progress, error,
                       parent_job_id, matter_id, metadata_, created_at, updated_at
                FROM jobs
                {where}
                """
            ),
            params,
        )
        row = result.first()
        if row is None:
            return None
        return row_to_dict(row)

    # ------------------------------------------------------------------
    # READ (list + count)
    # ------------------------------------------------------------------

    @staticmethod
    async def list_jobs(
        db: AsyncSession,
        offset: int = 0,
        limit: int = 50,
        matter_id: UUID | None = None,
        status: str | None = None,
    ) -> tuple[list[dict], int]:
        """Return ``(items, total_count)`` with offset/limit pagination.

        Jobs are ordered by ``created_at DESC`` (newest first).
        """
        clauses: list[str] = []
        params: dict = {"offset": offset, "limit": limit}
        if matter_id is not None:
            clauses.append("matter_id = :matter_id")
            params["matter_id"] = matter_id
        if status is not None:
            clauses.append("status = :status")
            params["status"] = status
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        # Total count
        count_result = await db.execute(text(f"SELECT count(*) FROM jobs {where}"), params)
        total = count_result.scalar_one()

        # Paginated rows
        result = await db.execute(
            text(
                f"""
                SELECT id, filename, status, stage, progress, error,
                       parent_job_id, matter_id, metadata_, created_at, updated_at
                FROM jobs
                {where}
                ORDER BY created_at DESC
                OFFSET :offset
                LIMIT :limit
                """
            ),
            params,
        )
        rows = result.all()
        items = [row_to_dict(r) for r in rows]

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
                        progress = CAST(:progress AS jsonb),
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

    # ------------------------------------------------------------------
    # BULK IMPORT JOBS
    # ------------------------------------------------------------------

    @staticmethod
    async def create_bulk_import_job(
        db: AsyncSession,
        matter_id: UUID,
        adapter_type: str,
        source_path: str,
        total_documents: int,
    ) -> dict:
        """Insert a ``bulk_import_jobs`` row and return it as a dict."""
        import json

        job_id = uuid4()
        now = datetime.now(UTC)

        await db.execute(
            text(
                """
                INSERT INTO bulk_import_jobs
                    (id, matter_id, adapter_type, source_path, status,
                     total_documents, processed_documents, failed_documents,
                     skipped_documents, metadata_, created_at, updated_at)
                VALUES
                    (:id, :matter_id, :adapter_type, :source_path, 'processing',
                     :total_documents, 0, 0, 0, :metadata_, :created_at, :updated_at)
                """
            ),
            {
                "id": job_id,
                "matter_id": matter_id,
                "adapter_type": adapter_type,
                "source_path": source_path,
                "total_documents": total_documents,
                "metadata_": json.dumps({}),
                "created_at": now,
                "updated_at": now,
            },
        )
        await db.flush()

        logger.info(
            "bulk_import.created",
            import_id=str(job_id),
            adapter=adapter_type,
            total=total_documents,
        )

        return {
            "id": job_id,
            "matter_id": matter_id,
            "adapter_type": adapter_type,
            "source_path": source_path,
            "status": "processing",
            "total_documents": total_documents,
            "processed_documents": 0,
            "failed_documents": 0,
            "skipped_documents": 0,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }

    @staticmethod
    async def get_bulk_import_job(
        db: AsyncSession,
        import_id: UUID,
        matter_id: UUID,
    ) -> dict | None:
        """Fetch a single bulk import job by id (matter-scoped)."""
        result = await db.execute(
            text(
                """
                SELECT id, matter_id, adapter_type, source_path, status,
                       total_documents, processed_documents, failed_documents,
                       skipped_documents, error, created_at, updated_at, completed_at
                FROM bulk_import_jobs
                WHERE id = :import_id AND matter_id = :matter_id
                """
            ),
            {"import_id": import_id, "matter_id": matter_id},
        )
        row = result.first()
        if row is None:
            return None
        return row_to_dict(row)

    # ------------------------------------------------------------------
    # LIST BULK IMPORTS (matter-scoped)
    # ------------------------------------------------------------------

    @staticmethod
    async def list_bulk_imports(
        db: AsyncSession,
        matter_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        """Return ``(items, total_count)`` for bulk import jobs (matter-scoped)."""
        params: dict = {"matter_id": matter_id, "offset": offset, "limit": limit}

        count_result = await db.execute(
            text("SELECT count(*) FROM bulk_import_jobs WHERE matter_id = :matter_id"),
            params,
        )
        total = count_result.scalar_one()

        result = await db.execute(
            text(
                """
                SELECT id, matter_id, adapter_type, source_path, status,
                       total_documents, processed_documents, failed_documents,
                       skipped_documents, error, created_at, updated_at, completed_at
                FROM bulk_import_jobs
                WHERE matter_id = :matter_id
                ORDER BY created_at DESC
                OFFSET :offset
                LIMIT :limit
                """
            ),
            params,
        )
        rows = result.all()
        items = [row_to_dict(r) for r in rows]

        return items, total

    # ------------------------------------------------------------------
    # DRY-RUN ESTIMATE
    # ------------------------------------------------------------------

    @staticmethod
    def estimate_import(request: DryRunRequest) -> DryRunResponse:
        """Estimate import results without actually processing."""
        file_count = request.file_count or 0
        total_bytes = request.total_size_bytes or 0
        est_pages = max(file_count * 5, total_bytes // (50 * 1024))  # ~50KB per page
        est_chunks = est_pages * 3  # ~3 chunks per page
        est_minutes = file_count * 0.5  # ~30s per doc
        est_storage = total_bytes / (1024 * 1024) * 1.2  # 20% overhead

        warnings: list[str] = []
        if file_count > 1000:
            warnings.append("Large import: consider batching in groups of 500")
        if total_bytes > 10 * 1024**3:
            warnings.append("Import exceeds 10 GB: ensure sufficient storage")

        return DryRunResponse(
            estimated_documents=file_count,
            estimated_chunks=est_chunks,
            estimated_duration_minutes=round(est_minutes, 1),
            estimated_storage_mb=round(est_storage, 1),
            warnings=warnings,
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
        updated: bool = (result.rowcount or 0) > 0  # type: ignore[attr-defined]

        if updated:
            logger.info("job.cancelled", job_id=str(job_id))
        else:
            logger.warning("job.cancel_noop", job_id=str(job_id))

        return updated
