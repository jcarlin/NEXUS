"""Hybrid retrieval combining Qdrant vector search and Neo4j graph traversal.

The ``HybridRetriever`` runs text retrieval (dense search via Qdrant) and
graph retrieval (entity-centric via Neo4j) in parallel, then returns both
result sets for downstream reranking and fusion.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from app.common.embedder import EmbeddingProvider
    from app.common.vector_store import VectorStoreClient
    from app.entities.extractor import EntityExtractor, ExtractedEntity
    from app.entities.graph_service import GraphService
    from app.ingestion.sparse_embedder import SparseEmbedder
    from app.ingestion.visual_embedder import VisualEmbedder

logger = structlog.get_logger(__name__)

# Focused entity types for query-time extraction (fewer = faster + less noise)
_QUERY_ENTITY_TYPES = ["person", "organization", "location", "vehicle", "date"]


class HybridRetriever:
    """Combine dense vector search (Qdrant) with knowledge-graph traversal (Neo4j).

    Usage::

        retriever = HybridRetriever(embedder, vector_store, entity_extractor, graph_service)
        text_results, graph_results = await retriever.retrieve_all("Who flew with Epstein?")
    """

    def __init__(
        self,
        embedder: EmbeddingProvider,
        vector_store: VectorStoreClient,
        entity_extractor: EntityExtractor,
        graph_service: GraphService,
        sparse_embedder: SparseEmbedder | None = None,
        visual_embedder: VisualEmbedder | None = None,
    ) -> None:
        self._embedder = embedder
        self._vector_store = vector_store
        self._entity_extractor = entity_extractor
        self._graph_service = graph_service
        self._sparse_embedder = sparse_embedder
        self._visual_embedder = visual_embedder

    # ------------------------------------------------------------------
    # Text retrieval (Qdrant dense search)
    # ------------------------------------------------------------------

    async def retrieve_text(
        self,
        query: str,
        *,
        limit: int = 20,
        filters: dict[str, Any] | None = None,
        exclude_privilege_statuses: list[str] | None = None,
        prefetch_multiplier: int = 2,
        dataset_doc_ids: list[str] | None = None,
        query_vector: list[float] | None = None,
        hyde_vector: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        """Embed *query* and run dense (+ optional sparse RRF) search against ``nexus_text``.

        If *query_vector* is provided, skip the embedding call and use it directly.
        If *hyde_vector* is provided, use it for dense retrieval instead of the
        raw query embedding (HyDE T2-6). The raw query is still used for sparse
        retrieval to preserve lexical matching.
        """
        # Dense vector: prefer HyDE vector > explicit query_vector > embed query
        if hyde_vector is not None:
            vector = hyde_vector
        elif query_vector is not None:
            vector = query_vector
        else:
            vector = await self._embedder.embed_query(query)

        # Sparse vector always uses the raw query for lexical matching
        sparse_vector: tuple[list[int], list[float]] | None = None
        if self._sparse_embedder is not None:
            sparse_vector = self._sparse_embedder.embed_single(query)

        results = await self._vector_store.query_text(
            vector,
            limit=limit,
            filters=filters,
            sparse_vector=sparse_vector,
            exclude_privilege_statuses=exclude_privilege_statuses,
            prefetch_multiplier=prefetch_multiplier,
            dataset_doc_ids=dataset_doc_ids,
        )
        logger.debug("retriever.text", query_len=len(query), results=len(results), sparse=sparse_vector is not None)

        # Deduplicate by near-duplicate cluster (T1-7)
        from app.dependencies import get_settings

        if get_settings().enable_near_duplicate_detection:
            results = self._deduplicate_by_cluster(results)
        return results

    @staticmethod
    def _deduplicate_by_cluster(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove near-duplicate chunks, keeping highest-scored per cluster.

        Chunks with ``duplicate_cluster_id`` in their payload are grouped.
        Within each cluster, the chunk with ``is_final_version=True`` is
        preferred; otherwise the highest-scored chunk wins.  Chunks without
        a cluster ID pass through unchanged.
        """
        clusters: dict[str, list[dict[str, Any]]] = {}
        unclustered: list[dict[str, Any]] = []

        for r in results:
            cluster_id = r.get("duplicate_cluster_id")
            if cluster_id:
                clusters.setdefault(cluster_id, []).append(r)
            else:
                unclustered.append(r)

        if not clusters:
            return results

        deduped: list[dict[str, Any]] = list(unclustered)
        for cluster_chunks in clusters.values():
            # Prefer final version, then highest score
            final = [c for c in cluster_chunks if c.get("is_final_version")]
            best = max(
                final or cluster_chunks,
                key=lambda c: c.get("score", 0),
            )
            deduped.append(best)

        # Re-sort by score descending
        deduped.sort(key=lambda c: c.get("score", 0), reverse=True)

        import structlog as _sl

        _sl.get_logger(__name__).debug(
            "retriever.dedup",
            before=len(results),
            after=len(deduped),
            clusters_removed=len(results) - len(deduped),
        )
        return deduped

    # ------------------------------------------------------------------
    # Graph retrieval (Neo4j entity-centric traversal)
    # ------------------------------------------------------------------

    async def retrieve_graph(
        self,
        query: str,
        *,
        limit: int = 20,
        exclude_privilege_statuses: list[str] | None = None,
        entity_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """Extract entities from *query*, then fetch their Neo4j neighbourhoods.

        Returns a deduplicated list of graph connections (source, target,
        relationship_type, edge_properties).
        """
        entities = self.extract_query_entities(query, entity_threshold=entity_threshold)
        if not entities:
            logger.debug("retriever.graph.no_entities", query=query)
            return []

        # Fetch connections for each detected entity in parallel
        tasks = [
            self._graph_service.get_entity_connections(
                ent.text,
                limit=limit,
                exclude_privilege_statuses=exclude_privilege_statuses,
            )
            for ent in entities
        ]
        all_connections = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten and deduplicate by (source, target, relationship_type)
        seen: set[tuple[str, str, str]] = set()
        results: list[dict[str, Any]] = []

        for connections in all_connections:
            if isinstance(connections, BaseException):
                logger.warning("retriever.graph.entity_error", error=str(connections))
                continue
            for conn in connections:
                key = (
                    str(conn.get("source", "")),
                    str(conn.get("target", "")),
                    str(conn.get("relationship_type", "")),
                )
                if key not in seen:
                    seen.add(key)
                    results.append(conn)

        logger.debug(
            "retriever.graph",
            entities_found=len(entities),
            connections=len(results),
        )
        return results[:limit]

    # ------------------------------------------------------------------
    # Combined retrieval
    # ------------------------------------------------------------------

    async def retrieve_all(
        self,
        query: str,
        *,
        text_limit: int = 20,
        graph_limit: int = 20,
        filters: dict[str, Any] | None = None,
        exclude_privilege_statuses: list[str] | None = None,
        prefetch_multiplier: int = 2,
        entity_threshold: float | None = None,
        dataset_doc_ids: list[str] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Run text and graph retrieval in parallel.

        Returns:
            Tuple of (text_results, graph_results).
        """
        text_results, graph_results = await asyncio.gather(
            self.retrieve_text(
                query,
                limit=text_limit,
                filters=filters,
                exclude_privilege_statuses=exclude_privilege_statuses,
                prefetch_multiplier=prefetch_multiplier,
                dataset_doc_ids=dataset_doc_ids,
            ),
            self.retrieve_graph(
                query,
                limit=graph_limit,
                exclude_privilege_statuses=exclude_privilege_statuses,
                entity_threshold=entity_threshold,
            ),
        )
        return text_results, graph_results

    # ------------------------------------------------------------------
    # Entity extraction helper
    # ------------------------------------------------------------------

    def extract_query_entities(
        self,
        query: str,
        *,
        entity_threshold: float | None = None,
    ) -> list[ExtractedEntity]:
        """Run GLiNER NER on the query with a focused entity type subset.

        Uses a higher threshold than ingestion because queries are short
        and we want high-precision entity matches. Defaults to 0.5 unless
        *entity_threshold* is explicitly provided.
        """
        threshold = entity_threshold if entity_threshold is not None else 0.5
        return self._entity_extractor.extract(
            query,
            entity_types=_QUERY_ENTITY_TYPES,
            threshold=threshold,
        )

    # ------------------------------------------------------------------
    # Visual reranking
    # ------------------------------------------------------------------

    async def rerank_visual(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        *,
        weight: float = 0.3,
        top_n: int = 20,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Rerank candidates by blending text scores with visual MaxSim scores.

        For each candidate, looks up the corresponding page's visual embedding
        in ``nexus_visual`` and computes a blended score:
        ``(1 - weight) * text_score + weight * visual_score``.

        Candidates without visual embeddings keep their original score.

        Args:
            query: The user query text.
            candidates: Text retrieval results with ``score``, ``doc_id``, ``page_number``.
            weight: Visual score blend factor (0.0 = text only, 1.0 = visual only).
            top_n: Number of results to return after reranking.
            filters: Optional payload filters (e.g. matter_id).

        Returns:
            Reranked candidate list sorted by blended score.
        """
        if self._visual_embedder is None or not candidates:
            return candidates[:top_n]

        # Embed query as multi-vector (CPU-bound, offload to thread)
        query_vectors = await asyncio.to_thread(self._visual_embedder.embed_query, query)

        # Look up visual embeddings for each candidate's page
        for candidate in candidates:
            doc_id = candidate.get("doc_id", "")
            page_num = candidate.get("page_number", 1)

            try:
                # Query for this specific page's visual embedding
                visual_results = await self._vector_store.query_visual(
                    query_vectors=query_vectors,
                    limit=1,
                    filters={"doc_id": doc_id, "page_number": page_num, **(filters or {})},
                )

                if visual_results:
                    visual_score = visual_results[0].get("score", 0.0)
                    text_score = candidate.get("score", 0.0)
                    candidate["visual_score"] = visual_score
                    candidate["score"] = (1 - weight) * text_score + weight * visual_score
                    candidate["_visual_reranked"] = True
            except Exception:
                logger.debug("retriever.visual_rerank.page_miss", doc_id=doc_id, page=page_num)

        # Re-sort by blended score
        reranked = sorted(candidates, key=lambda r: r.get("score", 0), reverse=True)
        logger.debug(
            "retriever.visual_rerank",
            candidates=len(candidates),
            reranked_count=len(reranked[:top_n]),
        )
        return reranked[:top_n]
