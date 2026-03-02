"""Annotation service layer -- database operations for the annotations table.

All queries use raw ``sqlalchemy.text()`` against the table created by
migration 010.  No ORM models are involved.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.annotations.schemas import AnnotationCreate, AnnotationUpdate
from app.common.db_utils import row_to_dict

logger = structlog.get_logger(__name__)

_COLUMNS = """id, document_id, matter_id, user_id, page_number,
              annotation_type, content, anchor, color,
              created_at, updated_at"""


class AnnotationService:
    """Static-style methods for annotation CRUD.  All methods are async and
    expect a caller-managed ``AsyncSession``."""

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------

    @staticmethod
    async def create_annotation(
        db: AsyncSession,
        matter_id: UUID,
        user_id: UUID,
        data: AnnotationCreate,
    ) -> dict:
        """Insert a new annotation after validating the document belongs to the matter."""
        # Validate document belongs to matter
        doc_check = await db.execute(
            text("SELECT id FROM documents WHERE id = :doc_id AND matter_id = :matter_id"),
            {"doc_id": data.document_id, "matter_id": matter_id},
        )
        if doc_check.first() is None:
            raise ValueError(f"Document {data.document_id} not found in matter {matter_id}")

        result = await db.execute(
            text(f"""
                INSERT INTO annotations (
                    document_id, matter_id, user_id, page_number,
                    annotation_type, content, anchor, color
                )
                VALUES (
                    :document_id, :matter_id, :user_id, :page_number,
                    :annotation_type, :content, CAST(:anchor AS jsonb), :color
                )
                RETURNING {_COLUMNS}
            """),
            {
                "document_id": data.document_id,
                "matter_id": matter_id,
                "user_id": user_id,
                "page_number": data.page_number,
                "annotation_type": data.annotation_type.value,
                "content": data.content,
                "anchor": _json_dumps(data.anchor),
                "color": data.color,
            },
        )
        row = result.one()
        logger.info(
            "annotation.created",
            annotation_id=str(row._mapping["id"]),
            document_id=str(data.document_id),
            matter_id=str(matter_id),
        )
        return row_to_dict(row)

    # ------------------------------------------------------------------
    # GET (single by id)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_annotation(
        db: AsyncSession,
        annotation_id: UUID,
        matter_id: UUID,
    ) -> dict | None:
        """Fetch a single annotation by id, scoped to matter."""
        result = await db.execute(
            text(f"SELECT {_COLUMNS} FROM annotations WHERE id = :id AND matter_id = :matter_id"),
            {"id": annotation_id, "matter_id": matter_id},
        )
        row = result.first()
        if row is None:
            return None
        return row_to_dict(row)

    # ------------------------------------------------------------------
    # LIST (paginated, filterable)
    # ------------------------------------------------------------------

    @staticmethod
    async def list_annotations(
        db: AsyncSession,
        matter_id: UUID,
        document_id: UUID | None = None,
        user_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        """Return ``(items, total_count)`` with offset/limit pagination."""
        where_clauses: list[str] = ["matter_id = :matter_id"]
        params: dict = {"matter_id": matter_id, "offset": offset, "limit": limit}

        if document_id is not None:
            where_clauses.append("document_id = :document_id")
            params["document_id"] = document_id

        if user_id is not None:
            where_clauses.append("user_id = :user_id")
            params["user_id"] = user_id

        where_sql = "WHERE " + " AND ".join(where_clauses)

        # Total count
        count_result = await db.execute(
            text(f"SELECT count(*) FROM annotations {where_sql}"),
            params,
        )
        total = count_result.scalar_one()

        # Paginated rows
        result = await db.execute(
            text(f"""
                SELECT {_COLUMNS}
                FROM annotations
                {where_sql}
                ORDER BY created_at DESC
                OFFSET :offset
                LIMIT :limit
            """),
            params,
        )
        rows = result.all()
        items = [row_to_dict(r) for r in rows]

        return items, total

    # ------------------------------------------------------------------
    # UPDATE
    # ------------------------------------------------------------------

    @staticmethod
    async def update_annotation(
        db: AsyncSession,
        annotation_id: UUID,
        matter_id: UUID,
        user_id: UUID,
        data: AnnotationUpdate,
    ) -> dict | None:
        """Update an annotation.  Only the owner can edit."""
        set_clauses: list[str] = ["updated_at = now()"]
        params: dict = {"id": annotation_id, "matter_id": matter_id, "user_id": user_id}

        if data.content is not None:
            set_clauses.append("content = :content")
            params["content"] = data.content

        if data.anchor is not None:
            set_clauses.append("anchor = CAST(:anchor AS jsonb)")
            params["anchor"] = _json_dumps(data.anchor)

        if data.color is not None:
            set_clauses.append("color = :color")
            params["color"] = data.color

        set_sql = ", ".join(set_clauses)

        result = await db.execute(
            text(f"""
                UPDATE annotations
                SET {set_sql}
                WHERE id = :id AND matter_id = :matter_id AND user_id = :user_id
                RETURNING {_COLUMNS}
            """),
            params,
        )
        row = result.first()
        if row is None:
            return None

        logger.info(
            "annotation.updated",
            annotation_id=str(annotation_id),
            matter_id=str(matter_id),
        )
        return row_to_dict(row)

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    @staticmethod
    async def delete_annotation(
        db: AsyncSession,
        annotation_id: UUID,
        matter_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Delete an annotation.  Only the owner can delete.

        Returns ``True`` if a row was deleted, ``False`` if not found.
        """
        result = await db.execute(
            text("DELETE FROM annotations WHERE id = :id AND matter_id = :matter_id AND user_id = :user_id"),
            {"id": annotation_id, "matter_id": matter_id, "user_id": user_id},
        )
        deleted: bool = (result.rowcount or 0) > 0

        if deleted:
            logger.info("annotation.deleted", annotation_id=str(annotation_id))
        else:
            logger.warning("annotation.delete_noop", annotation_id=str(annotation_id))

        return deleted


def _json_dumps(obj: dict) -> str:
    """Serialize a dict to JSON string for JSONB parameters."""
    import json

    return json.dumps(obj)
