"""Service layer for external task tracking."""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db_utils import row_to_dict

logger = structlog.get_logger(__name__)


class ExternalTaskService:
    """Static methods for external task CRUD."""

    @staticmethod
    async def register(
        db: AsyncSession,
        name: str,
        script_name: str,
        total: int = 0,
        metadata_: dict | None = None,
        matter_id: UUID | None = None,
    ) -> dict:
        """Create a new external task and return it."""
        result = await db.execute(
            text("""
                INSERT INTO external_tasks (name, script_name, total, metadata_, matter_id)
                VALUES (:name, :script_name, :total, CAST(:metadata AS jsonb), :matter_id)
                RETURNING *
            """),
            {
                "name": name,
                "script_name": script_name,
                "total": total,
                "metadata": __import__("json").dumps(metadata_ or {}),
                "matter_id": matter_id,
            },
        )
        return row_to_dict(result.one())

    @staticmethod
    async def update(
        db: AsyncSession,
        task_id: UUID,
        processed: int | None = None,
        failed: int | None = None,
        error: str | None = None,
        status: str | None = None,
        total: int | None = None,
    ) -> dict | None:
        """Update an external task's progress."""
        sets: list[str] = ["updated_at = now()"]
        params: dict = {"task_id": task_id}

        if processed is not None:
            sets.append("processed = :processed")
            params["processed"] = processed
        if failed is not None:
            sets.append("failed = :failed")
            params["failed"] = failed
        if error is not None:
            sets.append("error = :error")
            params["error"] = error
        if total is not None:
            sets.append("total = :total")
            params["total"] = total
        if status is not None:
            sets.append("status = :status")
            params["status"] = status
            if status in ("complete", "failed"):
                sets.append("completed_at = now()")

        result = await db.execute(
            text(f"""
                UPDATE external_tasks
                SET {', '.join(sets)}
                WHERE id = :task_id
                RETURNING *
            """),
            params,
        )
        row = result.one_or_none()
        return row_to_dict(row) if row else None

    @staticmethod
    async def list_tasks(
        db: AsyncSession,
        offset: int = 0,
        limit: int = 50,
        status: str | None = None,
    ) -> tuple[list[dict], int]:
        """Paginated task listing."""
        clauses: list[str] = []
        params: dict = {"offset": offset, "limit": limit}
        if status is not None:
            clauses.append("status = :status")
            params["status"] = status
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        count_result = await db.execute(text(f"SELECT count(*) FROM external_tasks {where}"), params)
        total = count_result.scalar_one()

        result = await db.execute(
            text(f"""
                SELECT * FROM external_tasks
                {where}
                ORDER BY updated_at DESC
                OFFSET :offset LIMIT :limit
            """),
            params,
        )
        items = [row_to_dict(r) for r in result.all()]
        return items, total

    @staticmethod
    async def get_task(db: AsyncSession, task_id: UUID) -> dict | None:
        """Get a single external task."""
        result = await db.execute(
            text("SELECT * FROM external_tasks WHERE id = :task_id"),
            {"task_id": task_id},
        )
        row = result.one_or_none()
        return row_to_dict(row) if row else None

    @staticmethod
    async def expire_stale(db: AsyncSession, stale_minutes: int = 30) -> int:
        """Mark tasks with no update in N minutes as stale."""
        result = await db.execute(
            text("""
                UPDATE external_tasks
                SET status = 'stale', updated_at = now()
                WHERE status = 'running'
                  AND updated_at < now() - make_interval(mins => :minutes)
            """),
            {"minutes": stale_minutes},
        )
        count = result.rowcount or 0  # type: ignore[attr-defined]
        if count > 0:
            logger.info("external_tasks.expired_stale", count=count)
        return count
