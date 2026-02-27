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
    ) -> None:
        self._embedder = embedder
        self._vector_store = vector_store
        self._entity_extractor = entity_extractor
        self._graph_service = graph_service
        self._sparse_embedder = sparse_embedder

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
    ) -> list[dict[str, Any]]:
        """Embed *query* and run dense (+ optional sparse RRF) search against ``nexus_text``."""
        vector = await self._embedder.embed_query(query)

        sparse_vector: tuple[list[int], list[float]] | None = None
        if self._sparse_embedder is not None:
            sparse_vector = self._sparse_embedder.embed_single(query)

        results = await self._vector_store.query_text(
            vector, limit=limit, filters=filters, sparse_vector=sparse_vector,
            exclude_privilege_statuses=exclude_privilege_statuses,
        )
        logger.debug("retriever.text", query_len=len(query), results=len(results), sparse=sparse_vector is not None)
        return results

    # ------------------------------------------------------------------
    # Graph retrieval (Neo4j entity-centric traversal)
    # ------------------------------------------------------------------

    async def retrieve_graph(
        self,
        query: str,
        *,
        limit: int = 20,
        exclude_privilege_statuses: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Extract entities from *query*, then fetch their Neo4j neighbourhoods.

        Returns a deduplicated list of graph connections (source, target,
        relationship_type, edge_properties).
        """
        entities = self.extract_query_entities(query)
        if not entities:
            logger.debug("retriever.graph.no_entities", query=query)
            return []

        # Fetch connections for each detected entity in parallel
        tasks = [
            self._graph_service.get_entity_connections(
                ent.text, limit=limit,
                exclude_privilege_statuses=exclude_privilege_statuses,
            )
            for ent in entities
        ]
        all_connections = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten and deduplicate by (source, target, relationship_type)
        seen: set[tuple[str, str, str]] = set()
        results: list[dict[str, Any]] = []

        for connections in all_connections:
            if isinstance(connections, Exception):
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
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Run text and graph retrieval in parallel.

        Returns:
            Tuple of (text_results, graph_results).
        """
        text_results, graph_results = await asyncio.gather(
            self.retrieve_text(query, limit=text_limit, filters=filters, exclude_privilege_statuses=exclude_privilege_statuses),
            self.retrieve_graph(query, limit=graph_limit, exclude_privilege_statuses=exclude_privilege_statuses),
        )
        return text_results, graph_results

    # ------------------------------------------------------------------
    # Entity extraction helper
    # ------------------------------------------------------------------

    def extract_query_entities(self, query: str) -> list[ExtractedEntity]:
        """Run GLiNER NER on the query with a focused entity type subset.

        Uses a higher threshold (0.5) than ingestion because queries are short
        and we want high-precision entity matches.
        """
        return self._entity_extractor.extract(
            query,
            entity_types=_QUERY_ENTITY_TYPES,
            threshold=0.5,
        )
