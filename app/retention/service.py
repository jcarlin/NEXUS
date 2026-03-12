"""Retention policy service layer.

Raw SQL CRUD and multi-system purge orchestration.  All queries
are matter-scoped where applicable.
"""

from __future__ import annotations

import csv
import io
import uuid
import zipfile
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class RetentionService:
    """Static methods for retention policy CRUD and purge orchestration."""

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    @staticmethod
    async def create_policy(
        db: AsyncSession,
        matter_id: uuid.UUID,
        retention_days: int,
        user_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Insert a retention policy. Computes purge_scheduled_at."""
        policy_id = str(uuid.uuid4())
        result = await db.execute(
            text("""
                INSERT INTO retention_policies
                    (id, matter_id, retention_days, policy_set_by,
                     purge_scheduled_at, status)
                VALUES
                    (:id, :matter_id, :retention_days, :user_id,
                     NOW() + :retention_days * interval '1 day', 'active')
                RETURNING id, matter_id, retention_days, policy_set_by,
                          policy_set_at, purge_scheduled_at,
                          purge_completed_at, purge_error, archive_path, status
            """),
            {
                "id": policy_id,
                "matter_id": str(matter_id),
                "retention_days": retention_days,
                "user_id": str(user_id),
            },
        )
        row = result.mappings().first()
        return dict(row) if row else {}

    @staticmethod
    async def get_policy(
        db: AsyncSession,
        matter_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        """Fetch retention policy by matter_id."""
        result = await db.execute(
            text("""
                SELECT id, matter_id, retention_days, policy_set_by,
                       policy_set_at, purge_scheduled_at,
                       purge_completed_at, purge_error, archive_path, status
                FROM retention_policies
                WHERE matter_id = :matter_id
            """),
            {"matter_id": str(matter_id)},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    @staticmethod
    async def list_policies(
        db: AsyncSession,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """List all retention policies with pagination."""
        count_result = await db.execute(text("SELECT count(*) FROM retention_policies"))
        total = count_result.scalar() or 0

        result = await db.execute(
            text("""
                SELECT id, matter_id, retention_days, policy_set_by,
                       policy_set_at, purge_scheduled_at,
                       purge_completed_at, purge_error, archive_path, status
                FROM retention_policies
                ORDER BY policy_set_at DESC
                OFFSET :offset LIMIT :limit
            """),
            {"offset": offset, "limit": limit},
        )
        rows = [dict(r) for r in result.mappings().all()]
        return rows, total

    @staticmethod
    async def delete_policy(
        db: AsyncSession,
        matter_id: uuid.UUID,
    ) -> bool:
        """Delete a policy only if status is 'active'."""
        result = await db.execute(
            text("""
                DELETE FROM retention_policies
                WHERE matter_id = :matter_id AND status = 'active'
                RETURNING id
            """),
            {"matter_id": str(matter_id)},
        )
        return result.rowcount > 0

    @staticmethod
    async def get_expired_policies(
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        """Find policies that are active and past their purge date."""
        result = await db.execute(
            text("""
                SELECT id, matter_id, retention_days, policy_set_by,
                       policy_set_at, purge_scheduled_at,
                       purge_completed_at, purge_error, archive_path, status
                FROM retention_policies
                WHERE status = 'active'
                  AND purge_scheduled_at <= NOW()
            """)
        )
        return [dict(r) for r in result.mappings().all()]

    # ------------------------------------------------------------------
    # Purge orchestration
    # ------------------------------------------------------------------

    @staticmethod
    async def _update_status(
        db: AsyncSession,
        matter_id: uuid.UUID,
        status: str,
        error: str | None = None,
        archive_path: str | None = None,
    ) -> None:
        """Update retention policy status."""
        params: dict[str, Any] = {
            "matter_id": str(matter_id),
            "status": status,
            "error": error,
        }
        extra_set = ""
        if archive_path is not None:
            extra_set = ", archive_path = :archive_path"
            params["archive_path"] = archive_path
        if status == "completed":
            extra_set += ", purge_completed_at = NOW()"

        await db.execute(
            text(f"""
                UPDATE retention_policies
                SET status = :status,
                    purge_error = :error
                    {extra_set}
                WHERE matter_id = :matter_id
            """),
            params,
        )

    @staticmethod
    async def _archive_matter(
        db: AsyncSession,
        matter_id: uuid.UUID,
        minio_client: Any,
    ) -> str:
        """Generate privilege log + audit log archive, upload to MinIO.

        Returns the archive path in MinIO.
        """
        # Export privilege log entries
        priv_result = await db.execute(
            text("""
                SELECT id, filename, privilege_status, privilege_basis,
                       created_at
                FROM documents
                WHERE matter_id = :matter_id
                  AND privilege_status IS NOT NULL
                ORDER BY filename
            """),
            {"matter_id": str(matter_id)},
        )
        priv_rows = [dict(r) for r in priv_result.mappings().all()]

        # Export audit log entries
        audit_result = await db.execute(
            text("""
                SELECT id, user_id, action, resource, resource_type,
                       matter_id, ip_address, status_code, created_at
                FROM audit_log
                WHERE matter_id = :matter_id
                ORDER BY created_at
            """),
            {"matter_id": str(matter_id)},
        )
        audit_rows = [dict(r) for r in audit_result.mappings().all()]

        # Build ZIP archive in memory
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # Privilege log CSV
            csv_buf = io.StringIO()
            writer = csv.writer(csv_buf)
            writer.writerow(["id", "filename", "privilege_status", "privilege_basis", "created_at"])
            for row in priv_rows:
                writer.writerow(
                    [
                        str(row["id"]),
                        row["filename"],
                        row.get("privilege_status", ""),
                        row.get("privilege_basis", ""),
                        str(row["created_at"]),
                    ]
                )
            zf.writestr("privilege_log.csv", csv_buf.getvalue())

            # Audit log CSV
            audit_csv_buf = io.StringIO()
            audit_writer = csv.writer(audit_csv_buf)
            audit_writer.writerow(
                [
                    "id",
                    "user_id",
                    "action",
                    "resource",
                    "resource_type",
                    "matter_id",
                    "ip_address",
                    "status_code",
                    "created_at",
                ]
            )
            for row in audit_rows:
                audit_writer.writerow(
                    [
                        str(row["id"]),
                        str(row.get("user_id", "")),
                        row["action"],
                        row["resource"],
                        row.get("resource_type", ""),
                        str(row.get("matter_id", "")),
                        row.get("ip_address", ""),
                        row.get("status_code", ""),
                        str(row["created_at"]),
                    ]
                )
            zf.writestr("audit_log.csv", audit_csv_buf.getvalue())

        archive_bytes = buf.getvalue()
        archive_path = f"archives/{matter_id}/retention_archive.zip"
        await minio_client.upload_bytes(
            key=archive_path,
            data=archive_bytes,
            content_type="application/zip",
        )

        logger.info(
            "retention.archive_uploaded",
            matter_id=str(matter_id),
            archive_path=archive_path,
            size_bytes=len(archive_bytes),
        )
        return archive_path

    @staticmethod
    async def _purge_qdrant(
        matter_id: uuid.UUID,
        qdrant_client: Any,
    ) -> None:
        """Delete all Qdrant points for the matter."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        for collection in ["nexus_text", "nexus_visual"]:
            try:
                qdrant_client.client.delete(
                    collection_name=collection,
                    points_selector=Filter(
                        must=[
                            FieldCondition(
                                key="matter_id",
                                match=MatchValue(value=str(matter_id)),
                            )
                        ]
                    ),
                )
                logger.info("retention.qdrant_purged", matter_id=str(matter_id), collection=collection)
            except Exception:
                # Collection may not exist — idempotent
                logger.warning("retention.qdrant_purge_skipped", matter_id=str(matter_id), collection=collection)

    @staticmethod
    async def _purge_neo4j(
        matter_id: uuid.UUID,
        neo4j_driver: Any,
    ) -> None:
        """Delete all Neo4j nodes for the matter."""
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (n {matter_id: $mid}) DETACH DELETE n",
                {"mid": str(matter_id)},
            )
        logger.info("retention.neo4j_purged", matter_id=str(matter_id))

    @staticmethod
    async def _purge_minio(
        matter_id: uuid.UUID,
        minio_client: Any,
    ) -> None:
        """Delete all MinIO objects for the matter (except archives)."""
        prefixes = [f"raw/{matter_id}/", f"pages/{matter_id}/", f"parsed/{matter_id}/"]
        for prefix in prefixes:
            try:
                objects = await minio_client.list_objects(prefix=prefix)
                for obj in objects:
                    await minio_client.delete_object(key=obj["key"])
            except Exception:
                logger.warning("retention.minio_purge_skipped", matter_id=str(matter_id), prefix=prefix)
        logger.info("retention.minio_purged", matter_id=str(matter_id))

    @staticmethod
    async def _purge_postgresql(
        db: AsyncSession,
        matter_id: uuid.UUID,
    ) -> None:
        """Delete matter data from PostgreSQL in FK order.

        Does NOT delete from audit_log or ai_audit_log (SOC 2 compliance).
        """
        mid = str(matter_id)

        # Annotations (reference documents/chunks)
        await db.execute(
            text("DELETE FROM annotations WHERE matter_id = :mid"),
            {"mid": mid},
        )

        # Chunks (reference documents)
        await db.execute(
            text("""
                DELETE FROM chunks
                WHERE document_id IN (
                    SELECT id FROM documents WHERE matter_id = :mid
                )
            """),
            {"mid": mid},
        )

        # Documents
        await db.execute(
            text("DELETE FROM documents WHERE matter_id = :mid"),
            {"mid": mid},
        )

        # Jobs
        await db.execute(
            text("DELETE FROM jobs WHERE matter_id = :mid"),
            {"mid": mid},
        )

        # Case entities (claims, parties, terms via case_contexts)
        await db.execute(
            text("""
                DELETE FROM case_claims
                WHERE case_context_id IN (
                    SELECT id FROM case_contexts WHERE matter_id = :mid
                )
            """),
            {"mid": mid},
        )
        await db.execute(
            text("""
                DELETE FROM case_parties
                WHERE case_context_id IN (
                    SELECT id FROM case_contexts WHERE matter_id = :mid
                )
            """),
            {"mid": mid},
        )
        await db.execute(
            text("""
                DELETE FROM case_defined_terms
                WHERE case_context_id IN (
                    SELECT id FROM case_contexts WHERE matter_id = :mid
                )
            """),
            {"mid": mid},
        )
        await db.execute(
            text("DELETE FROM case_contexts WHERE matter_id = :mid"),
            {"mid": mid},
        )

        logger.info("retention.postgresql_purged", matter_id=mid)

    @staticmethod
    async def execute_purge(
        db: AsyncSession,
        matter_id: uuid.UUID,
        qdrant_client: Any,
        neo4j_driver: Any,
        minio_client: Any,
    ) -> dict[str, Any]:
        """Orchestrate full matter purge across all data systems.

        Archive-before-purge is mandatory: if archive fails, purge aborts.
        Each per-system purge is idempotent (safe to re-run on partial failure).
        """
        try:
            # Step 1: Archive
            await RetentionService._update_status(db, matter_id, "archiving")
            await db.commit()

            archive_path = await RetentionService._archive_matter(db, matter_id, minio_client)
            await RetentionService._update_status(db, matter_id, "archiving", archive_path=archive_path)
            await db.commit()

        except Exception as exc:
            await db.rollback()
            await RetentionService._update_status(db, matter_id, "failed", error=f"Archive failed: {exc}")
            await db.commit()
            raise

        try:
            # Step 2: Purge across systems
            await RetentionService._update_status(db, matter_id, "purging")
            await db.commit()

            await RetentionService._purge_qdrant(matter_id, qdrant_client)
            await RetentionService._purge_neo4j(matter_id, neo4j_driver)
            await RetentionService._purge_minio(matter_id, minio_client)
            await RetentionService._purge_postgresql(db, matter_id)

            # Step 3: Mark matter as archived
            await db.execute(
                text("UPDATE case_matters SET is_archived = TRUE WHERE id = :mid"),
                {"mid": str(matter_id)},
            )

            # Step 4: Mark completed
            await RetentionService._update_status(db, matter_id, "completed", archive_path=archive_path)
            await db.commit()

            logger.info("retention.purge_completed", matter_id=str(matter_id))
            return {"status": "completed", "archive_path": archive_path}

        except Exception as exc:
            await db.rollback()
            await RetentionService._update_status(db, matter_id, "failed", error=f"Purge failed: {exc}")
            await db.commit()
            raise
