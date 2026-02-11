"""Neo4j knowledge graph operations.

Manages :Document, :Entity, and :Chunk nodes with MENTIONED_IN /
PART_OF relationships.  Uses ``MERGE`` for idempotent entity creation
(exact-name dedup) so the same pipeline step can safely be retried.
"""

from __future__ import annotations

from typing import Any

import structlog
from neo4j import AsyncDriver

logger = structlog.get_logger(__name__)


class GraphService:
    """Thin async wrapper around Neo4j for NEXUS knowledge-graph operations.

    All public methods are async and use the driver's session-per-call
    pattern so callers never need to manage sessions manually.

    Usage::

        from neo4j import AsyncGraphDatabase
        driver = AsyncGraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "pw"))
        gs = GraphService(driver)
        await gs.create_document_node(doc_id="d1", filename="flight_log.pdf", ...)
    """

    def __init__(self, driver: AsyncDriver) -> None:
        self._driver = driver

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_query(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a Cypher query and return all result records as dicts."""
        async with self._driver.session() as session:
            result = await session.run(query, params or {})
            records = await result.data()
            return records

    async def _run_write(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Execute a Cypher write query inside an implicit transaction."""
        async with self._driver.session() as session:
            await session.run(query, params or {})

    # ------------------------------------------------------------------
    # Document nodes
    # ------------------------------------------------------------------

    async def create_document_node(
        self,
        doc_id: str,
        filename: str,
        doc_type: str,
        page_count: int,
        minio_path: str,
    ) -> None:
        """Create (or update) a ``:Document`` node.

        Uses ``MERGE`` on the document id so the call is idempotent.
        """
        query = """
        MERGE (d:Document {id: $doc_id})
        SET d.filename   = $filename,
            d.type       = $doc_type,
            d.page_count = $page_count,
            d.minio_path = $minio_path,
            d.created_at = datetime()
        """
        try:
            await self._run_write(
                query,
                {
                    "doc_id": doc_id,
                    "filename": filename,
                    "doc_type": doc_type,
                    "page_count": page_count,
                    "minio_path": minio_path,
                },
            )
            logger.info(
                "graph.document.created",
                doc_id=doc_id,
                filename=filename,
            )
        except Exception:
            logger.error("graph.document.create_failed", doc_id=doc_id)
            raise

    # ------------------------------------------------------------------
    # Entity nodes
    # ------------------------------------------------------------------

    async def create_entity_node(
        self,
        name: str,
        entity_type: str,
        doc_id: str,
        page_number: int | None = None,
    ) -> None:
        """Create (or merge) an ``:Entity`` node and link it to a document.

        The ``MERGE`` is keyed on ``(name, type)`` so that duplicate mentions
        across chunks / documents converge on a single node.  A
        ``MENTIONED_IN`` relationship is always created to the target document.
        """
        query = """
        MERGE (e:Entity {name: $name, type: $entity_type})
        ON CREATE SET e.first_seen     = datetime(),
                      e.mention_count  = 1
        ON MATCH  SET e.mention_count  = e.mention_count + 1,
                      e.last_seen      = datetime()
        WITH e
        MATCH (d:Document {id: $doc_id})
        MERGE (e)-[r:MENTIONED_IN]->(d)
        SET r.page_number = $page_number
        """
        try:
            await self._run_write(
                query,
                {
                    "name": name,
                    "entity_type": entity_type,
                    "doc_id": doc_id,
                    "page_number": page_number,
                },
            )
            logger.debug(
                "graph.entity.created",
                name=name,
                type=entity_type,
                doc_id=doc_id,
            )
        except Exception:
            logger.error(
                "graph.entity.create_failed",
                name=name,
                type=entity_type,
                doc_id=doc_id,
            )
            raise

    # ------------------------------------------------------------------
    # Chunk nodes
    # ------------------------------------------------------------------

    async def create_chunk_node(
        self,
        chunk_id: str,
        text_preview: str,
        page_number: int,
        qdrant_point_id: str,
        doc_id: str,
    ) -> None:
        """Create a ``:Chunk`` node linked to its parent ``:Document``.

        ``text_preview`` is truncated to 200 characters to keep the graph
        lightweight — full text lives in Qdrant.
        """
        preview = text_preview[:200] if len(text_preview) > 200 else text_preview

        query = """
        CREATE (c:Chunk {
            id:              $chunk_id,
            text_preview:    $text_preview,
            page_number:     $page_number,
            qdrant_point_id: $qdrant_point_id
        })
        WITH c
        MATCH (d:Document {id: $doc_id})
        CREATE (c)-[:PART_OF]->(d)
        """
        try:
            await self._run_write(
                query,
                {
                    "chunk_id": chunk_id,
                    "text_preview": preview,
                    "page_number": page_number,
                    "qdrant_point_id": qdrant_point_id,
                    "doc_id": doc_id,
                },
            )
            logger.debug("graph.chunk.created", chunk_id=chunk_id, doc_id=doc_id)
        except Exception:
            logger.error(
                "graph.chunk.create_failed",
                chunk_id=chunk_id,
                doc_id=doc_id,
            )
            raise

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    async def index_entities_for_document(
        self,
        doc_id: str,
        entities: list[dict[str, Any]],
    ) -> int:
        """Bulk-create entity nodes and ``MENTIONED_IN`` relationships.

        Each dict in *entities* must contain ``name``, ``type``, and
        optionally ``page_number``.

        Returns:
            The number of entities processed (created or merged).
        """
        if not entities:
            return 0

        # Use UNWIND for efficient batch creation in a single Cypher query
        query = """
        UNWIND $entities AS ent
        MERGE (e:Entity {name: ent.name, type: ent.type})
        ON CREATE SET e.first_seen     = datetime(),
                      e.mention_count  = 1
        ON MATCH  SET e.mention_count  = e.mention_count + 1,
                      e.last_seen      = datetime()
        WITH e, ent
        MATCH (d:Document {id: $doc_id})
        MERGE (e)-[r:MENTIONED_IN]->(d)
        SET r.page_number = ent.page_number
        """
        try:
            await self._run_write(query, {"doc_id": doc_id, "entities": entities})
            logger.info(
                "graph.entities.indexed",
                doc_id=doc_id,
                count=len(entities),
            )
            return len(entities)
        except Exception:
            logger.error(
                "graph.entities.index_failed",
                doc_id=doc_id,
                count=len(entities),
            )
            raise

    # ------------------------------------------------------------------
    # Read queries
    # ------------------------------------------------------------------

    async def get_document_entities(self, doc_id: str) -> list[dict[str, Any]]:
        """Return all entities mentioned in *doc_id*, ordered by frequency."""
        query = """
        MATCH (e:Entity)-[r:MENTIONED_IN]->(d:Document {id: $doc_id})
        RETURN e.name          AS name,
               e.type          AS type,
               e.mention_count AS mention_count,
               r.page_number   AS page_number
        ORDER BY e.mention_count DESC
        """
        try:
            records = await self._run_query(query, {"doc_id": doc_id})
            logger.debug(
                "graph.document_entities.fetched",
                doc_id=doc_id,
                count=len(records),
            )
            return records
        except Exception:
            logger.error("graph.document_entities.failed", doc_id=doc_id)
            raise

    async def get_entity_connections(
        self,
        entity_name: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return the graph neighbourhood for a named entity.

        Traverses one hop outward and returns connected entities together
        with the relationship type and any context stored on the edge.
        """
        query = """
        MATCH (e:Entity {name: $name})-[r]-(connected)
        RETURN e.name           AS source,
               type(r)          AS relationship_type,
               connected.name   AS target,
               labels(connected) AS target_labels,
               properties(r)   AS edge_properties
        LIMIT $limit
        """
        try:
            records = await self._run_query(
                query,
                {"name": entity_name, "limit": limit},
            )
            logger.debug(
                "graph.entity_connections.fetched",
                entity=entity_name,
                count=len(records),
            )
            return records
        except Exception:
            logger.error("graph.entity_connections.failed", entity=entity_name)
            raise

    async def get_graph_stats(self) -> dict[str, Any]:
        """Return aggregate node and edge counts for the knowledge graph."""
        node_query = """
        MATCH (n)
        RETURN labels(n)[0] AS label, count(n) AS count
        """
        edge_query = """
        MATCH ()-[r]->()
        RETURN type(r) AS type, count(r) AS count
        """
        try:
            node_records = await self._run_query(node_query)
            edge_records = await self._run_query(edge_query)

            node_counts: dict[str, int] = {
                rec["label"]: rec["count"] for rec in node_records
            }
            edge_counts: dict[str, int] = {
                rec["type"]: rec["count"] for rec in edge_records
            }
            total_nodes = sum(node_counts.values())
            total_edges = sum(edge_counts.values())

            logger.debug(
                "graph.stats.fetched",
                total_nodes=total_nodes,
                total_edges=total_edges,
            )
            return {
                "total_nodes": total_nodes,
                "total_edges": total_edges,
                "node_counts": node_counts,
                "edge_counts": edge_counts,
            }
        except Exception:
            logger.error("graph.stats.failed")
            raise
