"""Dataset service — CRUD, tree operations, document assignment, tags, access control."""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.schemas import (
    DatasetAccessResponse,
    DatasetAccessRole,
    DatasetResponse,
    DatasetTreeNode,
    TagResponse,
)

logger = structlog.get_logger(__name__)

# Maximum folder nesting depth enforced at service layer.
MAX_TREE_DEPTH = 5


class DatasetService:
    """Static methods for dataset and collection operations."""

    # ------------------------------------------------------------------
    # Dataset CRUD
    # ------------------------------------------------------------------

    @staticmethod
    async def create_dataset(
        db: AsyncSession,
        *,
        name: str,
        description: str,
        parent_id: UUID | None,
        matter_id: UUID,
        created_by: UUID,
    ) -> DatasetResponse:
        # Enforce tree depth limit when parent is specified.
        if parent_id is not None:
            depth = await DatasetService._get_depth(db, parent_id)
            if depth >= MAX_TREE_DEPTH:
                raise ValueError(f"Maximum folder depth of {MAX_TREE_DEPTH} exceeded")

            # Verify parent belongs to same matter.
            parent_row = await db.execute(
                text("SELECT matter_id FROM datasets WHERE id = :pid"),
                {"pid": parent_id},
            )
            parent = parent_row.mappings().first()
            if parent is None:
                raise ValueError("Parent dataset not found")
            if parent["matter_id"] != matter_id:
                raise ValueError("Parent dataset belongs to a different matter")

        if parent_id is None:
            # Root-level: partial unique index uq_datasets_matter_name_root
            # covers (matter_id, name) WHERE parent_id IS NULL
            result = await db.execute(
                text("""
                    INSERT INTO datasets (name, description, parent_id, matter_id, created_by)
                    VALUES (:name, :description, NULL, :matter_id, :created_by)
                    ON CONFLICT (matter_id, name) WHERE parent_id IS NULL
                    DO UPDATE SET updated_at = now()
                    RETURNING id, matter_id, name, description, parent_id, created_by, created_at, updated_at
                """),
                {
                    "name": name,
                    "description": description,
                    "matter_id": matter_id,
                    "created_by": created_by,
                },
            )
        else:
            # Non-root: existing constraint uq_datasets_matter_parent_name
            # covers (matter_id, parent_id, name)
            result = await db.execute(
                text("""
                    INSERT INTO datasets (name, description, parent_id, matter_id, created_by)
                    VALUES (:name, :description, :parent_id, :matter_id, :created_by)
                    ON CONFLICT ON CONSTRAINT uq_datasets_matter_parent_name
                    DO UPDATE SET updated_at = now()
                    RETURNING id, matter_id, name, description, parent_id, created_by, created_at, updated_at
                """),
                {
                    "name": name,
                    "description": description,
                    "parent_id": parent_id,
                    "matter_id": matter_id,
                    "created_by": created_by,
                },
            )
        row = result.mappings().one()

        # Get current counts for the returned dataset
        counts = await db.execute(
            text("""
                SELECT
                    (SELECT count(*) FROM dataset_documents dd WHERE dd.dataset_id = :id) AS document_count,
                    (SELECT count(*) FROM datasets c WHERE c.parent_id = :id) AS children_count
            """),
            {"id": row["id"]},
        )
        count_row = counts.mappings().one()
        return DatasetResponse(
            **dict(row), document_count=count_row["document_count"], children_count=count_row["children_count"]
        )

    @staticmethod
    async def get_dataset(
        db: AsyncSession,
        dataset_id: UUID,
        matter_id: UUID,
    ) -> DatasetResponse | None:
        result = await db.execute(
            text("""
                SELECT d.id, d.matter_id, d.name, d.description, d.parent_id,
                       d.created_by, d.created_at, d.updated_at,
                       (SELECT count(*) FROM dataset_documents dd WHERE dd.dataset_id = d.id) AS document_count,
                       (SELECT count(*) FROM datasets c WHERE c.parent_id = d.id) AS children_count
                FROM datasets d
                WHERE d.id = :dataset_id AND d.matter_id = :matter_id
            """),
            {"dataset_id": dataset_id, "matter_id": matter_id},
        )
        row = result.mappings().first()
        if row is None:
            return None
        return DatasetResponse(**dict(row))

    @staticmethod
    async def list_datasets(
        db: AsyncSession,
        matter_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[DatasetResponse], int]:
        count_result = await db.execute(
            text("SELECT count(*) FROM datasets WHERE matter_id = :matter_id"),
            {"matter_id": matter_id},
        )
        total = count_result.scalar_one()

        result = await db.execute(
            text("""
                SELECT d.id, d.matter_id, d.name, d.description, d.parent_id,
                       d.created_by, d.created_at, d.updated_at,
                       (SELECT count(*) FROM dataset_documents dd WHERE dd.dataset_id = d.id) AS document_count,
                       (SELECT count(*) FROM datasets c WHERE c.parent_id = d.id) AS children_count
                FROM datasets d
                WHERE d.matter_id = :matter_id
                ORDER BY d.name ASC
                OFFSET :offset LIMIT :limit
            """),
            {"matter_id": matter_id, "offset": offset, "limit": limit},
        )
        rows = result.mappings().all()
        items = [DatasetResponse(**dict(r)) for r in rows]
        return items, total

    @staticmethod
    async def update_dataset(
        db: AsyncSession,
        dataset_id: UUID,
        matter_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        parent_id: UUID | None = ...,  # type: ignore[assignment]
    ) -> DatasetResponse | None:
        # Check dataset exists.
        existing = await DatasetService.get_dataset(db, dataset_id, matter_id)
        if existing is None:
            return None

        set_clauses: list[str] = ["updated_at = now()"]
        params: dict = {"dataset_id": dataset_id, "matter_id": matter_id}

        if name is not None:
            set_clauses.append("name = :name")
            params["name"] = name

        if description is not None:
            set_clauses.append("description = :description")
            params["description"] = description

        if parent_id is not ...:
            # Validate the move.
            if parent_id is not None:
                # Prevent circular reference.
                if parent_id == dataset_id:
                    raise ValueError("Cannot set a dataset as its own parent")
                # Check depth.
                depth = await DatasetService._get_depth(db, parent_id)
                if depth >= MAX_TREE_DEPTH:
                    raise ValueError(f"Maximum folder depth of {MAX_TREE_DEPTH} exceeded")
            set_clauses.append("parent_id = :parent_id")
            params["parent_id"] = parent_id

        result = await db.execute(
            text(f"""
                UPDATE datasets
                SET {", ".join(set_clauses)}
                WHERE id = :dataset_id AND matter_id = :matter_id
                RETURNING id, matter_id, name, description, parent_id, created_by, created_at, updated_at
            """),
            params,
        )
        row = result.mappings().first()
        if row is None:
            return None
        return DatasetResponse(
            **dict(row),
            document_count=existing.document_count,
            children_count=existing.children_count,
        )

    @staticmethod
    async def delete_dataset(
        db: AsyncSession,
        dataset_id: UUID,
        matter_id: UUID,
    ) -> bool:
        result = await db.execute(
            text("DELETE FROM datasets WHERE id = :dataset_id AND matter_id = :matter_id RETURNING id"),
            {"dataset_id": dataset_id, "matter_id": matter_id},
        )
        deleted = result.rowcount > 0
        if deleted:
            logger.info("dataset.deleted", dataset_id=str(dataset_id))
        return deleted

    # ------------------------------------------------------------------
    # Tree operations
    # ------------------------------------------------------------------

    @staticmethod
    async def get_dataset_tree(
        db: AsyncSession,
        matter_id: UUID,
    ) -> tuple[list[DatasetTreeNode], int]:
        """Build the full folder tree for a matter using a recursive CTE."""
        result = await db.execute(
            text("""
                WITH RECURSIVE tree AS (
                    SELECT id, name, description, parent_id, 1 AS depth
                    FROM datasets
                    WHERE matter_id = :matter_id AND parent_id IS NULL
                    UNION ALL
                    SELECT d.id, d.name, d.description, d.parent_id, t.depth + 1
                    FROM datasets d
                    JOIN tree t ON d.parent_id = t.id
                    WHERE t.depth < :max_depth
                )
                SELECT t.id, t.name, t.description, t.parent_id,
                       (SELECT count(*) FROM dataset_documents dd WHERE dd.dataset_id = t.id) AS document_count
                FROM tree t
                ORDER BY t.name ASC
            """),
            {"matter_id": matter_id, "max_depth": MAX_TREE_DEPTH},
        )
        rows = result.mappings().all()

        # Build tree in memory.
        nodes: dict[UUID, DatasetTreeNode] = {}
        children_map: dict[UUID | None, list[UUID]] = {}

        for r in rows:
            node = DatasetTreeNode(
                id=r["id"],
                name=r["name"],
                description=r["description"],
                document_count=r["document_count"],
            )
            nodes[r["id"]] = node
            parent = r["parent_id"]
            children_map.setdefault(parent, []).append(r["id"])

        # Wire children.
        for parent_id, child_ids in children_map.items():
            if parent_id is not None and parent_id in nodes:
                nodes[parent_id].children = [nodes[cid] for cid in child_ids if cid in nodes]

        roots = [nodes[cid] for cid in children_map.get(None, []) if cid in nodes]
        return roots, len(rows)

    @staticmethod
    async def _get_depth(db: AsyncSession, dataset_id: UUID) -> int:
        """Return the depth of a dataset in the folder tree (root = 1)."""
        result = await db.execute(
            text("""
                WITH RECURSIVE ancestors AS (
                    SELECT id, parent_id, 1 AS depth
                    FROM datasets WHERE id = :dataset_id
                    UNION ALL
                    SELECT d.id, d.parent_id, a.depth + 1
                    FROM datasets d
                    JOIN ancestors a ON d.id = a.parent_id
                )
                SELECT max(depth) AS max_depth FROM ancestors
            """),
            {"dataset_id": dataset_id},
        )
        row = result.scalar_one_or_none()
        return row or 0

    # ------------------------------------------------------------------
    # Document assignment
    # ------------------------------------------------------------------

    @staticmethod
    async def assign_documents(
        db: AsyncSession,
        dataset_id: UUID,
        document_ids: list[UUID],
        matter_id: UUID,
        assigned_by: UUID,
    ) -> int:
        """Assign documents to a dataset. Returns count of new assignments."""
        # Verify dataset belongs to matter.
        ds = await DatasetService.get_dataset(db, dataset_id, matter_id)
        if ds is None:
            raise ValueError("Dataset not found")

        count = 0
        for doc_id in document_ids:
            result = await db.execute(
                text("""
                    INSERT INTO dataset_documents (dataset_id, document_id, assigned_by)
                    VALUES (:dataset_id, :document_id, :assigned_by)
                    ON CONFLICT (dataset_id, document_id) DO NOTHING
                """),
                {"dataset_id": dataset_id, "document_id": doc_id, "assigned_by": assigned_by},
            )
            count += result.rowcount
        logger.info("dataset.documents_assigned", dataset_id=str(dataset_id), count=count)
        return count

    @staticmethod
    async def unassign_documents(
        db: AsyncSession,
        dataset_id: UUID,
        document_ids: list[UUID],
        matter_id: UUID,
    ) -> int:
        """Remove documents from a dataset. Returns count of removals."""
        ds = await DatasetService.get_dataset(db, dataset_id, matter_id)
        if ds is None:
            raise ValueError("Dataset not found")

        result = await db.execute(
            text("""
                DELETE FROM dataset_documents
                WHERE dataset_id = :dataset_id
                  AND document_id = ANY(:document_ids)
            """),
            {"dataset_id": dataset_id, "document_ids": list(document_ids)},
        )
        count = result.rowcount
        logger.info("dataset.documents_unassigned", dataset_id=str(dataset_id), count=count)
        return count

    @staticmethod
    async def move_documents(
        db: AsyncSession,
        source_dataset_id: UUID,
        target_dataset_id: UUID,
        document_ids: list[UUID],
        matter_id: UUID,
        assigned_by: UUID,
    ) -> int:
        """Move documents from one dataset to another. Returns count of moves."""
        # Verify both datasets belong to matter.
        for ds_id in (source_dataset_id, target_dataset_id):
            ds = await DatasetService.get_dataset(db, ds_id, matter_id)
            if ds is None:
                raise ValueError(f"Dataset {ds_id} not found")

        # Remove from source.
        await db.execute(
            text("""
                DELETE FROM dataset_documents
                WHERE dataset_id = :source_id AND document_id = ANY(:document_ids)
            """),
            {"source_id": source_dataset_id, "document_ids": list(document_ids)},
        )

        # Add to target.
        count = 0
        for doc_id in document_ids:
            result = await db.execute(
                text("""
                    INSERT INTO dataset_documents (dataset_id, document_id, assigned_by)
                    VALUES (:target_id, :document_id, :assigned_by)
                    ON CONFLICT (dataset_id, document_id) DO NOTHING
                """),
                {"target_id": target_dataset_id, "document_id": doc_id, "assigned_by": assigned_by},
            )
            count += result.rowcount

        logger.info(
            "dataset.documents_moved",
            source=str(source_dataset_id),
            target=str(target_dataset_id),
            count=count,
        )
        return count

    @staticmethod
    async def list_dataset_documents(
        db: AsyncSession,
        dataset_id: UUID,
        matter_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        """List documents assigned to a dataset. Returns (items, total)."""
        ds = await DatasetService.get_dataset(db, dataset_id, matter_id)
        if ds is None:
            raise ValueError("Dataset not found")

        count_result = await db.execute(
            text("SELECT count(*) FROM dataset_documents WHERE dataset_id = :dataset_id"),
            {"dataset_id": dataset_id},
        )
        total = count_result.scalar_one()

        result = await db.execute(
            text("""
                SELECT doc.id, doc.filename, doc.document_type, doc.page_count,
                       doc.chunk_count, doc.entity_count, doc.created_at,
                       doc.minio_path, doc.privilege_status, doc.thread_id,
                       doc.is_inclusive, doc.duplicate_cluster_id,
                       doc.version_group_id, doc.hot_doc_score,
                       dd.assigned_at
                FROM documents doc
                JOIN dataset_documents dd ON dd.document_id = doc.id
                WHERE dd.dataset_id = :dataset_id AND doc.matter_id = :matter_id
                ORDER BY dd.assigned_at DESC
                OFFSET :offset LIMIT :limit
            """),
            {"dataset_id": dataset_id, "matter_id": matter_id, "offset": offset, "limit": limit},
        )
        rows = result.mappings().all()
        items = [dict(r) for r in rows]
        return items, total

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    @staticmethod
    async def add_tag(
        db: AsyncSession,
        document_id: UUID,
        tag_name: str,
        matter_id: UUID,
        created_by: UUID,
    ) -> bool:
        """Add a tag to a document. Returns True if new tag was created."""
        # Verify document belongs to matter.
        doc_check = await db.execute(
            text("SELECT id FROM documents WHERE id = :doc_id AND matter_id = :matter_id"),
            {"doc_id": document_id, "matter_id": matter_id},
        )
        if doc_check.first() is None:
            raise ValueError("Document not found")

        result = await db.execute(
            text("""
                INSERT INTO document_tags (document_id, tag_name, created_by)
                VALUES (:document_id, :tag_name, :created_by)
                ON CONFLICT (document_id, tag_name) DO NOTHING
            """),
            {"document_id": document_id, "tag_name": tag_name, "created_by": created_by},
        )
        return result.rowcount > 0

    @staticmethod
    async def remove_tag(
        db: AsyncSession,
        document_id: UUID,
        tag_name: str,
        matter_id: UUID,
    ) -> bool:
        """Remove a tag from a document. Returns True if tag was removed."""
        result = await db.execute(
            text("""
                DELETE FROM document_tags
                WHERE document_id = :document_id AND tag_name = :tag_name
                  AND document_id IN (SELECT id FROM documents WHERE matter_id = :matter_id)
            """),
            {"document_id": document_id, "tag_name": tag_name, "matter_id": matter_id},
        )
        return result.rowcount > 0

    @staticmethod
    async def list_document_tags(
        db: AsyncSession,
        document_id: UUID,
        matter_id: UUID,
    ) -> list[str]:
        """List all tags on a document."""
        result = await db.execute(
            text("""
                SELECT dt.tag_name
                FROM document_tags dt
                JOIN documents d ON d.id = dt.document_id
                WHERE dt.document_id = :document_id AND d.matter_id = :matter_id
                ORDER BY dt.tag_name ASC
            """),
            {"document_id": document_id, "matter_id": matter_id},
        )
        return [row[0] for row in result.all()]

    @staticmethod
    async def list_all_tags(
        db: AsyncSession,
        matter_id: UUID,
    ) -> list[TagResponse]:
        """List all tags in a matter with document counts (for autocomplete)."""
        result = await db.execute(
            text("""
                SELECT dt.tag_name, count(*) AS document_count
                FROM document_tags dt
                JOIN documents d ON d.id = dt.document_id
                WHERE d.matter_id = :matter_id
                GROUP BY dt.tag_name
                ORDER BY dt.tag_name ASC
            """),
            {"matter_id": matter_id},
        )
        rows = result.mappings().all()
        return [TagResponse(**dict(r)) for r in rows]

    @staticmethod
    async def list_documents_by_tag(
        db: AsyncSession,
        tag_name: str,
        matter_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        """List documents with a specific tag. Returns (items, total)."""
        count_result = await db.execute(
            text("""
                SELECT count(*)
                FROM document_tags dt
                JOIN documents d ON d.id = dt.document_id
                WHERE dt.tag_name = :tag_name AND d.matter_id = :matter_id
            """),
            {"tag_name": tag_name, "matter_id": matter_id},
        )
        total = count_result.scalar_one()

        result = await db.execute(
            text("""
                SELECT d.id, d.filename, d.document_type, d.page_count,
                       d.chunk_count, d.entity_count, d.created_at
                FROM documents d
                JOIN document_tags dt ON dt.document_id = d.id
                WHERE dt.tag_name = :tag_name AND d.matter_id = :matter_id
                ORDER BY d.created_at DESC
                OFFSET :offset LIMIT :limit
            """),
            {"tag_name": tag_name, "matter_id": matter_id, "offset": offset, "limit": limit},
        )
        rows = result.mappings().all()
        items = [dict(r) for r in rows]
        return items, total

    # ------------------------------------------------------------------
    # Access control
    # ------------------------------------------------------------------

    @staticmethod
    async def grant_access(
        db: AsyncSession,
        dataset_id: UUID,
        user_id: UUID,
        access_role: DatasetAccessRole,
        granted_by: UUID,
        matter_id: UUID,
    ) -> DatasetAccessResponse:
        """Grant or update access for a user on a dataset."""
        ds = await DatasetService.get_dataset(db, dataset_id, matter_id)
        if ds is None:
            raise ValueError("Dataset not found")

        result = await db.execute(
            text("""
                INSERT INTO dataset_access (dataset_id, user_id, access_role, granted_by)
                VALUES (:dataset_id, :user_id, :access_role, :granted_by)
                ON CONFLICT (dataset_id, user_id)
                DO UPDATE SET access_role = :access_role, granted_by = :granted_by, granted_at = now()
                RETURNING id, dataset_id, user_id, access_role, granted_by, granted_at
            """),
            {
                "dataset_id": dataset_id,
                "user_id": user_id,
                "access_role": access_role,
                "granted_by": granted_by,
            },
        )
        row = result.mappings().one()
        return DatasetAccessResponse(**dict(row))

    @staticmethod
    async def revoke_access(
        db: AsyncSession,
        dataset_id: UUID,
        user_id: UUID,
        matter_id: UUID,
    ) -> bool:
        """Revoke a user's access to a dataset. Returns True if a row was deleted."""
        ds = await DatasetService.get_dataset(db, dataset_id, matter_id)
        if ds is None:
            raise ValueError("Dataset not found")

        result = await db.execute(
            text("""
                DELETE FROM dataset_access
                WHERE dataset_id = :dataset_id AND user_id = :user_id
            """),
            {"dataset_id": dataset_id, "user_id": user_id},
        )
        return result.rowcount > 0

    @staticmethod
    async def list_access(
        db: AsyncSession,
        dataset_id: UUID,
        matter_id: UUID,
    ) -> list[DatasetAccessResponse]:
        """List all access entries for a dataset."""
        ds = await DatasetService.get_dataset(db, dataset_id, matter_id)
        if ds is None:
            raise ValueError("Dataset not found")

        result = await db.execute(
            text("""
                SELECT id, dataset_id, user_id, access_role, granted_by, granted_at
                FROM dataset_access
                WHERE dataset_id = :dataset_id
                ORDER BY granted_at ASC
            """),
            {"dataset_id": dataset_id},
        )
        rows = result.mappings().all()
        return [DatasetAccessResponse(**dict(r)) for r in rows]

    @staticmethod
    async def check_dataset_access(
        db: AsyncSession,
        dataset_id: UUID,
        user_id: UUID,
        matter_id: UUID,
    ) -> bool:
        """Check if a user has access to a dataset.

        Default-open: if no access rows exist for the dataset, all matter users
        have access. If any rows exist, only listed users have access.
        """
        # Check whether the dataset has any access restrictions.
        has_restrictions = await db.execute(
            text("SELECT 1 FROM dataset_access WHERE dataset_id = :dataset_id LIMIT 1"),
            {"dataset_id": dataset_id},
        )
        if has_restrictions.first() is None:
            # No restrictions — default-open.
            return True

        # Has restrictions — check if user is listed.
        user_access = await db.execute(
            text("""
                SELECT 1 FROM dataset_access
                WHERE dataset_id = :dataset_id AND user_id = :user_id
            """),
            {"dataset_id": dataset_id, "user_id": user_id},
        )
        return user_access.first() is not None

    # ------------------------------------------------------------------
    # Query helper
    # ------------------------------------------------------------------

    @staticmethod
    async def get_document_ids_for_dataset(
        db: AsyncSession,
        dataset_id: UUID,
        matter_id: UUID,
    ) -> list[str]:
        """Resolve a dataset to a list of document IDs for Qdrant filtering.

        Returns documents.id (stored as doc_id in Qdrant payloads).
        """
        result = await db.execute(
            text("""
                SELECT CAST(doc.id AS text) AS doc_id
                FROM documents doc
                JOIN dataset_documents dd ON dd.document_id = doc.id
                WHERE dd.dataset_id = :dataset_id AND doc.matter_id = :matter_id
            """),
            {"dataset_id": dataset_id, "matter_id": matter_id},
        )
        return [row[0] for row in result.all() if row[0] is not None]
