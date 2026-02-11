"""Qdrant vector store wrapper.

Manages two collections:
  * ``nexus_text``   -- 1024-dim dense vectors (BGE-M3 / OpenAI embeddings)
  * ``nexus_visual`` -- placeholder for ColQwen2.5 multi-vector (deferred)
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
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
        logger.info("qdrant.init", url=settings.qdrant_url)

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    async def ensure_collections(self) -> None:
        """Create required collections if they do not already exist.

        Qdrant's Python client is synchronous for management operations,
        so these are plain (non-async) calls.
        """
        existing = {c.name for c in self.client.get_collections().collections}

        # --- Text collection (dense only for now; sparse added in Phase 2) ---
        if TEXT_COLLECTION not in existing:
            self.client.create_collection(
                collection_name=TEXT_COLLECTION,
                vectors_config=VectorParams(
                    size=self._embedding_dim,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("qdrant.collection_created", name=TEXT_COLLECTION, dim=self._embedding_dim)
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
          - ``vector``  (list[float])
          - ``payload`` (dict) -- arbitrary metadata stored alongside the vector
        """
        points = [
            PointStruct(
                id=chunk.get("id") or str(uuid.uuid4()),
                vector=chunk["vector"],
                payload=chunk.get("payload", {}),
            )
            for chunk in chunks
        ]
        self.client.upsert(collection_name=TEXT_COLLECTION, points=points)
        logger.info("qdrant.upsert", collection=TEXT_COLLECTION, count=len(points))

    async def query_text(
        self,
        vector: list[float],
        limit: int = 15,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Dense vector search against ``nexus_text``. Returns scored payloads."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        qdrant_filter: Filter | None = None
        if filters:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filters.items()
            ]
            qdrant_filter = Filter(must=conditions)

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
