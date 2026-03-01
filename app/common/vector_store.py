"""Qdrant vector store wrapper.

Manages two collections:
  * ``nexus_text``   -- dense (1024d) + optional sparse (BM42) named vectors
  * ``nexus_visual`` -- placeholder for ColQwen2.5 multi-vector (deferred)

When ``ENABLE_SPARSE_EMBEDDINGS`` is on, the text collection uses named
vectors (``dense`` + ``sparse``) and queries use native Qdrant RRF fusion
via ``prefetch`` + ``FusionQuery``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    HnswConfigDiff,
    MatchAny,
    MatchValue,
    MultiVectorComparator,
    MultiVectorConfig,
    PointStruct,
    Prefetch,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

if TYPE_CHECKING:
    from app.config import Settings

logger = structlog.get_logger(__name__)

# Collection names used throughout the application.
TEXT_COLLECTION = "nexus_text"
VISUAL_COLLECTION = "nexus_visual"


class VectorStoreClient:
    """Thin wrapper around QdrantClient with NEXUS-specific helpers."""

    def __init__(self, settings: Settings) -> None:
        self.client = QdrantClient(url=settings.qdrant_url)
        self._embedding_dim = settings.embedding_dimensions
        self._enable_visual = settings.enable_visual_embeddings
        self._enable_sparse = settings.enable_sparse_embeddings
        logger.info("qdrant.init", url=settings.qdrant_url, sparse=self._enable_sparse)

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    async def ensure_collections(self) -> None:
        """Create required collections if they do not already exist.

        Qdrant's Python client is synchronous for management operations,
        so these are plain (non-async) calls.
        """
        existing = {c.name for c in self.client.get_collections().collections}

        # --- Text collection ---
        if TEXT_COLLECTION not in existing:
            if self._enable_sparse:
                # Named vectors: dense (1024d COSINE) + sparse (BM42)
                self.client.create_collection(
                    collection_name=TEXT_COLLECTION,
                    vectors_config={
                        "dense": VectorParams(
                            size=self._embedding_dim,
                            distance=Distance.COSINE,
                        ),
                    },
                    sparse_vectors_config={
                        "sparse": SparseVectorParams(),
                    },
                )
                logger.info(
                    "qdrant.collection_created",
                    name=TEXT_COLLECTION,
                    mode="named+sparse",
                    dim=self._embedding_dim,
                )
            else:
                # Unnamed dense vector only (backward compatible)
                self.client.create_collection(
                    collection_name=TEXT_COLLECTION,
                    vectors_config=VectorParams(
                        size=self._embedding_dim,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(
                    "qdrant.collection_created", name=TEXT_COLLECTION, mode="dense-only", dim=self._embedding_dim
                )
        else:
            logger.info("qdrant.collection_exists", name=TEXT_COLLECTION)

        # --- Visual collection (multi-vector MaxSim for ColQwen2.5 reranking) ---
        if self._enable_visual and VISUAL_COLLECTION not in existing:
            self.client.create_collection(
                collection_name=VISUAL_COLLECTION,
                vectors_config=VectorParams(
                    size=128,  # ColQwen2.5 per-token dimension
                    distance=Distance.COSINE,
                    multivector_config=MultiVectorConfig(
                        comparator=MultiVectorComparator.MAX_SIM,
                    ),
                    hnsw_config=HnswConfigDiff(m=0),  # Reranking only, no HNSW index
                ),
            )
            logger.info("qdrant.collection_created", name=VISUAL_COLLECTION, mode="multivector_maxsim", dim=128)
        elif VISUAL_COLLECTION in existing:
            logger.info("qdrant.collection_exists", name=VISUAL_COLLECTION)

    # ------------------------------------------------------------------
    # Text collection CRUD
    # ------------------------------------------------------------------

    async def upsert_text_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """Upsert a batch of text chunks into ``nexus_text``.

        Each dict in *chunks* must contain:
          - ``id``      (str | None) -- point id, auto-generated if missing
          - ``vector``  (list[float]) -- dense embedding
          - ``payload`` (dict) -- arbitrary metadata stored alongside the vector
          - ``sparse_vector`` (optional dict with ``indices`` and ``values``)
        """
        points = []
        for chunk in chunks:
            point_id = chunk.get("id") or str(uuid.uuid4())
            payload = chunk.get("payload", {})
            sparse = chunk.get("sparse_vector")

            if self._enable_sparse or sparse is not None:
                # Named vector format
                vector: dict[str, Any] = {"dense": chunk["vector"]}
                if sparse is not None:
                    vector["sparse"] = SparseVector(
                        indices=sparse["indices"],
                        values=sparse["values"],
                    )
                points.append(PointStruct(id=point_id, vector=vector, payload=payload))
            else:
                # Unnamed vector (backward compatible)
                points.append(PointStruct(id=point_id, vector=chunk["vector"], payload=payload))

        self.client.upsert(collection_name=TEXT_COLLECTION, points=points)
        logger.info("qdrant.upsert", collection=TEXT_COLLECTION, count=len(points))

    async def update_privilege_status(
        self,
        doc_id: str,
        privilege_status: str,
    ) -> None:
        """Batch-update ``privilege_status`` payload on all points for a document.

        Uses ``set_payload`` with a filter on the ``doc_id`` field to update
        all chunks belonging to the document in one call.
        """
        self.client.set_payload(
            collection_name=TEXT_COLLECTION,
            payload={"privilege_status": privilege_status},
            points=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]),
        )
        logger.info(
            "qdrant.privilege_updated",
            doc_id=doc_id,
            privilege_status=privilege_status,
        )

    async def query_text(
        self,
        vector: list[float],
        limit: int = 15,
        filters: dict[str, Any] | None = None,
        sparse_vector: tuple[list[int], list[float]] | None = None,
        exclude_privilege_statuses: list[str] | None = None,
        prefetch_multiplier: int = 2,
        dataset_doc_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search ``nexus_text``. Uses RRF fusion when sparse vector is provided."""
        must_conditions: list[FieldCondition] = []
        must_not_conditions: list[FieldCondition] = []

        if filters:
            must_conditions = [FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filters.items()]

        if dataset_doc_ids:
            must_conditions.append(FieldCondition(key="doc_id", match=MatchAny(any=dataset_doc_ids)))

        if exclude_privilege_statuses:
            for status in exclude_privilege_statuses:
                must_not_conditions.append(FieldCondition(key="privilege_status", match=MatchValue(value=status)))

        qdrant_filter: Filter | None = None
        if must_conditions or must_not_conditions:
            qdrant_filter = Filter(
                must=must_conditions if must_conditions else None,  # type: ignore[arg-type]
                must_not=must_not_conditions if must_not_conditions else None,  # type: ignore[arg-type]
            )

        if sparse_vector is not None and self._enable_sparse:
            # Native RRF fusion via prefetch
            sv = SparseVector(indices=sparse_vector[0], values=sparse_vector[1])
            results = self.client.query_points(
                collection_name=TEXT_COLLECTION,
                prefetch=[
                    Prefetch(query=vector, using="dense", limit=limit * prefetch_multiplier, filter=qdrant_filter),
                    Prefetch(query=sv, using="sparse", limit=limit * prefetch_multiplier, filter=qdrant_filter),
                ],
                query=FusionQuery(fusion=Fusion.RRF),
                limit=limit,
                with_payload=True,
            )
        elif self._enable_sparse:
            # Sparse enabled but no sparse vector — dense-only with named vector
            results = self.client.query_points(
                collection_name=TEXT_COLLECTION,
                query=vector,
                using="dense",
                limit=limit,
                query_filter=qdrant_filter,
                with_payload=True,
            )
        else:
            # Unnamed vector (backward compatible)
            results = self.client.query_points(
                collection_name=TEXT_COLLECTION,
                query=vector,
                limit=limit,
                query_filter=qdrant_filter,
                with_payload=True,
            )

        return [
            {
                "id": str(point.id),
                "score": point.score,
                **(point.payload or {}),
            }
            for point in results.points
        ]

    async def query_text_sparse_only(
        self,
        sparse_vector: tuple[list[int], list[float]],
        limit: int = 15,
        filters: dict[str, Any] | None = None,
        exclude_privilege_statuses: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search ``nexus_text`` using only the sparse vector.

        Mirrors ``query_text()`` but uses only the sparse prefetch path,
        enabling separate measurement of sparse retrieval quality.
        Requires ``ENABLE_SPARSE_EMBEDDINGS=true``.
        """
        if not self._enable_sparse:
            raise RuntimeError("Sparse embeddings are not enabled")

        must_conditions: list[FieldCondition] = []
        must_not_conditions: list[FieldCondition] = []

        if filters:
            must_conditions = [FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filters.items()]

        if exclude_privilege_statuses:
            for status in exclude_privilege_statuses:
                must_not_conditions.append(FieldCondition(key="privilege_status", match=MatchValue(value=status)))

        qdrant_filter: Filter | None = None
        if must_conditions or must_not_conditions:
            qdrant_filter = Filter(
                must=must_conditions if must_conditions else None,  # type: ignore[arg-type]
                must_not=must_not_conditions if must_not_conditions else None,  # type: ignore[arg-type]
            )

        sv = SparseVector(indices=sparse_vector[0], values=sparse_vector[1])
        results = self.client.query_points(
            collection_name=TEXT_COLLECTION,
            query=sv,
            using="sparse",
            limit=limit,
            query_filter=qdrant_filter,
            with_payload=True,
        )

        return [
            {
                "id": str(point.id),
                "score": point.score,
                **(point.payload or {}),
            }
            for point in results.points
        ]

    async def get_collection_info(self, name: str) -> dict[str, Any]:
        """Return basic stats about the named collection."""
        info = self.client.get_collection(collection_name=name)
        return {
            "name": name,
            "points_count": info.points_count,
            "vectors_count": info.indexed_vectors_count,
            "status": info.status.value,
        }

    # ------------------------------------------------------------------
    # Visual collection CRUD
    # ------------------------------------------------------------------

    async def upsert_visual_pages(self, pages: list[dict[str, Any]]) -> None:
        """Upsert page-level multi-vector embeddings into ``nexus_visual``.

        Each dict in *pages* must contain:
          - ``id``        (str) -- point id (typically ``{doc_id}_{page_number}``)
          - ``vectors``   (list[list[float]]) -- multi-vector embedding (patches × 128d)
          - ``payload``   (dict) -- metadata (doc_id, page_number, matter_id, etc.)
        """
        points = [
            PointStruct(
                id=page["id"],
                vector=page["vectors"],
                payload=page.get("payload", {}),
            )
            for page in pages
        ]
        self.client.upsert(collection_name=VISUAL_COLLECTION, points=points)
        logger.info("qdrant.upsert", collection=VISUAL_COLLECTION, count=len(points))

    async def query_visual(
        self,
        query_vectors: list[list[float]],
        limit: int = 20,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Query ``nexus_visual`` with multi-vector MaxSim for reranking.

        Args:
            query_vectors: Query token embeddings (tokens × 128d).
            limit: Maximum results to return.
            filters: Payload filters (e.g. matter_id).

        Returns:
            List of result dicts with ``id``, ``score``, and payload fields.
        """
        must_conditions: list[FieldCondition] = []
        if filters:
            must_conditions = [FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filters.items()]

        qdrant_filter = Filter(must=must_conditions) if must_conditions else None

        results = self.client.query_points(
            collection_name=VISUAL_COLLECTION,
            query=query_vectors,
            limit=limit,
            query_filter=qdrant_filter,
            with_payload=True,
        )

        return [
            {
                "id": str(point.id),
                "score": point.score,
                **(point.payload or {}),
            }
            for point in results.points
        ]

    # ------------------------------------------------------------------
    # HNSW index management (bulk import optimization)
    # ------------------------------------------------------------------

    def disable_hnsw_indexing(self, collection_name: str) -> None:
        """Disable HNSW graph link construction for fast bulk inserts.

        Setting ``m=0`` tells Qdrant to skip building graph links during
        upserts, yielding 5-10x speedup for large batch imports.
        Call ``rebuild_hnsw_index()`` after the import is complete.
        """
        from qdrant_client.models import HnswConfigDiff

        self.client.update_collection(
            collection_name=collection_name,
            hnsw_config=HnswConfigDiff(m=0),
        )
        logger.info("qdrant.hnsw_disabled", collection=collection_name)

    def rebuild_hnsw_index(
        self,
        collection_name: str,
        m: int = 16,
        ef_construct: int = 200,
    ) -> None:
        """Restore HNSW defaults and trigger a background index rebuild.

        Qdrant rebuilds segments in the background after this call returns.
        """
        from qdrant_client.models import HnswConfigDiff

        self.client.update_collection(
            collection_name=collection_name,
            hnsw_config=HnswConfigDiff(m=m, ef_construct=ef_construct),
        )
        logger.info(
            "qdrant.hnsw_rebuild",
            collection=collection_name,
            m=m,
            ef_construct=ef_construct,
        )
