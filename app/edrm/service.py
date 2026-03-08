"""EDRM service layer — database operations for EDRM interop.

Queries for email threads, duplicate clusters, version groups,
and EDRM import log management.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


def _row_to_dict(row) -> dict:
    """Convert a SQLAlchemy Row to a plain dict."""
    return dict(row._mapping)


class EDRMService:
    """Static methods for EDRM-related queries."""

    # ------------------------------------------------------------------
    # THREADS
    # ------------------------------------------------------------------

    @staticmethod
    async def list_threads(
        db: AsyncSession,
        matter_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        """List email threads for a matter with message counts."""
        count_result = await db.execute(
            text(
                "SELECT count(DISTINCT thread_id) FROM documents WHERE thread_id IS NOT NULL AND matter_id = :matter_id"
            ),
            {"matter_id": matter_id},
        )
        total = count_result.scalar_one()

        result = await db.execute(
            text(
                """
                SELECT thread_id,
                       count(*) as message_count,
                       min(metadata_->>'subject') as subject,
                       min(created_at) as earliest,
                       max(created_at) as latest
                FROM documents
                WHERE thread_id IS NOT NULL AND matter_id = :matter_id
                GROUP BY thread_id
                ORDER BY latest DESC
                OFFSET :offset LIMIT :limit
                """
            ),
            {"matter_id": matter_id, "offset": offset, "limit": limit},
        )
        items = [_row_to_dict(r) for r in result.all()]
        return items, total

    # ------------------------------------------------------------------
    # DUPLICATE CLUSTERS
    # ------------------------------------------------------------------

    @staticmethod
    async def list_duplicate_clusters(
        db: AsyncSession,
        matter_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        """List duplicate clusters for a matter."""
        count_result = await db.execute(
            text(
                "SELECT count(DISTINCT duplicate_cluster_id) FROM documents "
                "WHERE duplicate_cluster_id IS NOT NULL AND matter_id = :matter_id"
            ),
            {"matter_id": matter_id},
        )
        total = count_result.scalar_one()

        result = await db.execute(
            text(
                """
                SELECT duplicate_cluster_id as cluster_id,
                       count(*) as document_count,
                       avg(duplicate_score) as avg_score
                FROM documents
                WHERE duplicate_cluster_id IS NOT NULL AND matter_id = :matter_id
                GROUP BY duplicate_cluster_id
                ORDER BY document_count DESC
                OFFSET :offset LIMIT :limit
                """
            ),
            {"matter_id": matter_id, "offset": offset, "limit": limit},
        )
        items = [_row_to_dict(r) for r in result.all()]
        return items, total

    # ------------------------------------------------------------------
    # IMPORT LOG
    # ------------------------------------------------------------------

    @staticmethod
    async def create_import_log(
        db: AsyncSession,
        matter_id: UUID,
        filename: str,
        fmt: str,
        record_count: int,
        status: str = "complete",
    ) -> dict:
        """Create an EDRM import log entry."""
        result = await db.execute(
            text(
                """
                INSERT INTO edrm_import_log (matter_id, filename, format, record_count, status, completed_at)
                VALUES (:matter_id, :filename, :format, :record_count, :status, now())
                RETURNING id, matter_id, filename, format, record_count, status, created_at, completed_at
                """
            ),
            {
                "matter_id": matter_id,
                "filename": filename,
                "format": fmt,
                "record_count": record_count,
                "status": status,
            },
        )
        row = result.first()
        return _row_to_dict(row)

    @staticmethod
    async def list_import_logs(
        db: AsyncSession,
        matter_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        """List EDRM import log entries for a matter."""
        count_result = await db.execute(
            text("SELECT count(*) FROM edrm_import_log WHERE matter_id = :matter_id"),
            {"matter_id": matter_id},
        )
        total = count_result.scalar_one()

        result = await db.execute(
            text(
                """
                SELECT id, matter_id, filename, format, record_count, status,
                       error, created_at, completed_at
                FROM edrm_import_log
                WHERE matter_id = :matter_id
                ORDER BY created_at DESC
                OFFSET :offset LIMIT :limit
                """
            ),
            {"matter_id": matter_id, "offset": offset, "limit": limit},
        )
        items = [_row_to_dict(r) for r in result.all()]
        return items, total
