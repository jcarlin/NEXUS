"""Evaluation service — dataset CRUD, run management, metrics."""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluation.schemas import (
    DatasetItemCreate,
    DatasetItemResponse,
    DatasetType,
    EvalMetrics,
    EvalMode,
    EvalRunResponse,
    EvalRunStatus,
    LatestEvalResponse,
)

logger = structlog.get_logger(__name__)


class EvaluationService:
    """Static methods for evaluation operations."""

    # ------------------------------------------------------------------
    # Dataset items
    # ------------------------------------------------------------------

    @staticmethod
    async def list_dataset_items(
        db: AsyncSession,
        dataset_type: DatasetType,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[DatasetItemResponse], int]:
        count_result = await db.execute(
            text("SELECT count(*) FROM evaluation_dataset_items WHERE dataset_type = :dt"),
            {"dt": dataset_type},
        )
        total = count_result.scalar_one()

        result = await db.execute(
            text("""
                SELECT id, dataset_type, question, expected_answer, tags,
                       metadata_ , created_at
                FROM evaluation_dataset_items
                WHERE dataset_type = :dt
                ORDER BY created_at DESC
                OFFSET :offset LIMIT :limit
            """),
            {"dt": dataset_type, "offset": offset, "limit": limit},
        )
        rows = result.mappings().all()
        items = [DatasetItemResponse(**dict(r)) for r in rows]
        return items, total

    @staticmethod
    async def create_dataset_item(
        db: AsyncSession,
        dataset_type: DatasetType,
        item: DatasetItemCreate,
    ) -> DatasetItemResponse:
        result = await db.execute(
            text("""
                INSERT INTO evaluation_dataset_items
                    (dataset_type, question, expected_answer, tags, metadata_)
                VALUES (:dt, :question, :expected_answer, :tags, :metadata_)
                RETURNING id, dataset_type, question, expected_answer, tags, metadata_, created_at
            """),
            {
                "dt": dataset_type,
                "question": item.question,
                "expected_answer": item.expected_answer,
                "tags": item.tags,
                "metadata_": item.metadata_,
            },
        )
        row = result.mappings().one()
        return DatasetItemResponse(**dict(row))

    @staticmethod
    async def delete_dataset_item(db: AsyncSession, item_id: UUID) -> bool:
        result = await db.execute(
            text("DELETE FROM evaluation_dataset_items WHERE id = :id RETURNING id"),
            {"id": item_id},
        )
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # Evaluation runs
    # ------------------------------------------------------------------

    @staticmethod
    async def list_runs(
        db: AsyncSession,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[EvalRunResponse], int]:
        count_result = await db.execute(text("SELECT count(*) FROM evaluation_runs"))
        total = count_result.scalar_one()

        result = await db.execute(
            text("""
                SELECT id, mode, status, metrics, config_overrides,
                       total_items, processed_items, error,
                       created_at, completed_at
                FROM evaluation_runs
                ORDER BY created_at DESC
                OFFSET :offset LIMIT :limit
            """),
            {"offset": offset, "limit": limit},
        )
        rows = result.mappings().all()
        items = []
        for r in rows:
            d = dict(r)
            if d.get("metrics"):
                d["metrics"] = EvalMetrics(**d["metrics"])
            items.append(EvalRunResponse(**d))
        return items, total

    @staticmethod
    async def create_run(
        db: AsyncSession,
        mode: EvalMode,
        config_overrides: dict,
    ) -> EvalRunResponse:
        result = await db.execute(
            text("""
                INSERT INTO evaluation_runs (mode, status, config_overrides)
                VALUES (:mode, :status, :config_overrides)
                RETURNING id, mode, status, metrics, config_overrides,
                          total_items, processed_items, error,
                          created_at, completed_at
            """),
            {
                "mode": mode,
                "status": EvalRunStatus.PENDING,
                "config_overrides": config_overrides,
            },
        )
        row = result.mappings().one()
        return EvalRunResponse(**dict(row))

    @staticmethod
    async def get_latest(db: AsyncSession) -> LatestEvalResponse | None:
        result = await db.execute(
            text("""
                SELECT id, metrics, completed_at
                FROM evaluation_runs
                WHERE status = 'completed' AND metrics IS NOT NULL
                ORDER BY completed_at DESC
                LIMIT 1
            """)
        )
        row = result.mappings().first()
        if not row:
            return None
        d = dict(row)
        metrics = EvalMetrics(**d["metrics"]) if d["metrics"] else EvalMetrics()
        passed = all(
            [
                metrics.accuracy >= 0.7,
                metrics.faithfulness >= 0.7,
                metrics.relevance >= 0.7,
            ]
        )
        return LatestEvalResponse(
            metrics=metrics,
            passed=passed,
            run_id=d["id"],
            completed_at=d["completed_at"],
        )
