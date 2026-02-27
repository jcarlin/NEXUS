"""Document service layer — database operations for the documents table.

All queries use raw ``sqlalchemy.text()`` against the tables created by
migration 001.  No ORM models are involved.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Column list shared across queries
_COLUMNS = """id, job_id, filename, document_type, page_count, chunk_count,
              entity_count, minio_path, file_size_bytes, content_hash,
              metadata_, created_at, updated_at"""


def _row_to_dict(row) -> dict:
    """Convert a SQLAlchemy Row (from text query) into a plain dict."""
    return dict(row._mapping)


class DocumentService:
    """Static-style methods for document CRUD.  All methods are async and
    expect a caller-managed ``AsyncSession``."""

    # ------------------------------------------------------------------
    # LIST (paginated, with optional filters)
    # ------------------------------------------------------------------

    @staticmethod
    async def list_documents(
        db: AsyncSession,
        document_type: str | None = None,
        filename_search: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        """Return ``(items, total_count)`` with offset/limit pagination.

        Optional filters:
        - *document_type*: exact match on the ``document_type`` column.
        - *filename_search*: case-insensitive substring match via ``ILIKE``.

        Documents are ordered by ``created_at DESC`` (newest first).
        """
        where_clauses: list[str] = []
        params: dict = {"offset": offset, "limit": limit}

        if document_type is not None:
            where_clauses.append("document_type = :document_type")
            params["document_type"] = document_type

        if filename_search is not None:
            where_clauses.append("filename ILIKE :filename_search")
            params["filename_search"] = f"%{filename_search}%"

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # Total count
        count_result = await db.execute(
            text(f"SELECT count(*) FROM documents {where_sql}"),
            params,
        )
        total = count_result.scalar_one()

        # Paginated rows
        result = await db.execute(
            text(
                f"""
                SELECT {_COLUMNS}
                FROM documents
                {where_sql}
                ORDER BY created_at DESC
                OFFSET :offset
                LIMIT :limit
                """
            ),
            params,
        )
        rows = result.all()
        items = [_row_to_dict(r) for r in rows]

        return items, total

    # ------------------------------------------------------------------
    # GET (single by id)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_document(db: AsyncSession, doc_id: UUID) -> dict | None:
        """Fetch a single document by id.  Returns ``None`` if not found."""
        result = await db.execute(
            text(f"SELECT {_COLUMNS} FROM documents WHERE id = :doc_id"),
            {"doc_id": doc_id},
        )
        row = result.first()
        if row is None:
            return None
        return _row_to_dict(row)

    # ------------------------------------------------------------------
    # GET (single by job_id)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_document_by_job(db: AsyncSession, job_id: UUID) -> dict | None:
        """Fetch a single document by its parent job_id."""
        result = await db.execute(
            text(f"SELECT {_COLUMNS} FROM documents WHERE job_id = :job_id"),
            {"job_id": job_id},
        )
        row = result.first()
        if row is None:
            return None
        return _row_to_dict(row)

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    @staticmethod
    async def delete_document(db: AsyncSession, doc_id: UUID) -> bool:
        """Delete a document by id.

        Returns ``True`` if a row was deleted, ``False`` if not found.
        """
        result = await db.execute(
            text("DELETE FROM documents WHERE id = :doc_id"),
            {"doc_id": doc_id},
        )
        deleted = result.rowcount > 0

        if deleted:
            logger.info("document.deleted", doc_id=str(doc_id))
        else:
            logger.warning("document.delete_noop", doc_id=str(doc_id))

        return deleted
