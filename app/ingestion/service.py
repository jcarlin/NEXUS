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
        filename: str | None = None,
        minio_path: str = "",
        parent_job_id: UUID | None = None,
        job_id: UUID | None = None,
        matter_id: UUID | None = None,
        dataset_id: UUID | None = None,
        task_type: str = "ingestion",
        label: str | None = None,
    ) -> dict:
        """Insert a new job row and return it as a dict.

        If *job_id* is provided it will be used as the primary key;
        otherwise a new UUID is generated.  This allows the caller to
        pre-generate an id that matches the MinIO object prefix.

        For non-ingestion tasks, *filename* may be ``None`` and *label*
        provides the display name shown in the UI.

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
                                  parent_job_id, matter_id, dataset_id, metadata_,
                                  task_type, label, created_at, updated_at)
                VALUES (:id, :filename, :status, :stage, :progress, :error,
                        :parent_job_id, :matter_id, :dataset_id, :metadata_,
                        :task_type, :label, :created_at, :updated_at)
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
                "metadata_": f'{{"minio_path": "{minio_path}"}}' if minio_path else "{}",
                "task_type": task_type,
                "label": label,
                "created_at": now,
                "updated_at": now,
            },
        )
        await db.flush()

        logger.info("job.created", job_id=str(job_id), filename=filename, task_type=task_type)

        return {
            "id": job_id,
            "filename": filename,
            "status": "pending",
            "stage": "uploading",
            "progress": {},
            "error": None,
            "parent_job_id": parent_job_id,
            "matter_id": matter_id,
            "task_type": task_type,
            "label": label,
            "metadata_": {"minio_path": minio_path} if minio_path else {},
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
                       parent_job_id, matter_id, metadata_,
                       task_type, label, created_at, updated_at
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
        task_type: str | None = None,
    ) -> tuple[list[dict], int]:
        """Return ``(items, total_count)`` with offset/limit pagination.

        Jobs are ordered by ``created_at DESC`` (newest first).
        """
        clauses: list[str] = []
        params: dict = {"offset": offset, "limit": limit}
        if matter_id is not None:
            clauses.append("j.matter_id = :matter_id")
            params["matter_id"] = matter_id
        if status is not None:
            statuses = [s.strip() for s in status.split(",") if s.strip()]
            if len(statuses) == 1:
                clauses.append("j.status = :status")
                params["status"] = statuses[0]
            elif statuses:
                clauses.append("j.status = ANY(:statuses)")
                params["statuses"] = statuses
        if task_type is not None:
            clauses.append("j.task_type = :task_type")
            params["task_type"] = task_type
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        # Total count
        count_result = await db.execute(text(f"SELECT count(*) FROM jobs j {where}"), params)
        total = count_result.scalar_one()

        # Paginated rows
        result = await db.execute(
            text(
                f"""
                SELECT j.id, j.filename, j.status, j.stage, j.progress, j.error,
                       j.parent_job_id, j.matter_id, j.metadata_,
                       j.task_type, j.label, j.created_at, j.updated_at,
                       j.error_category, j.retry_count, j.worker_hostname,
                       j.started_at, j.completed_at,
                       d.file_size_bytes, d.page_count,
                       d.document_type
                FROM jobs j
                LEFT JOIN documents d ON d.job_id = j.id
                {where}
                ORDER BY j.created_at DESC
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
    # LIST JOBS BY BULK IMPORT
    # ------------------------------------------------------------------

    @staticmethod
    async def list_jobs_by_bulk_import(
        db: AsyncSession,
        bulk_import_job_id: UUID,
        matter_id: UUID,
        offset: int = 0,
        limit: int = 50,
        status: str | None = None,
    ) -> tuple[list[dict], int]:
        """Return ``(items, total_count)`` for jobs linked to a bulk import."""
        clauses: list[str] = [
            "j.bulk_import_job_id = :bulk_import_job_id",
            "j.matter_id = :matter_id",
        ]
        params: dict = {
            "bulk_import_job_id": bulk_import_job_id,
            "matter_id": matter_id,
            "offset": offset,
            "limit": limit,
        }
        if status is not None:
            clauses.append("j.status = :status")
            params["status"] = status
        where = "WHERE " + " AND ".join(clauses)

        count_result = await db.execute(text(f"SELECT count(*) FROM jobs j {where}"), params)
        total = count_result.scalar_one()

        result = await db.execute(
            text(
                f"""
                SELECT j.id, j.filename, j.status, j.stage, j.progress, j.error,
                       j.parent_job_id, j.matter_id, j.metadata_,
                       j.task_type, j.label, j.created_at, j.updated_at,
                       j.error_category, j.retry_count, j.worker_hostname,
                       j.started_at, j.completed_at,
                       d.file_size_bytes, d.page_count,
                       d.document_type
                FROM jobs j
                LEFT JOIN documents d ON d.job_id = j.id
                {where}
                ORDER BY CASE j.status
                    WHEN 'processing' THEN 1
                    WHEN 'pending' THEN 2
                    WHEN 'failed' THEN 3
                    WHEN 'complete' THEN 4
                    WHEN 'dismissed' THEN 5
                    ELSE 6
                END, j.created_at DESC
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
                SELECT bi.id, bi.matter_id, bi.adapter_type, bi.source_path, bi.status,
                       bi.total_documents, bi.processed_documents, bi.failed_documents,
                       bi.skipped_documents, bi.error, bi.created_at, bi.updated_at,
                       bi.completed_at,
                       COALESCE(agg.total_size_bytes, 0) AS total_size_bytes,
                       COALESCE(agg.total_pages, 0) AS total_pages
                FROM bulk_import_jobs bi
                LEFT JOIN LATERAL (
                    SELECT SUM(d.file_size_bytes) AS total_size_bytes,
                           SUM(d.page_count) AS total_pages
                    FROM jobs j
                    JOIN documents d ON d.job_id = j.id
                    WHERE j.bulk_import_job_id = bi.id
                ) agg ON true
                WHERE bi.matter_id = :matter_id
                ORDER BY bi.created_at DESC
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
    # RE-INDEX (look up real MinIO paths for existing documents)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_documents_for_reindex(
        db: AsyncSession,
        doc_ids: list[UUID],
        matter_id: UUID,
    ) -> list[dict]:
        """Fetch document metadata needed to re-dispatch ingestion.

        Returns list of dicts with id, filename, minio_path for each
        document that exists and belongs to the given matter.
        """
        placeholders = ", ".join(f":id_{i}" for i in range(len(doc_ids)))
        params: dict = {f"id_{i}": did for i, did in enumerate(doc_ids)}
        params["matter_id"] = matter_id

        result = await db.execute(
            text(f"""
                SELECT id, filename, minio_path
                FROM documents
                WHERE id IN ({placeholders})
                  AND matter_id = :matter_id
            """),
            params,
        )
        return [row_to_dict(r) for r in result.all()]

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

    @staticmethod
    async def get_celery_task_id(db: AsyncSession, job_id: UUID) -> str | None:
        """Read the celery_task_id from a job record for revocation."""
        result = await db.execute(
            text("SELECT celery_task_id FROM jobs WHERE id = :job_id"),
            {"job_id": job_id},
        )
        row = result.first()
        if row is None:
            return None
        return row.celery_task_id

    # ------------------------------------------------------------------
    # RETRY
    # ------------------------------------------------------------------

    @staticmethod
    async def retry_job(db: AsyncSession, job_id: UUID) -> dict | None:
        """Reset a failed job to pending for retry.

        Returns the job dict if successfully reset, None if job not found
        or not in a retryable state.
        """
        result = await db.execute(
            text(
                """
                UPDATE jobs
                SET status = 'pending',
                    stage = 'uploading',
                    error = NULL,
                    celery_task_id = NULL,
                    updated_at = now()
                WHERE id = :job_id
                  AND status = 'failed'
                RETURNING id, filename, metadata_, task_type, matter_id
                """
            ),
            {"job_id": job_id},
        )
        row = result.first()
        if row is None:
            return None
        return row_to_dict(row)

    @staticmethod
    async def retry_all_failed(db: AsyncSession, matter_id: UUID) -> list[dict]:
        """Reset all failed ingestion jobs for a matter to pending.

        Returns list of job dicts that were reset.
        """
        result = await db.execute(
            text(
                """
                UPDATE jobs
                SET status = 'pending',
                    stage = 'uploading',
                    error = NULL,
                    celery_task_id = NULL,
                    updated_at = now()
                WHERE status = 'failed'
                  AND matter_id = :matter_id
                  AND task_type = 'ingestion'
                RETURNING id, filename, metadata_, task_type, matter_id
                """
            ),
            {"matter_id": matter_id},
        )
        rows = result.fetchall()
        logger.info("jobs.retry_all", matter_id=str(matter_id), count=len(rows))
        return [row_to_dict(r) for r in rows]

    @staticmethod
    async def dismiss_job(db: AsyncSession, job_id: UUID) -> bool:
        """Mark a failed job as dismissed (reviewed/archived).

        Returns True if the job was dismissed, False if not found or not failed.
        """
        result = await db.execute(
            text(
                """
                UPDATE jobs
                SET status = 'dismissed',
                    updated_at = now()
                WHERE id = :job_id
                  AND status = 'failed'
                """
            ),
            {"job_id": job_id},
        )
        updated: bool = (result.rowcount or 0) > 0  # type: ignore[attr-defined]
        if updated:
            logger.info("job.dismissed", job_id=str(job_id))
        return updated

    @staticmethod
    async def retry_failed_by_bulk_import(
        db: AsyncSession,
        bulk_import_job_id: UUID,
        matter_id: UUID,
    ) -> list[dict]:
        """Reset failed jobs for a specific bulk import to pending.

        Returns list of job dicts that were reset.
        """
        result = await db.execute(
            text(
                """
                UPDATE jobs
                SET status = 'pending',
                    stage = 'uploading',
                    error = NULL,
                    celery_task_id = NULL,
                    updated_at = now()
                WHERE status = 'failed'
                  AND bulk_import_job_id = :bulk_import_job_id
                  AND matter_id = :matter_id
                RETURNING id, filename, metadata_, task_type, matter_id
                """
            ),
            {"bulk_import_job_id": bulk_import_job_id, "matter_id": matter_id},
        )
        rows = result.fetchall()
        logger.info(
            "jobs.retry_by_bulk_import",
            bulk_import_job_id=str(bulk_import_job_id),
            count=len(rows),
        )
        return [row_to_dict(r) for r in rows]

    @staticmethod
    async def dismiss_failed_by_bulk_import(
        db: AsyncSession,
        bulk_import_job_id: UUID,
        matter_id: UUID,
    ) -> int:
        """Dismiss all failed jobs for a specific bulk import.

        Returns the number of jobs dismissed.
        """
        result = await db.execute(
            text(
                """
                UPDATE jobs
                SET status = 'dismissed',
                    updated_at = now()
                WHERE status = 'failed'
                  AND bulk_import_job_id = :bulk_import_job_id
                  AND matter_id = :matter_id
                """
            ),
            {"bulk_import_job_id": bulk_import_job_id, "matter_id": matter_id},
        )
        count = result.rowcount or 0  # type: ignore[attr-defined]
        logger.info(
            "jobs.dismiss_by_bulk_import",
            bulk_import_job_id=str(bulk_import_job_id),
            count=count,
        )
        return count

    # ------------------------------------------------------------------
    # PIPELINE MONITORING
    # ------------------------------------------------------------------

    @staticmethod
    async def get_pipeline_throughput(db: AsyncSession) -> dict:
        """Compute jobs/min and avg duration over the last hour."""
        result = await db.execute(
            text("""
                SELECT
                    count(*) AS jobs_last_hour,
                    CASE WHEN count(*) > 0 THEN
                        count(*)::float / GREATEST(
                            EXTRACT(EPOCH FROM (now() - min(completed_at))) / 60.0, 1
                        )
                    ELSE 0 END AS jobs_per_minute,
                    coalesce(
                        avg(EXTRACT(EPOCH FROM (completed_at - started_at))), 0
                    ) AS avg_duration_seconds
                FROM jobs
                WHERE status IN ('complete', 'completed')
                  AND completed_at > now() - interval '1 hour'
                  AND started_at IS NOT NULL
            """)
        )
        row = result.one()
        return {
            "jobs_per_minute": round(float(row[1] or 0), 2),
            "jobs_last_hour": int(row[0] or 0),
            "avg_duration_seconds": round(float(row[2] or 0), 1),
        }

    @staticmethod
    async def get_failure_analysis(db: AsyncSession, matter_id: UUID, hours: int = 168) -> dict:
        """Aggregate failure analysis."""
        params: dict = {"matter_id": matter_id, "hours": hours}

        cat_result = await db.execute(
            text("""
                SELECT coalesce(error_category, 'UNKNOWN') AS category, count(*) AS count
                FROM jobs
                WHERE status = 'failed' AND matter_id = :matter_id
                  AND updated_at > now() - make_interval(hours => :hours)
                GROUP BY category ORDER BY count DESC
            """),
            params,
        )
        category_breakdown = [{"category": r[0], "count": r[1]} for r in cat_result.all()]

        rate_result = await db.execute(
            text("""
                SELECT date_trunc('hour', updated_at) AS bucket,
                    count(*) FILTER (WHERE status IN ('complete', 'completed')) AS completed,
                    count(*) FILTER (WHERE status = 'failed') AS failed
                FROM jobs WHERE matter_id = :matter_id
                  AND updated_at > now() - make_interval(hours => :hours)
                  AND status IN ('complete', 'completed', 'failed')
                GROUP BY bucket ORDER BY bucket
            """),
            params,
        )
        failure_rate = [{"timestamp": r[0], "completed": r[1], "failed": r[2]} for r in rate_result.all()]

        top_result = await db.execute(
            text("""
                SELECT left(error, 200) AS error_summary,
                    coalesce(error_category, 'UNKNOWN') AS category,
                    count(*) AS count, max(updated_at) AS last_seen
                FROM jobs WHERE status = 'failed' AND matter_id = :matter_id
                  AND updated_at > now() - make_interval(hours => :hours) AND error IS NOT NULL
                GROUP BY error_summary, category ORDER BY count DESC LIMIT 10
            """),
            params,
        )
        top_errors = [
            {"error_summary": r[0], "category": r[1], "count": r[2], "last_seen": r[3]} for r in top_result.all()
        ]

        stage_result = await db.execute(
            text("""
                SELECT stage, count(*) AS count FROM jobs
                WHERE status = 'failed' AND matter_id = :matter_id
                  AND updated_at > now() - make_interval(hours => :hours)
                GROUP BY stage ORDER BY count DESC
            """),
            params,
        )
        stage_distribution = [{"stage": r[0], "count": r[1]} for r in stage_result.all()]

        totals_result = await db.execute(
            text("""
                SELECT count(*) FILTER (WHERE status = 'failed') AS total_failed,
                    count(*) FILTER (WHERE status IN ('complete', 'completed')) AS total_completed
                FROM jobs WHERE matter_id = :matter_id
                  AND updated_at > now() - make_interval(hours => :hours)
            """),
            params,
        )
        totals = totals_result.one()

        return {
            "category_breakdown": category_breakdown,
            "failure_rate": failure_rate,
            "top_errors": top_errors,
            "stage_distribution": stage_distribution,
            "total_failed": totals[0] or 0,
            "total_completed": totals[1] or 0,
        }

    @staticmethod
    async def list_pipeline_events(
        db: AsyncSession,
        offset: int = 0,
        limit: int = 50,
        job_id: UUID | None = None,
        event_type: str | None = None,
    ) -> tuple[list[dict], int]:
        """Paginated event listing with optional filters."""
        clauses: list[str] = []
        params: dict = {"offset": offset, "limit": limit}
        if job_id is not None:
            clauses.append("pe.job_id = :job_id")
            params["job_id"] = job_id
        if event_type is not None:
            clauses.append("pe.event_type = :event_type")
            params["event_type"] = event_type
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        count_result = await db.execute(text(f"SELECT count(*) FROM pipeline_events pe {where}"), params)
        total = count_result.scalar_one()

        result = await db.execute(
            text(f"""
                SELECT pe.id, pe.job_id, pe.event_type, pe.timestamp,
                       pe.worker, pe.detail, pe.duration_ms, j.filename
                FROM pipeline_events pe
                LEFT JOIN jobs j ON j.id = pe.job_id
                {where}
                ORDER BY pe.timestamp DESC
                OFFSET :offset LIMIT :limit
            """),
            params,
        )
        items = [row_to_dict(r) for r in result.all()]
        return items, total

    @staticmethod
    async def list_events_for_job(db: AsyncSession, job_id: UUID, limit: int = 50) -> list[dict]:
        """All events for a specific job, ordered chronologically."""
        result = await db.execute(
            text("""
                SELECT pe.id, pe.job_id, pe.event_type, pe.timestamp,
                       pe.worker, pe.detail, pe.duration_ms
                FROM pipeline_events pe
                WHERE pe.job_id = :job_id
                ORDER BY pe.timestamp ASC LIMIT :limit
            """),
            {"job_id": job_id, "limit": limit},
        )
        return [row_to_dict(r) for r in result.all()]
