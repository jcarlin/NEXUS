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
from typing import TYPE_CHECKING, Any, TypedDict

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import (
    DatetimeRange,
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


class DateRangeFilter(TypedDict, total=False):
    """Inclusive ISO 8601 date range for ``document_date`` filtering.

    Both bounds are optional. At least one must be provided to have any
    effect. Values must be ISO 8601 strings that Qdrant can parse (e.g.
    ``"2020-01-01T00:00:00+00:00"`` or ``"2020-01-01T00:00:00Z"``).
    """

    gte: str
    lte: str


if TYPE_CHECKING:
    from app.config import Settings

logger = structlog.get_logger(__name__)

# Collection names used throughout the application.
TEXT_COLLECTION = "nexus_text"
VISUAL_COLLECTION = "nexus_visual"


class VectorStoreClient:
    """Thin wrapper around QdrantClient with NEXUS-specific helpers."""

    def __init__(self, settings: Settings) -> None:
        self.client = QdrantClient(
            url=settings.qdrant_url,
            timeout=30,
        )
        self._embedding_dim = settings.embedding_dimensions
        self._enable_visual = settings.enable_visual_embeddings
        self._enable_sparse = settings.enable_sparse_embeddings
        self._enable_multi_repr = settings.enable_multi_representation
        logger.info(
            "qdrant.init",
            url=settings.qdrant_url,
            sparse=self._enable_sparse,
            multi_repr=self._enable_multi_repr,
        )

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
            if self._enable_sparse or self._enable_multi_repr:
                # Named vectors: dense (1024d COSINE) + optional summary + sparse (BM42)
                named_vectors: dict[str, VectorParams] = {
                    "dense": VectorParams(
                        size=self._embedding_dim,
                        distance=Distance.COSINE,
                    ),
                }
                if self._enable_multi_repr:
                    named_vectors["summary"] = VectorParams(
                        size=self._embedding_dim,
                        distance=Distance.COSINE,
                    )
                sparse_config = {"sparse": SparseVectorParams()} if self._enable_sparse else None
                create_kwargs: dict[str, Any] = {
                    "collection_name": TEXT_COLLECTION,
                    "vectors_config": named_vectors,
                }
                if sparse_config:
                    create_kwargs["sparse_vectors_config"] = sparse_config
                self.client.create_collection(**create_kwargs)
                logger.info(
                    "qdrant.collection_created",
                    name=TEXT_COLLECTION,
                    mode="named"
                    + ("+sparse" if self._enable_sparse else "")
                    + ("+summary" if self._enable_multi_repr else ""),
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
            # Upgrade existing collection: add sparse vectors if enabled but missing
            if self._enable_sparse:
                info = self.client.get_collection(TEXT_COLLECTION)
                has_sparse = bool(info.config.params.sparse_vectors and "sparse" in info.config.params.sparse_vectors)
                if not has_sparse:
                    self.client.update_collection(
                        collection_name=TEXT_COLLECTION,
                        sparse_vectors_config={"sparse": SparseVectorParams()},
                    )
                    logger.info(
                        "qdrant.collection_upgraded",
                        name=TEXT_COLLECTION,
                        added="sparse_vectors",
                    )
            # Upgrade: add summary vector if multi-repr enabled but missing
            if self._enable_multi_repr:
                info = self.client.get_collection(TEXT_COLLECTION)
                existing_vectors = info.config.params.vectors
                has_summary = isinstance(existing_vectors, dict) and "summary" in existing_vectors
                if not has_summary:
                    # Need to ensure collection uses named vectors first
                    if isinstance(existing_vectors, dict):
                        self.client.update_collection(
                            collection_name=TEXT_COLLECTION,
                            vectors_config={
                                "summary": VectorParams(
                                    size=self._embedding_dim,
                                    distance=Distance.COSINE,
                                ),
                            },
                        )
                        logger.info(
                            "qdrant.collection_upgraded",
                            name=TEXT_COLLECTION,
                            added="summary_vector",
                        )
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

        # --- Payload indexes for filtered queries ---
        self._ensure_payload_indexes()

    def _ensure_payload_indexes(self) -> None:
        """Create payload indexes for commonly-filtered fields (idempotent)."""
        from qdrant_client.models import PayloadSchemaType

        text_indexes = [
            ("matter_id", PayloadSchemaType.KEYWORD),
            ("doc_id", PayloadSchemaType.KEYWORD),
            ("privilege_status", PayloadSchemaType.KEYWORD),
            ("page_number", PayloadSchemaType.INTEGER),
            ("chunk_index", PayloadSchemaType.INTEGER),
            ("document_date", PayloadSchemaType.DATETIME),
        ]
        for field, schema_type in text_indexes:
            try:
                self.client.create_payload_index(
                    collection_name=TEXT_COLLECTION,
                    field_name=field,
                    field_schema=schema_type,
                )
            except Exception:
                pass  # Index already exists or field not present yet

        if self._enable_visual:
            visual_indexes = [
                ("matter_id", PayloadSchemaType.KEYWORD),
                ("doc_id", PayloadSchemaType.KEYWORD),
                ("page_number", PayloadSchemaType.INTEGER),
            ]
            for field, schema_type in visual_indexes:
                try:
                    self.client.create_payload_index(
                        collection_name=VISUAL_COLLECTION,
                        field_name=field,
                        field_schema=schema_type,
                    )
                except Exception:
                    pass

        logger.info("qdrant.payload_indexes_ensured")

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
          - ``summary_vector`` (optional list[float]) -- summary embedding for multi-repr
        """
        points = []
        for chunk in chunks:
            point_id = chunk.get("id") or str(uuid.uuid4())
            payload = chunk.get("payload", {})
            sparse = chunk.get("sparse_vector")
            summary_vec = chunk.get("summary_vector")

            if self._enable_sparse or self._enable_multi_repr or sparse is not None:
                # Named vector format
                vector: dict[str, Any] = {"dense": chunk["vector"]}
                if sparse is not None:
                    vector["sparse"] = SparseVector(
                        indices=sparse["indices"],
                        values=sparse["values"],
                    )
                if summary_vec is not None and self._enable_multi_repr:
                    vector["summary"] = summary_vec
                points.append(PointStruct(id=point_id, vector=vector, payload=payload))
            else:
                # Unnamed vector (backward compatible)
                points.append(PointStruct(id=point_id, vector=chunk["vector"], payload=payload))

        try:
            self.client.upsert(collection_name=TEXT_COLLECTION, points=points)
        except Exception:
            logger.error(
                "qdrant.upsert_failed",
                collection=TEXT_COLLECTION,
                count=len(points),
                exc_info=True,
            )
            raise
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
        dense_prefetch_multiplier: int | None = None,
        sparse_prefetch_multiplier: int | None = None,
        date_range: DateRangeFilter | None = None,
    ) -> list[dict[str, Any]]:
        """Search ``nexus_text``. Uses RRF fusion when sparse vector is provided.

        Matryoshka dimensionality optimization (T3-15): when enabled, truncates
        query vectors to fewer dimensions for faster approximate search.

        Per-modality prefetch multipliers (T2-9):
        - *dense_prefetch_multiplier*: multiplier for dense prefetch limit.
        - *sparse_prefetch_multiplier*: multiplier for sparse prefetch limit.
        If not provided, falls back to the shared *prefetch_multiplier*.

        *date_range* (optional) restricts results to chunks whose
        ``document_date`` payload falls within the given inclusive ISO
        8601 bounds. Chunks without a ``document_date`` are excluded.
        """
        # Matryoshka dimensionality optimization (T3-15):
        # Truncate query vector to fewer dimensions for faster search.
        from app.dependencies import get_settings

        _settings = get_settings()
        if _settings.matryoshka_search_dimensions > 0 and len(vector) > _settings.matryoshka_search_dimensions:
            vector = vector[: _settings.matryoshka_search_dimensions]

        # Resolve per-modality multipliers (T2-9)
        dense_mult = dense_prefetch_multiplier if dense_prefetch_multiplier is not None else prefetch_multiplier
        sparse_mult = sparse_prefetch_multiplier if sparse_prefetch_multiplier is not None else prefetch_multiplier

        must_conditions: list[FieldCondition] = []
        must_not_conditions: list[FieldCondition] = []

        if filters:
            must_conditions = [FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filters.items()]

        if dataset_doc_ids:
            must_conditions.append(FieldCondition(key="doc_id", match=MatchAny(any=dataset_doc_ids)))

        if date_range:
            must_conditions.append(
                FieldCondition(
                    key="document_date",
                    range=DatetimeRange(
                        gte=date_range.get("gte"),
                        lte=date_range.get("lte"),
                    ),
                )
            )

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
            # Native RRF fusion via prefetch with per-modality multipliers (T2-9)
            sv = SparseVector(indices=sparse_vector[0], values=sparse_vector[1])
            prefetches = [
                Prefetch(query=vector, using="dense", limit=limit * dense_mult, filter=qdrant_filter),
                Prefetch(query=sv, using="sparse", limit=limit * sparse_mult, filter=qdrant_filter),
            ]
            # Multi-representation: add summary vector prefetch for triple RRF
            if self._enable_multi_repr:
                prefetches.append(
                    Prefetch(query=vector, using="summary", limit=limit * dense_mult, filter=qdrant_filter),
                )
            results = self.client.query_points(
                collection_name=TEXT_COLLECTION,
                prefetch=prefetches,
                query=FusionQuery(fusion=Fusion.RRF),
                limit=limit,
                with_payload=True,
            )
        elif self._enable_sparse or self._enable_multi_repr:
            # Named vectors mode — dense-only or with summary prefetch
            if self._enable_multi_repr:
                # RRF between dense and summary
                prefetches = [
                    Prefetch(query=vector, using="dense", limit=limit * prefetch_multiplier, filter=qdrant_filter),
                    Prefetch(query=vector, using="summary", limit=limit * prefetch_multiplier, filter=qdrant_filter),
                ]
                results = self.client.query_points(
                    collection_name=TEXT_COLLECTION,
                    prefetch=prefetches,
                    query=FusionQuery(fusion=Fusion.RRF),
                    limit=limit,
                    with_payload=True,
                )
            else:
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

    def count_points_by_doc_ids(self, doc_ids: list[str]) -> dict[str, int]:
        """Count Qdrant points per doc_id.

        Returns a dict mapping each doc_id to its point count.
        Uses scroll with payload filter to avoid loading vectors.
        """
        if not doc_ids:
            return {}

        counts: dict[str, int] = {did: 0 for did in doc_ids}
        qdrant_filter = Filter(must=[FieldCondition(key="doc_id", match=MatchAny(any=doc_ids))])

        offset = None
        while True:
            results, next_offset = self.client.scroll(
                collection_name=TEXT_COLLECTION,
                scroll_filter=qdrant_filter,
                limit=1000,
                offset=offset,
                with_payload=["doc_id"],
                with_vectors=False,
            )
            for point in results:
                did = (point.payload or {}).get("doc_id")
                if did and did in counts:
                    counts[did] += 1

            if next_offset is None:
                break
            offset = next_offset

        return counts

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
        try:
            self.client.upsert(collection_name=VISUAL_COLLECTION, points=points)
        except Exception:
            logger.error(
                "qdrant.upsert_failed",
                collection=VISUAL_COLLECTION,
                count=len(points),
                exc_info=True,
            )
            raise
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
