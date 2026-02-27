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
    MatchValue,
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
                logger.info("qdrant.collection_created", name=TEXT_COLLECTION, mode="dense-only", dim=self._embedding_dim)
        else:
            logger.info("qdrant.collection_exists", name=TEXT_COLLECTION)

        # --- Visual collection (placeholder, created only when feature flag is on) ---
        if self._enable_visual and VISUAL_COLLECTION not in existing:
            self.client.create_collection(
                collection_name=VISUAL_COLLECTION,
                vectors_config=VectorParams(
                    size=128,  # ColQwen2.5 patch embedding dimensionality
                    distance=Distance.COSINE,
                ),
            )
            logger.info("qdrant.collection_created", name=VISUAL_COLLECTION, dim=128)
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
            points=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            ),
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
    ) -> list[dict[str, Any]]:
        """Search ``nexus_text``. Uses RRF fusion when sparse vector is provided."""
        must_conditions: list[FieldCondition] = []
        must_not_conditions: list[FieldCondition] = []

        if filters:
            must_conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filters.items()
            ]

        if exclude_privilege_statuses:
            for status in exclude_privilege_statuses:
                must_not_conditions.append(
                    FieldCondition(key="privilege_status", match=MatchValue(value=status))
                )

        qdrant_filter: Filter | None = None
        if must_conditions or must_not_conditions:
            qdrant_filter = Filter(
                must=must_conditions or None,
                must_not=must_not_conditions or None,
            )

        if sparse_vector is not None and self._enable_sparse:
            # Native RRF fusion via prefetch
            sv = SparseVector(indices=sparse_vector[0], values=sparse_vector[1])
            results = self.client.query_points(
                collection_name=TEXT_COLLECTION,
                prefetch=[
                    Prefetch(query=vector, using="dense", limit=limit * 2, filter=qdrant_filter),
                    Prefetch(query=sv, using="sparse", limit=limit * 2, filter=qdrant_filter),
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
                **point.payload,
            }
            for point in results.points
        ]

    async def get_collection_info(self, name: str) -> dict[str, Any]:
        """Return basic stats about the named collection."""
        info = self.client.get_collection(collection_name=name)
        return {
            "name": name,
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
            "status": info.status.value,
        }
