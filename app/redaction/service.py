"""Redaction service layer — business logic and database operations.

All queries use raw ``sqlalchemy.text()`` against tables created by
migration 011.  No ORM models.  All operations are matter-scoped.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db_utils import row_to_dict
from app.common.storage import StorageClient
from app.redaction.engine import hash_text, redact_pdf
from app.redaction.pii_detector import detect_pii
from app.redaction.schemas import PIIDetection, RedactionSpec

logger = structlog.get_logger(__name__)

_LOG_COLUMNS = """id, document_id, matter_id, user_id, redaction_type,
                  pii_category, page_number, span_start, span_end,
                  reason, original_text_hash, created_at"""


class RedactionService:
    """Static-style methods for redaction operations.  All methods are async
    and expect a caller-managed ``AsyncSession``."""

    # ------------------------------------------------------------------
    # PII Detection
    # ------------------------------------------------------------------

    @staticmethod
    async def detect_pii_for_document(
        db: AsyncSession,
        matter_id: UUID,
        document_id: UUID,
    ) -> list[PIIDetection]:
        """Detect PII in all chunks of a document.

        Fetches chunk text from the DB, runs regex-based PII detection on
        each chunk, and returns aggregated detections with chunk references.
        """
        # Validate document belongs to matter
        doc_check = await db.execute(
            text("SELECT id FROM documents WHERE id = :doc_id AND matter_id = :matter_id"),
            {"doc_id": document_id, "matter_id": matter_id},
        )
        if doc_check.first() is None:
            raise ValueError(f"Document {document_id} not found in matter {matter_id}")

        # Fetch chunks for the document
        result = await db.execute(
            text("""
                SELECT chunk_index, page_number, content
                FROM document_chunks
                WHERE document_id = :doc_id
                ORDER BY chunk_index
            """),
            {"doc_id": document_id},
        )
        chunks = result.all()

        all_detections: list[PIIDetection] = []
        for chunk in chunks:
            mapping = chunk._mapping
            content = mapping["content"]
            chunk_idx = mapping["chunk_index"]
            page_num = mapping.get("page_number")

            detections = detect_pii(content)
            for d in detections:
                d.chunk_index = chunk_idx
                d.page_number = page_num
            all_detections.extend(detections)

        logger.info(
            "redaction.pii_detected",
            document_id=str(document_id),
            detection_count=len(all_detections),
        )
        return all_detections

    # ------------------------------------------------------------------
    # Privilege Redaction Suggestions
    # ------------------------------------------------------------------

    @staticmethod
    async def suggest_privilege_redactions(
        db: AsyncSession,
        matter_id: UUID,
        document_id: UUID,
    ) -> list[PIIDetection]:
        """Suggest redactions based on document privilege status.

        If the document is marked as privileged or work_product, returns
        a suggestion covering the entire document.
        """
        result = await db.execute(
            text("""
                SELECT id, privilege_status
                FROM documents
                WHERE id = :doc_id AND matter_id = :matter_id
            """),
            {"doc_id": document_id, "matter_id": matter_id},
        )
        row = result.first()
        if row is None:
            raise ValueError(f"Document {document_id} not found in matter {matter_id}")

        mapping = row._mapping
        status = mapping.get("privilege_status")

        if status in ("privileged", "work_product"):
            return [
                PIIDetection(
                    text="[Full document — privilege-protected]",
                    category="ssn",  # placeholder; the redaction_type=privilege differentiates
                    confidence=1.0,
                    start=0,
                    end=0,
                    page_number=None,
                ),
            ]
        return []

    # ------------------------------------------------------------------
    # Apply Redactions
    # ------------------------------------------------------------------

    @staticmethod
    async def apply_redactions(
        db: AsyncSession,
        storage: StorageClient,
        matter_id: UUID,
        document_id: UUID,
        user_id: UUID,
        specs: list[RedactionSpec],
    ) -> dict:
        """Apply redactions to a document's PDF.

        1. Validate document belongs to matter
        2. Download original PDF from MinIO
        3. Run redaction engine to produce redacted PDF
        4. Upload redacted PDF to MinIO
        5. Insert redaction log entries (one per spec)
        6. Update documents.redacted_pdf_path
        7. Return summary
        """
        # 1. Validate document
        doc_result = await db.execute(
            text("SELECT id, minio_path FROM documents WHERE id = :doc_id AND matter_id = :matter_id"),
            {"doc_id": document_id, "matter_id": matter_id},
        )
        doc_row = doc_result.first()
        if doc_row is None:
            raise ValueError(f"Document {document_id} not found in matter {matter_id}")

        file_path = doc_row._mapping["minio_path"]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_pdf = tmp / "original.pdf"
            output_pdf = tmp / "redacted.pdf"

            # 2. Download original PDF
            pdf_bytes = await storage.download_bytes(file_path)
            input_pdf.write_bytes(pdf_bytes)

            # 3. Redact
            redaction_count = redact_pdf(input_pdf, output_pdf, specs)

            # 4. Upload redacted PDF
            redacted_key = f"redacted/{matter_id}/{document_id}.pdf"
            redacted_bytes = output_pdf.read_bytes()
            await storage.upload_bytes(redacted_key, redacted_bytes, content_type="application/pdf")

        # 5. Insert redaction log entries
        for spec in specs:
            # Hash a representation of the redaction target (NOT the text itself — rule 39)
            text_repr = f"{spec.start}:{spec.end}:{spec.reason}"
            text_hash = hash_text(text_repr)

            await db.execute(
                text(f"""
                    INSERT INTO redactions (
                        document_id, matter_id, user_id, redaction_type,
                        pii_category, page_number, span_start, span_end,
                        reason, original_text_hash
                    )
                    VALUES (
                        :document_id, :matter_id, :user_id, :redaction_type,
                        :pii_category, :page_number, :span_start, :span_end,
                        :reason, :original_text_hash
                    )
                    RETURNING {_LOG_COLUMNS}
                """),
                {
                    "document_id": document_id,
                    "matter_id": matter_id,
                    "user_id": user_id,
                    "redaction_type": spec.redaction_type.value,
                    "pii_category": spec.pii_category.value if spec.pii_category else None,
                    "page_number": spec.page_number,
                    "span_start": spec.start,
                    "span_end": spec.end,
                    "reason": spec.reason,
                    "original_text_hash": text_hash,
                },
            )

        # 6. Update document
        await db.execute(
            text("UPDATE documents SET redacted_pdf_path = :path WHERE id = :doc_id"),
            {"path": redacted_key, "doc_id": document_id},
        )

        logger.info(
            "redaction.applied",
            document_id=str(document_id),
            matter_id=str(matter_id),
            redaction_count=redaction_count,
        )

        return {
            "document_id": document_id,
            "matter_id": matter_id,
            "redaction_count": redaction_count,
            "redacted_pdf_path": redacted_key,
        }

    # ------------------------------------------------------------------
    # Redaction Log
    # ------------------------------------------------------------------

    @staticmethod
    async def get_redaction_log(
        db: AsyncSession,
        matter_id: UUID,
        document_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        """Return ``(items, total_count)`` for the redaction log of a document."""
        params: dict = {
            "matter_id": matter_id,
            "document_id": document_id,
            "offset": offset,
            "limit": limit,
        }

        # Total count
        count_result = await db.execute(
            text("""
                SELECT count(*) FROM redactions
                WHERE document_id = :document_id AND matter_id = :matter_id
            """),
            params,
        )
        total = count_result.scalar_one()

        # Paginated rows
        result = await db.execute(
            text(f"""
                SELECT {_LOG_COLUMNS}
                FROM redactions
                WHERE document_id = :document_id AND matter_id = :matter_id
                ORDER BY created_at DESC
                OFFSET :offset
                LIMIT :limit
            """),
            params,
        )
        rows = result.all()
        items = [row_to_dict(r) for r in rows]

        return items, total
