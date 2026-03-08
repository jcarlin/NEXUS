"""Document service layer — database operations for the documents table.

All queries use raw ``sqlalchemy.text()`` against the tables created by
migration 001.  No ORM models are involved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db_utils import row_to_dict

if TYPE_CHECKING:
    from app.common.vector_store import VectorStoreClient
    from app.entities.graph_service import GraphService

logger = structlog.get_logger(__name__)

# Column list shared across queries
_COLUMNS = """id, job_id, filename, document_type, page_count, chunk_count,
              entity_count, minio_path, file_size_bytes, content_hash,
              matter_id, metadata_, created_at, updated_at,
              privilege_status, privilege_reviewed_by, privilege_reviewed_at,
              message_id, in_reply_to, references_, thread_id, thread_position,
              is_inclusive, duplicate_cluster_id, duplicate_score,
              version_group_id, version_number, is_final_version,
              sentiment_positive, sentiment_negative, sentiment_pressure,
              sentiment_opportunity, sentiment_rationalization, sentiment_intent,
              sentiment_concealment, hot_doc_score, context_gap_score,
              context_gaps, anomaly_score,
              bates_begin, bates_end"""

# Privilege statuses that non-privileged users (paralegal, reviewer) cannot see
_RESTRICTED_STATUSES = ("privileged", "work_product")


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
        file_extension: str | None = None,
        filename_search: str | None = None,
        hot_doc_score_min: float | None = None,
        anomaly_score_min: float | None = None,
        offset: int = 0,
        limit: int = 50,
        matter_id: UUID | None = None,
        user_role: str | None = None,
        dataset_id: UUID | None = None,
        tag_name: str | None = None,
    ) -> tuple[list[dict], int]:
        """Return ``(items, total_count)`` with offset/limit pagination.

        Optional filters:
        - *document_type*: exact match on the ``document_type`` column.
        - *file_extension*: filter by file extension (e.g. ``pdf``, ``docx``).
        - *filename_search*: case-insensitive substring match via ``ILIKE``.
        - *hot_doc_score_min*: minimum hot_doc_score threshold.
        - *anomaly_score_min*: minimum anomaly_score threshold.
        - *matter_id*: scope to a specific case matter.
        - *user_role*: when not admin/attorney, filters out privileged/work_product docs.
        - *dataset_id*: scope to documents in a specific dataset.
        - *tag_name*: scope to documents with a specific tag.

        Documents are ordered by ``created_at DESC`` (newest first).
        """
        join_clauses: list[str] = []
        where_clauses: list[str] = []
        params: dict = {"offset": offset, "limit": limit}

        if dataset_id is not None:
            join_clauses.append("JOIN dataset_documents dd ON dd.document_id = d.id AND dd.dataset_id = :dataset_id")
            params["dataset_id"] = dataset_id

        if tag_name is not None:
            join_clauses.append("JOIN document_tags dt ON dt.document_id = d.id AND dt.tag_name = :tag_name")
            params["tag_name"] = tag_name

        if matter_id is not None:
            where_clauses.append("d.matter_id = :matter_id")
            params["matter_id"] = matter_id

        if document_type is not None:
            where_clauses.append("d.document_type = :document_type")
            params["document_type"] = document_type

        if file_extension is not None:
            where_clauses.append("d.filename ILIKE :file_ext_pattern")
            params["file_ext_pattern"] = f"%.{file_extension}"

        if filename_search is not None:
            where_clauses.append("d.filename ILIKE :filename_search")
            params["filename_search"] = f"%{filename_search}%"

        if hot_doc_score_min is not None:
            where_clauses.append("d.hot_doc_score >= :hot_doc_score_min")
            params["hot_doc_score_min"] = hot_doc_score_min

        if anomaly_score_min is not None:
            where_clauses.append("d.anomaly_score >= :anomaly_score_min")
            params["anomaly_score_min"] = anomaly_score_min

        # Privilege filtering: non-admin/attorney users cannot see restricted docs
        if user_role not in ("admin", "attorney"):
            where_clauses.append(
                "(d.privilege_status IS NULL OR d.privilege_status NOT IN ('privileged', 'work_product'))"
            )

        join_sql = " ".join(join_clauses)
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # Total count
        count_result = await db.execute(
            text(f"SELECT count(*) FROM documents d {join_sql} {where_sql}"),
            params,
        )
        total = count_result.scalar_one()

        # Paginated rows — qualify column list with table alias
        columns_qualified = ", ".join(f"d.{c.strip()}" for c in _COLUMNS.split(","))
        result = await db.execute(
            text(
                f"""
                SELECT {columns_qualified}
                FROM documents d
                {join_sql}
                {where_sql}
                ORDER BY d.created_at DESC
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
    # GET (single by id)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_document(
        db: AsyncSession,
        doc_id: UUID,
        matter_id: UUID | None = None,
        user_role: str | None = None,
    ) -> dict | None:
        """Fetch a single document by id.  Returns ``None`` if not found.

        When *user_role* is not admin/attorney, documents with privilege_status
        of ``privileged`` or ``work_product`` are treated as not found.
        """
        where = "WHERE id = :doc_id"
        params: dict = {"doc_id": doc_id}
        if matter_id is not None:
            where += " AND matter_id = :matter_id"
            params["matter_id"] = matter_id

        if user_role not in ("admin", "attorney"):
            where += " AND (privilege_status IS NULL OR privilege_status NOT IN ('privileged', 'work_product'))"

        result = await db.execute(
            text(f"SELECT {_COLUMNS} FROM documents {where}"),
            params,
        )
        row = result.first()
        if row is None:
            return None
        return row_to_dict(row)

    # ------------------------------------------------------------------
    # GET (single by job_id)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_document_by_job(
        db: AsyncSession,
        job_id: UUID,
        matter_id: UUID | None = None,
        user_role: str | None = None,
    ) -> dict | None:
        """Fetch a single document by its parent job_id.

        Supports the same *matter_id* and *user_role* privilege filtering
        as :meth:`get_document`.
        """
        where = "WHERE job_id = :job_id"
        params: dict = {"job_id": job_id}
        if matter_id is not None:
            where += " AND matter_id = :matter_id"
            params["matter_id"] = matter_id

        if user_role not in ("admin", "attorney"):
            where += " AND (privilege_status IS NULL OR privilege_status NOT IN ('privileged', 'work_product'))"

        result = await db.execute(
            text(f"SELECT {_COLUMNS} FROM documents {where}"),
            params,
        )
        row = result.first()
        if row is None:
            return None
        return row_to_dict(row)

    # ------------------------------------------------------------------
    # PRIVILEGE UPDATE
    # ------------------------------------------------------------------

    @staticmethod
    async def update_privilege(
        db: AsyncSession,
        doc_id: UUID,
        privilege_status: str,
        reviewed_by: UUID,
    ) -> dict | None:
        """Update a document's privilege status.

        Returns the updated row dict or ``None`` if the document was not found.
        """
        result = await db.execute(
            text("""
                UPDATE documents
                SET privilege_status = :privilege_status,
                    privilege_reviewed_by = :reviewed_by,
                    privilege_reviewed_at = now(),
                    updated_at = now()
                WHERE id = :doc_id
                RETURNING privilege_reviewed_at
            """),
            {
                "doc_id": doc_id,
                "privilege_status": privilege_status,
                "reviewed_by": reviewed_by,
            },
        )
        row = result.first()
        if row is None:
            return None

        reviewed_at = row._mapping["privilege_reviewed_at"]
        logger.info(
            "document.privilege_updated",
            doc_id=str(doc_id),
            privilege_status=privilege_status,
            reviewed_by=str(reviewed_by),
        )
        return {
            "id": doc_id,
            "privilege_status": privilege_status,
            "privilege_reviewed_by": reviewed_by,
            "privilege_reviewed_at": reviewed_at,
        }

    # ------------------------------------------------------------------
    # PRIVILEGE UPDATE (cross-store orchestration)
    # ------------------------------------------------------------------

    @staticmethod
    async def update_privilege_across_stores(
        db: AsyncSession,
        doc_id: UUID,
        privilege_status: str,
        reviewed_by: UUID,
        qdrant: VectorStoreClient,
        gs: GraphService,
        job_id: str,
    ) -> dict:
        """Update privilege status across PostgreSQL, Qdrant, and Neo4j.

        Raises if any step fails after the PostgreSQL update.
        Returns the updated privilege record dict.
        """

        # Step 1: Update PostgreSQL
        updated = await DocumentService.update_privilege(
            db=db,
            doc_id=doc_id,
            privilege_status=privilege_status,
            reviewed_by=reviewed_by,
        )
        if updated is None:
            return None  # type: ignore[return-value]

        # Step 2: Update Qdrant payload
        await qdrant.update_privilege_status(doc_id=job_id, privilege_status=privilege_status)

        # Step 3: Update Neo4j Document node
        await gs.update_document_privilege(doc_id=job_id, privilege_status=privilege_status)

        return updated

    # ------------------------------------------------------------------
    # LIST BY THREAD
    # ------------------------------------------------------------------

    @staticmethod
    async def list_by_thread(
        db: AsyncSession,
        thread_id: str,
        matter_id: UUID | None = None,
    ) -> list[dict]:
        """List all documents in an email thread, ordered by thread_position."""
        where = "WHERE thread_id = :thread_id"
        params: dict = {"thread_id": thread_id}
        if matter_id is not None:
            where += " AND matter_id = :matter_id"
            params["matter_id"] = matter_id

        result = await db.execute(
            text(f"SELECT {_COLUMNS} FROM documents {where} ORDER BY thread_position ASC"),
            params,
        )
        return [row_to_dict(r) for r in result.all()]

    # ------------------------------------------------------------------
    # LIST BY CLUSTER
    # ------------------------------------------------------------------

    @staticmethod
    async def list_by_cluster(
        db: AsyncSession,
        cluster_id: str,
        matter_id: UUID | None = None,
    ) -> list[dict]:
        """List all documents in a duplicate cluster."""
        where = "WHERE duplicate_cluster_id = :cluster_id"
        params: dict = {"cluster_id": cluster_id}
        if matter_id is not None:
            where += " AND matter_id = :matter_id"
            params["matter_id"] = matter_id

        result = await db.execute(
            text(f"SELECT {_COLUMNS} FROM documents {where} ORDER BY duplicate_score DESC NULLS LAST"),
            params,
        )
        return [row_to_dict(r) for r in result.all()]

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
        deleted: bool = (result.rowcount or 0) > 0  # type: ignore[attr-defined]

        if deleted:
            logger.info("document.deleted", doc_id=str(doc_id))
        else:
            logger.warning("document.delete_noop", doc_id=str(doc_id))

        return deleted
