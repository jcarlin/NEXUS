"""Export service layer -- database operations for production sets and export jobs.

All queries use raw ``sqlalchemy.text()`` against the tables created by
migration 010.  No ORM models are involved.
"""

from __future__ import annotations

import json
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db_utils import row_to_dict

logger = structlog.get_logger(__name__)


class ExportService:
    """Static methods for production set CRUD and export job management."""

    # ------------------------------------------------------------------
    # Production Set CRUD
    # ------------------------------------------------------------------

    @staticmethod
    async def create_production_set(
        db: AsyncSession,
        matter_id: UUID,
        user_id: UUID,
        data: dict,
    ) -> dict:
        """Create a new production set and return it."""
        result = await db.execute(
            text("""
                INSERT INTO production_sets
                    (matter_id, name, description, bates_prefix, bates_start,
                     bates_padding, next_bates, status, created_by)
                VALUES
                    (:matter_id, :name, :description, :bates_prefix, :bates_start,
                     :bates_padding, :bates_start, 'draft', :created_by)
                RETURNING id, matter_id, name, description, bates_prefix,
                          bates_start, bates_padding, next_bates, status,
                          created_by, created_at, updated_at
            """),
            {
                "matter_id": matter_id,
                "name": data["name"],
                "description": data.get("description"),
                "bates_prefix": data.get("bates_prefix", "NEXUS"),
                "bates_start": data.get("bates_start", 1),
                "bates_padding": data.get("bates_padding", 6),
                "created_by": user_id,
            },
        )
        row = result.one()
        rec = row_to_dict(row)
        rec["document_count"] = 0
        logger.info("production_set.created", ps_id=str(rec["id"]), name=data["name"])
        return rec

    @staticmethod
    async def get_production_set(
        db: AsyncSession,
        ps_id: UUID,
        matter_id: UUID,
    ) -> dict | None:
        """Fetch a production set by id, including document_count."""
        result = await db.execute(
            text("""
                SELECT ps.*,
                       COALESCE(cnt.doc_count, 0) AS document_count
                FROM production_sets ps
                LEFT JOIN (
                    SELECT production_set_id, count(*) AS doc_count
                    FROM production_set_documents
                    GROUP BY production_set_id
                ) cnt ON cnt.production_set_id = ps.id
                WHERE ps.id = :ps_id AND ps.matter_id = :matter_id
            """),
            {"ps_id": ps_id, "matter_id": matter_id},
        )
        row = result.first()
        if row is None:
            return None
        return row_to_dict(row)

    @staticmethod
    async def list_production_sets(
        db: AsyncSession,
        matter_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        """Return (items, total_count) for production sets in a matter."""
        count_result = await db.execute(
            text("SELECT count(*) FROM production_sets WHERE matter_id = :matter_id"),
            {"matter_id": matter_id},
        )
        total = count_result.scalar_one()

        result = await db.execute(
            text("""
                SELECT ps.*,
                       COALESCE(cnt.doc_count, 0) AS document_count
                FROM production_sets ps
                LEFT JOIN (
                    SELECT production_set_id, count(*) AS doc_count
                    FROM production_set_documents
                    GROUP BY production_set_id
                ) cnt ON cnt.production_set_id = ps.id
                WHERE ps.matter_id = :matter_id
                ORDER BY ps.created_at DESC
                OFFSET :offset
                LIMIT :limit
            """),
            {"matter_id": matter_id, "offset": offset, "limit": limit},
        )
        items = [row_to_dict(r) for r in result.all()]
        return items, total

    @staticmethod
    async def add_documents_to_production_set(
        db: AsyncSession,
        ps_id: UUID,
        matter_id: UUID,
        doc_ids: list[UUID],
    ) -> list[dict]:
        """Add documents to a production set. Validates status=draft and doc ownership."""
        # Validate production set exists and is draft
        ps = await ExportService.get_production_set(db, ps_id, matter_id)
        if ps is None:
            raise ValueError("Production set not found")
        if ps["status"] != "draft":
            raise ValueError("Can only add documents to a draft production set")

        # Validate all documents belong to this matter
        result = await db.execute(
            text("""
                SELECT id FROM documents
                WHERE id = ANY(:doc_ids) AND matter_id = :matter_id
            """),
            {"doc_ids": doc_ids, "matter_id": matter_id},
        )
        valid_ids = {row._mapping["id"] for row in result.all()}
        invalid_ids = set(doc_ids) - valid_ids
        if invalid_ids:
            raise ValueError(f"Documents not found in matter: {[str(i) for i in invalid_ids]}")

        # Bulk insert (skip duplicates via ON CONFLICT)
        added: list[dict] = []
        for doc_id in doc_ids:
            ins_result = await db.execute(
                text("""
                    INSERT INTO production_set_documents
                        (production_set_id, document_id)
                    VALUES (:ps_id, :doc_id)
                    ON CONFLICT (production_set_id, document_id) DO NOTHING
                    RETURNING id, production_set_id, document_id,
                              bates_begin, bates_end, added_at
                """),
                {"ps_id": ps_id, "doc_id": doc_id},
            )
            row = ins_result.first()
            if row is not None:
                added.append(row_to_dict(row))

        logger.info(
            "production_set.documents_added",
            ps_id=str(ps_id),
            added_count=len(added),
        )
        return added

    @staticmethod
    async def list_production_set_documents(
        db: AsyncSession,
        ps_id: UUID,
        matter_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        """Return (items, total) for documents in a production set."""
        # Validate production set belongs to matter
        ps = await ExportService.get_production_set(db, ps_id, matter_id)
        if ps is None:
            raise ValueError("Production set not found")

        count_result = await db.execute(
            text("""
                SELECT count(*) FROM production_set_documents
                WHERE production_set_id = :ps_id
            """),
            {"ps_id": ps_id},
        )
        total = count_result.scalar_one()

        result = await db.execute(
            text("""
                SELECT psd.id, psd.production_set_id, psd.document_id,
                       psd.bates_begin, psd.bates_end, psd.added_at,
                       d.filename
                FROM production_set_documents psd
                JOIN documents d ON d.id = psd.document_id
                WHERE psd.production_set_id = :ps_id
                ORDER BY psd.added_at ASC
                OFFSET :offset
                LIMIT :limit
            """),
            {"ps_id": ps_id, "offset": offset, "limit": limit},
        )
        items = [row_to_dict(r) for r in result.all()]
        return items, total

    @staticmethod
    async def remove_document_from_production_set(
        db: AsyncSession,
        ps_id: UUID,
        doc_id: UUID,
        matter_id: UUID,
    ) -> bool:
        """Remove a document from a production set. Returns True if removed."""
        # Validate production set belongs to matter
        ps = await ExportService.get_production_set(db, ps_id, matter_id)
        if ps is None:
            raise ValueError("Production set not found")
        if ps["status"] != "draft":
            raise ValueError("Can only remove documents from a draft production set")

        result = await db.execute(
            text("""
                DELETE FROM production_set_documents
                WHERE production_set_id = :ps_id AND document_id = :doc_id
            """),
            {"ps_id": ps_id, "doc_id": doc_id},
        )
        deleted: bool = (result.rowcount or 0) > 0
        if deleted:
            logger.info(
                "production_set.document_removed",
                ps_id=str(ps_id),
                doc_id=str(doc_id),
            )
        return deleted

    @staticmethod
    async def assign_bates_numbers(
        db: AsyncSession,
        ps_id: UUID,
        matter_id: UUID,
    ) -> dict:
        """Atomically assign sequential Bates numbers to all documents in a production set.

        Reads the prefix, padding, and next_bates from the production set,
        assigns bates_begin/bates_end to each junction row using page_count
        for ranges, updates documents.bates_begin/bates_end if not already
        set, and sets the production set status to finalized.
        """
        # Load production set
        ps = await ExportService.get_production_set(db, ps_id, matter_id)
        if ps is None:
            raise ValueError("Production set not found")
        if ps["status"] != "draft":
            raise ValueError("Can only assign Bates numbers to a draft production set")

        prefix = ps["bates_prefix"]
        padding = ps["bates_padding"]
        current_number = ps["next_bates"]

        # Get all documents with page counts, ordered by added_at for determinism
        result = await db.execute(
            text("""
                SELECT psd.id AS psd_id, psd.document_id,
                       COALESCE(d.page_count, 1) AS page_count
                FROM production_set_documents psd
                JOIN documents d ON d.id = psd.document_id
                WHERE psd.production_set_id = :ps_id
                ORDER BY psd.added_at ASC
            """),
            {"ps_id": ps_id},
        )
        rows = result.all()

        if not rows:
            raise ValueError("No documents in production set")

        # Assign sequential Bates numbers
        for row in rows:
            page_count = row._mapping["page_count"]
            bates_begin = f"{prefix}{str(current_number).zfill(padding)}"
            bates_end = f"{prefix}{str(current_number + page_count - 1).zfill(padding)}"

            # Update junction table
            await db.execute(
                text("""
                    UPDATE production_set_documents
                    SET bates_begin = :bates_begin, bates_end = :bates_end
                    WHERE id = :psd_id
                """),
                {
                    "psd_id": row._mapping["psd_id"],
                    "bates_begin": bates_begin,
                    "bates_end": bates_end,
                },
            )

            # Update canonical bates on document if not already set
            await db.execute(
                text("""
                    UPDATE documents
                    SET bates_begin = :bates_begin, bates_end = :bates_end,
                        updated_at = now()
                    WHERE id = :doc_id
                      AND bates_begin IS NULL
                """),
                {
                    "doc_id": row._mapping["document_id"],
                    "bates_begin": bates_begin,
                    "bates_end": bates_end,
                },
            )

            current_number += page_count

        # Update production set: next_bates, status
        await db.execute(
            text("""
                UPDATE production_sets
                SET next_bates = :next_bates,
                    status = 'finalized',
                    updated_at = now()
                WHERE id = :ps_id
            """),
            {"ps_id": ps_id, "next_bates": current_number},
        )

        logger.info(
            "production_set.bates_assigned",
            ps_id=str(ps_id),
            documents=len(rows),
            next_bates=current_number,
        )

        # Return updated production set
        return await ExportService.get_production_set(db, ps_id, matter_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Export Jobs
    # ------------------------------------------------------------------

    @staticmethod
    async def create_export_job(
        db: AsyncSession,
        matter_id: UUID,
        user_id: UUID,
        data: dict,
    ) -> dict:
        """Create a new export job record."""
        result = await db.execute(
            text("""
                INSERT INTO export_jobs
                    (matter_id, export_type, export_format, status, parameters, created_by)
                VALUES
                    (:matter_id, :export_type, :export_format, 'pending',
                     CAST(:parameters AS jsonb), :created_by)
                RETURNING id, matter_id, export_type, export_format, status,
                          parameters, output_path, file_size_bytes, error,
                          created_by, created_at, completed_at
            """),
            {
                "matter_id": matter_id,
                "export_type": data["export_type"],
                "export_format": data.get("export_format", "zip"),
                "parameters": json.dumps(data.get("parameters", {})),
                "created_by": user_id,
            },
        )
        row = result.one()
        rec = row_to_dict(row)
        logger.info(
            "export_job.created",
            job_id=str(rec["id"]),
            export_type=data["export_type"],
        )
        return rec

    @staticmethod
    async def get_export_job(
        db: AsyncSession,
        job_id: UUID,
        matter_id: UUID,
    ) -> dict | None:
        """Fetch an export job by id, scoped to matter."""
        result = await db.execute(
            text("""
                SELECT id, matter_id, export_type, export_format, status,
                       parameters, output_path, file_size_bytes, error,
                       created_by, created_at, completed_at
                FROM export_jobs
                WHERE id = :job_id AND matter_id = :matter_id
            """),
            {"job_id": job_id, "matter_id": matter_id},
        )
        row = result.first()
        if row is None:
            return None
        return row_to_dict(row)

    @staticmethod
    async def list_export_jobs(
        db: AsyncSession,
        matter_id: UUID,
        export_type: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        """Return (items, total) for export jobs in a matter."""
        from app.common.db_utils import build_where_clause

        where_sql, params = build_where_clause(
            {
                "matter_id": ("matter_id = :matter_id", matter_id),
                "export_type": ("export_type = :export_type", export_type),
                "status": ("status = :status", status),
            }
        )
        params["offset"] = offset
        params["limit"] = limit

        count_result = await db.execute(
            text(f"SELECT count(*) FROM export_jobs {where_sql}"),
            params,
        )
        total = count_result.scalar_one()

        result = await db.execute(
            text(f"""
                SELECT id, matter_id, export_type, export_format, status,
                       parameters, output_path, file_size_bytes, error,
                       created_by, created_at, completed_at
                FROM export_jobs
                {where_sql}
                ORDER BY created_at DESC
                OFFSET :offset
                LIMIT :limit
            """),
            params,
        )
        items = [row_to_dict(r) for r in result.all()]
        return items, total

    # ------------------------------------------------------------------
    # Bates Import helper
    # ------------------------------------------------------------------

    @staticmethod
    async def import_bates_from_loadfile(
        db: AsyncSession,
        matter_id: UUID,
        records: list,
    ) -> int:
        """Import Bates numbers from parsed load file records.

        Accepts either ``LoadFileRecord`` objects (with ``.doc_id`` and
        ``.fields`` dict) or plain dicts.  Extracts BEGBATES/ENDBATES and
        updates ``documents.bates_begin/bates_end`` where records match.
        Returns count of updated documents.
        """
        updated_count = 0
        for record in records:
            # Support both LoadFileRecord objects and plain dicts
            if hasattr(record, "doc_id"):
                doc_id = record.doc_id
                fields = record.fields
            else:
                doc_id = record.get("doc_id")
                fields = record

            beg = fields.get("BEGBATES") or fields.get("BegBates") or fields.get("bates_begin")
            end = fields.get("ENDBATES") or fields.get("EndBates") or fields.get("bates_end")
            if not doc_id or not beg:
                continue

            result = await db.execute(
                text("""
                    UPDATE documents
                    SET bates_begin = :bates_begin,
                        bates_end = :bates_end,
                        updated_at = now()
                    WHERE id::text = :doc_id AND matter_id = :matter_id
                      AND bates_begin IS NULL
                """),
                {
                    "doc_id": doc_id,
                    "bates_begin": beg,
                    "bates_end": end or beg,
                    "matter_id": matter_id,
                },
            )
            if (result.rowcount or 0) > 0:
                updated_count += 1

        if updated_count > 0:
            logger.info(
                "bates.imported_from_loadfile",
                matter_id=str(matter_id),
                total_records=len(records),
                updated_count=updated_count,
            )
        return updated_count

    # ------------------------------------------------------------------
    # Privilege Log Preview
    # ------------------------------------------------------------------

    @staticmethod
    async def get_privilege_log_preview(
        db: AsyncSession,
        matter_id: UUID,
        production_set_id: UUID | None = None,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        """Return (entries, total) for a privilege log preview.

        If production_set_id is given, scopes to documents in that set.
        """
        if production_set_id is not None:
            count_result = await db.execute(
                text("""
                    SELECT count(*) FROM documents d
                    JOIN production_set_documents psd ON psd.document_id = d.id
                    WHERE d.matter_id = :matter_id
                      AND psd.production_set_id = :ps_id
                      AND d.privilege_status IN ('privileged', 'work_product')
                """),
                {"matter_id": matter_id, "ps_id": production_set_id},
            )
            total = count_result.scalar_one()

            result = await db.execute(
                text("""
                    SELECT psd.bates_begin, psd.bates_end,
                           d.filename, d.document_type AS doc_type,
                           d.created_at AS date,
                           d.privilege_status, d.privilege_reviewed_by,
                           d.privilege_reviewed_at
                    FROM documents d
                    JOIN production_set_documents psd ON psd.document_id = d.id
                    WHERE d.matter_id = :matter_id
                      AND psd.production_set_id = :ps_id
                      AND d.privilege_status IN ('privileged', 'work_product')
                    ORDER BY psd.bates_begin ASC NULLS LAST
                    LIMIT :limit
                """),
                {"matter_id": matter_id, "ps_id": production_set_id, "limit": limit},
            )
        else:
            count_result = await db.execute(
                text("""
                    SELECT count(*) FROM documents
                    WHERE matter_id = :matter_id
                      AND privilege_status IN ('privileged', 'work_product')
                """),
                {"matter_id": matter_id},
            )
            total = count_result.scalar_one()

            result = await db.execute(
                text("""
                    SELECT bates_begin, bates_end,
                           filename, document_type AS doc_type,
                           created_at AS date,
                           privilege_status, privilege_reviewed_by,
                           privilege_reviewed_at
                    FROM documents
                    WHERE matter_id = :matter_id
                      AND privilege_status IN ('privileged', 'work_product')
                    ORDER BY bates_begin ASC NULLS LAST
                    LIMIT :limit
                """),
                {"matter_id": matter_id, "limit": limit},
            )

        entries = []
        for row in result.all():
            m = row._mapping
            priv = m["privilege_status"]
            basis = "Attorney-Client Privilege" if priv == "privileged" else "Work Product Doctrine"
            entries.append(
                {
                    "bates_begin": m.get("bates_begin"),
                    "bates_end": m.get("bates_end"),
                    "filename": m["filename"],
                    "doc_type": m.get("doc_type"),
                    "date": m.get("date"),
                    "privilege_status": priv,
                    "privilege_basis": basis,
                    "reviewed_by": str(m["privilege_reviewed_by"]) if m.get("privilege_reviewed_by") else None,
                    "reviewed_at": m.get("privilege_reviewed_at"),
                }
            )

        return entries, total
