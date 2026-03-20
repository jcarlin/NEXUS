"""Neo4j knowledge graph operations.

Manages :Document, :Entity, :Chunk, :Email, and :Topic nodes with typed
relationships.  Uses ``MERGE`` for idempotent entity creation (exact-name
dedup) so the same pipeline step can safely be retried.

M11 enhancements: dual-label entities, email-as-node, temporal relationships,
topic/alias edges, communication/reporting chain queries, path-finding.
"""

from __future__ import annotations

from typing import Any

import structlog
from neo4j import AsyncDriver

from app.entities.schema import TEMPORAL_RELATIONSHIP_TYPES, get_neo4j_label

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

    @staticmethod
    def _serialize_value(val: Any) -> Any:
        """Convert Neo4j temporal types to ISO-8601 strings for JSON."""
        try:
            from neo4j.time import DateTime as Neo4jDateTime

            if isinstance(val, Neo4jDateTime):
                return val.iso_format()
        except ImportError:
            pass
        return val

    async def _run_query(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a Cypher query and return all result records as dicts."""
        async with self._driver.session() as session:
            result = await session.run(query, params or {})
            records = await result.data()
            return [{k: self._serialize_value(v) for k, v in rec.items()} for rec in records]

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
        matter_id: str | None = None,
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
            d.matter_id  = $matter_id,
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
                    "matter_id": matter_id,
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
        matter_id: str | None = None,
    ) -> None:
        """Create (or merge) an ``:Entity`` node and link it to a document.

        The ``MERGE`` is keyed on ``(name, type)`` so that duplicate mentions
        across chunks / documents converge on a single node.  A
        ``MENTIONED_IN`` relationship is always created to the target document.

        M11: Applies a typed secondary label (e.g. ``:Person``) when a mapping
        exists in ``ENTITY_TYPE_TO_LABEL``, and stores ``matter_id``.
        """
        # Build secondary label clause (e.g. "SET e:Person")
        label = get_neo4j_label(entity_type)
        label_clause = f"SET e:{label}" if label else ""

        query = f"""
        MERGE (e:Entity {{name: $name, type: $entity_type, matter_id: $matter_id}})
        ON CREATE SET e.first_seen     = datetime(),
                      e.mention_count  = 1
        ON MATCH  SET e.mention_count  = e.mention_count + 1,
                      e.last_seen      = datetime()
        {label_clause}
        WITH e
        MATCH (d:Document {{id: $doc_id}})
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
                    "matter_id": matter_id,
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
        matter_id: str | None = None,
    ) -> int:
        """Bulk-create entity nodes and ``MENTIONED_IN`` relationships.

        Each dict in *entities* must contain ``name``, ``type``, and
        optionally ``page_number``.

        M11: Groups entities by type and applies dual labels (e.g.
        ``:Entity:Person``) in per-type batches.

        Returns:
            The number of entities processed (created or merged).
        """
        if not entities:
            return 0

        # Group by type so we can apply the correct secondary label per batch
        by_type: dict[str, list[dict[str, Any]]] = {}
        for ent in entities:
            by_type.setdefault(ent["type"], []).append(ent)

        total = 0
        for etype, batch in by_type.items():
            label = get_neo4j_label(etype)
            label_clause = f"SET e:{label}" if label else ""

            query = f"""
            UNWIND $entities AS ent
            MERGE (e:Entity {{name: ent.name, type: ent.type, matter_id: $matter_id}})
            ON CREATE SET e.first_seen     = datetime(),
                          e.mention_count  = 1
            ON MATCH  SET e.mention_count  = e.mention_count + 1,
                          e.last_seen      = datetime()
            {label_clause}
            WITH e, ent
            MATCH (d:Document {{id: $doc_id}})
            MERGE (e)-[r:MENTIONED_IN]->(d)
            SET r.page_number = ent.page_number
            """
            try:
                await self._run_write(
                    query,
                    {"doc_id": doc_id, "entities": batch, "matter_id": matter_id},
                )
                total += len(batch)
            except Exception:
                logger.error(
                    "graph.entities.index_failed",
                    doc_id=doc_id,
                    entity_type=etype,
                    count=len(batch),
                )
                raise

        logger.info(
            "graph.entities.indexed",
            doc_id=doc_id,
            count=total,
        )
        return total

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

    async def update_document_privilege(
        self,
        doc_id: str,
        privilege_status: str,
    ) -> None:
        """Set the ``privilege_status`` property on a ``:Document`` node."""
        query = """
        MATCH (d:Document {id: $doc_id})
        SET d.privilege_status = $privilege_status
        """
        try:
            await self._run_write(
                query,
                {"doc_id": doc_id, "privilege_status": privilege_status},
            )
            logger.info(
                "graph.document.privilege_updated",
                doc_id=doc_id,
                privilege_status=privilege_status,
            )
        except Exception:
            logger.error(
                "graph.document.privilege_update_failed",
                doc_id=doc_id,
            )
            raise

    async def get_entity_connections(
        self,
        entity_name: str,
        *,
        limit: int = 50,
        exclude_privilege_statuses: list[str] | None = None,
        matter_id: str | None = None,
        entity_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Return the graph neighbourhood for a named entity.

        Traverses one hop outward and returns connected entities together
        with the relationship type and any context stored on the edge.

        When *exclude_privilege_statuses* is provided, connections to
        Document nodes with those privilege statuses are filtered out.
        """
        where_clauses: list[str] = []
        params: dict[str, Any] = {"name": entity_name, "limit": limit}

        if matter_id:
            where_clauses.append("e.matter_id = $matter_id")
            params["matter_id"] = matter_id

        if exclude_privilege_statuses:
            where_clauses.append(
                "(NOT connected:Document "
                "OR connected.privilege_status IS NULL "
                "OR NOT connected.privilege_status IN $excluded_statuses)"
            )
            params["excluded_statuses"] = exclude_privilege_statuses

        where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        connected_pattern = "(connected:Entity)" if entity_only else "(connected)"

        query = f"""
        MATCH (e:Entity {{name: $name}})-[r]-{connected_pattern}
        {where_clause}
        RETURN e.name           AS source,
               type(r)          AS relationship_type,
               COALESCE(connected.name, connected.filename, connected.chunk_id) AS target,
               labels(connected) AS target_labels,
               properties(r)   AS edge_properties
        LIMIT $limit
        """
        try:
            records = await self._run_query(query, params)
            # Filter out nodes without a displayable name (COALESCE returned None)
            records = [r for r in records if r.get("target") is not None]
            logger.debug(
                "graph.entity_connections.fetched",
                entity=entity_name,
                count=len(records),
            )
            return records
        except Exception:
            logger.error("graph.entity_connections.failed", entity=entity_name)
            raise

    # ------------------------------------------------------------------
    # Entity resolution & search operations (M3)
    # ------------------------------------------------------------------

    async def get_all_entities_by_type(
        self,
        entity_type: str,
        matter_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return all entities of a given type, optionally scoped by matter."""
        matter_filter = " AND e.matter_id = $matter_id" if matter_id else ""
        query = f"""
        MATCH (e:Entity {{type: $entity_type}})
        WHERE true{matter_filter}
        RETURN e.name AS name, e.type AS type, e.mention_count AS mention_count
        ORDER BY e.mention_count DESC
        """
        try:
            records = await self._run_query(query, {"entity_type": entity_type, "matter_id": matter_id})
            logger.debug(
                "graph.entities_by_type.fetched",
                entity_type=entity_type,
                count=len(records),
            )
            return records
        except Exception:
            logger.error("graph.entities_by_type.failed", entity_type=entity_type)
            raise

    async def merge_entities(
        self,
        canonical_name: str,
        alias_name: str,
        entity_type: str,
        matter_id: str,
    ) -> None:
        """Merge two entity nodes, keeping the canonical name.

        Transfers all relationships from the alias to the canonical node,
        adds the alias to the canonical's aliases list, sums mention counts,
        and deletes the alias node.
        """
        query = """
        MATCH (canonical:Entity {name: $canonical_name, type: $entity_type, matter_id: $matter_id})
        MATCH (alias:Entity {name: $alias_name, type: $entity_type, matter_id: $matter_id})
        WHERE canonical <> alias

        // Transfer MENTIONED_IN relationships
        WITH canonical, alias
        OPTIONAL MATCH (alias)-[r:MENTIONED_IN]->(d:Document)
        WITH canonical, alias, collect(d) AS docs, collect(r) AS rels
        FOREACH (d IN docs |
            MERGE (canonical)-[:MENTIONED_IN]->(d)
        )
        FOREACH (r IN rels | DELETE r)

        // Update canonical: add alias, sum mention counts
        WITH canonical, alias
        SET canonical.mention_count = coalesce(canonical.mention_count, 0) + coalesce(alias.mention_count, 0),
            canonical.aliases = coalesce(canonical.aliases, []) + [$alias_name]

        // Delete alias node and its remaining relationships
        WITH alias
        DETACH DELETE alias
        """
        try:
            await self._run_write(
                query,
                {
                    "canonical_name": canonical_name,
                    "alias_name": alias_name,
                    "entity_type": entity_type,
                    "matter_id": matter_id,
                },
            )
            logger.info(
                "graph.entity.merged",
                canonical=canonical_name,
                alias=alias_name,
                type=entity_type,
            )
        except Exception:
            logger.error(
                "graph.entity.merge_failed",
                canonical=canonical_name,
                alias=alias_name,
            )
            raise

    async def search_entities(
        self,
        query: str | None = None,
        entity_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
        matter_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Search entities with optional text query and type filter.

        Returns (items, total_count).
        """
        where_clauses: list[str] = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}

        if matter_id:
            where_clauses.append("e.matter_id = $matter_id")
            params["matter_id"] = matter_id

        if query:
            where_clauses.append("toLower(e.name) CONTAINS toLower($query)")
            params["query"] = query

        if entity_type:
            where_clauses.append("e.type = $entity_type")
            params["entity_type"] = entity_type

        where_str = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        count_cypher = f"""
        MATCH (e:Entity) {where_str}
        RETURN count(e) AS total
        """
        data_cypher = f"""
        MATCH (e:Entity) {where_str}
        RETURN e.name AS id, e.name AS name, e.type AS type,
               e.mention_count AS mention_count,
               e.first_seen AS first_seen, e.last_seen AS last_seen,
               coalesce(e.aliases, []) AS aliases
        ORDER BY e.mention_count DESC
        SKIP $offset LIMIT $limit
        """
        try:
            count_records = await self._run_query(count_cypher, params)
            total = count_records[0]["total"] if count_records else 0

            records = await self._run_query(data_cypher, params)
            logger.debug(
                "graph.search_entities.fetched",
                total=total,
                returned=len(records),
            )
            return records, total
        except Exception:
            logger.error("graph.search_entities.failed")
            raise

    async def get_entity_by_name(
        self,
        name: str,
        entity_type: str | None = None,
        matter_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Look up a single entity by name (and optionally type)."""
        where_clauses = ["e.name = $name"]
        params: dict[str, Any] = {"name": name}

        if entity_type:
            where_clauses.append("e.type = $entity_type")
            params["entity_type"] = entity_type

        if matter_id:
            where_clauses.append("e.matter_id = $matter_id")
            params["matter_id"] = matter_id

        where_str = "WHERE " + " AND ".join(where_clauses)
        cypher = f"""
            MATCH (e:Entity) {where_str}
            RETURN e.name AS id, e.name AS name, e.type AS type,
                   e.mention_count AS mention_count,
                   e.first_seen AS first_seen, e.last_seen AS last_seen,
                   coalesce(e.aliases, []) AS aliases
            LIMIT 1
            """

        try:
            records = await self._run_query(cypher, params)
            if records:
                return records[0]
            return None
        except Exception:
            logger.error("graph.get_entity_by_name.failed", name=name)
            raise

    async def get_entity_timeline(
        self,
        entity_name: str,
        matter_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return chronological events / document mentions for an entity."""
        where_clause = ""
        params: dict[str, Any] = {"name": entity_name}
        if matter_id:
            where_clause = "WHERE e.matter_id = $matter_id"
            params["matter_id"] = matter_id

        cypher = f"""
        MATCH (e:Entity {{name: $name}})-[r:MENTIONED_IN]->(d:Document)
        {where_clause}
        OPTIONAL MATCH (other:Entity)-[:MENTIONED_IN]->(d)
        WHERE other.name <> $name
        WITH d, r, collect(DISTINCT other.name)[..5] AS co_entities
        RETURN d.filename AS document,
               d.type AS document_type,
               r.page_number AS page_number,
               d.created_at AS date,
               co_entities
        ORDER BY d.created_at
        """
        try:
            records = await self._run_query(cypher, params)
            # Map raw Neo4j records to TimelineEvent-compatible dicts
            events = []
            for r in records:
                filename = r.get("document", "Unknown document")
                page = r.get("page_number")
                doc_type = r.get("document_type", "")
                desc = f"Mentioned in {filename}"
                if page is not None:
                    desc += f" (page {page})"
                if doc_type:
                    desc += f" [{doc_type}]"
                events.append(
                    {
                        "date": r.get("date"),
                        "description": desc,
                        "entities": r.get("co_entities", []),
                        "document_source": filename,
                    }
                )
            logger.debug(
                "graph.entity_timeline.fetched",
                entity=entity_name,
                events=len(events),
            )
            return events
        except Exception:
            logger.error("graph.entity_timeline.failed", entity=entity_name)
            raise

    async def create_relationships(
        self,
        doc_id: str,
        relationships: list[dict[str, Any]],
    ) -> int:
        """Create relationship edges between entities for a document.

        Each dict in *relationships* should have:
        - source_entity, source_type, target_entity, target_type
        - relationship_type, context, confidence, temporal
        """
        if not relationships:
            return 0

        query = """
        UNWIND $rels AS rel
        MATCH (src:Entity {name: rel.source_entity, type: rel.source_type})
        MATCH (tgt:Entity {name: rel.target_entity, type: rel.target_type})
        MERGE (src)-[r:RELATED_TO {type: rel.relationship_type}]->(tgt)
        SET r.context = rel.context,
            r.confidence = rel.confidence,
            r.temporal = rel.temporal,
            r.doc_id = $doc_id
        """
        try:
            await self._run_write(
                query,
                {"doc_id": doc_id, "rels": relationships},
            )
            logger.info(
                "graph.relationships.created",
                doc_id=doc_id,
                count=len(relationships),
            )
            return len(relationships)
        except Exception:
            logger.error(
                "graph.relationships.create_failed",
                doc_id=doc_id,
                count=len(relationships),
            )
            raise

    # ------------------------------------------------------------------
    # Email-as-node modeling (M11)
    # ------------------------------------------------------------------

    async def create_email_node(
        self,
        email_id: str,
        subject: str,
        date: str | None,
        message_id: str | None,
        doc_id: str,
        matter_id: str | None = None,
    ) -> None:
        """Create an ``:Email`` node linked to its source ``:Document`` via ``SOURCED_FROM``."""
        query = """
        MERGE (em:Email {id: $email_id})
        SET em.subject    = $subject,
            em.date       = $date,
            em.message_id = $message_id,
            em.matter_id  = $matter_id
        WITH em
        MATCH (d:Document {id: $doc_id})
        MERGE (em)-[:SOURCED_FROM]->(d)
        """
        try:
            await self._run_write(
                query,
                {
                    "email_id": email_id,
                    "subject": subject,
                    "date": date,
                    "message_id": message_id,
                    "doc_id": doc_id,
                    "matter_id": matter_id,
                },
            )
            logger.info("graph.email.created", email_id=email_id, doc_id=doc_id)
        except Exception:
            logger.error("graph.email.create_failed", email_id=email_id)
            raise

    async def link_email_participants(
        self,
        email_id: str,
        sender: tuple[str, str] | None,
        to: list[tuple[str, str]] | None = None,
        cc: list[tuple[str, str]] | None = None,
        bcc: list[tuple[str, str]] | None = None,
        matter_id: str | None = None,
    ) -> None:
        """Create ``:Person`` nodes and ``SENT`` / ``SENT_TO`` / ``CC`` / ``BCC`` edges.

        Each participant is a ``(display_name, email_address)`` tuple.
        The person node is keyed on the email address for dedup.
        """

        async def _link(name: str, addr: str, rel_type: str) -> None:
            display = name or addr.split("@")[0]
            query = f"""
            MERGE (p:Entity:Person {{name: $display, type: 'person', matter_id: $matter_id}})
            ON CREATE SET p.first_seen = datetime(),
                          p.mention_count = 1,
                          p.email_address = $addr
            ON MATCH  SET p.mention_count = p.mention_count + 1,
                          p.email_address = coalesce(p.email_address, $addr)
            WITH p
            MATCH (em:Email {{id: $email_id}})
            MERGE (p)-[:{rel_type}]->(em)
            """
            await self._run_write(
                query,
                {
                    "display": display,
                    "addr": addr,
                    "email_id": email_id,
                    "matter_id": matter_id,
                },
            )

        try:
            if sender:
                await _link(sender[0], sender[1], "SENT")

            for recip_list, rel_type in [
                (to or [], "SENT_TO"),
                (cc or [], "CC"),
                (bcc or [], "BCC"),
            ]:
                for name, addr in recip_list:
                    await _link(name, addr, rel_type)

            logger.info("graph.email.participants_linked", email_id=email_id)
        except Exception:
            logger.error("graph.email.participants_link_failed", email_id=email_id)
            raise

    # ------------------------------------------------------------------
    # Temporal relationships (M11)
    # ------------------------------------------------------------------

    async def create_temporal_relationship(
        self,
        source_name: str,
        target_name: str,
        rel_type: str,
        since: str | None = None,
        until: str | None = None,
        matter_id: str | None = None,
    ) -> None:
        """Create a time-bounded relationship between two entities.

        Only allowlisted relationship types are accepted:
        ``MANAGES``, ``HAS_ROLE``, ``MEMBER_OF``, ``BOARD_MEMBER``, ``REPORTS_TO``.
        """
        if rel_type not in TEMPORAL_RELATIONSHIP_TYPES:
            raise ValueError(
                f"Invalid temporal relationship type: {rel_type}. Allowed: {sorted(TEMPORAL_RELATIONSHIP_TYPES)}"
            )

        query = f"""
        MATCH (src:Entity {{name: $source}})
        MATCH (tgt:Entity {{name: $target}})
        MERGE (src)-[r:{rel_type}]->(tgt)
        SET r.since     = $since,
            r.until     = $until,
            r.matter_id = $matter_id
        """
        try:
            await self._run_write(
                query,
                {
                    "source": source_name,
                    "target": target_name,
                    "since": since,
                    "until": until,
                    "matter_id": matter_id,
                },
            )
            logger.info(
                "graph.temporal_rel.created",
                source=source_name,
                target=target_name,
                rel_type=rel_type,
            )
        except Exception:
            logger.error(
                "graph.temporal_rel.create_failed",
                source=source_name,
                target=target_name,
            )
            raise

    # ------------------------------------------------------------------
    # Advanced graph queries (M11)
    # ------------------------------------------------------------------

    async def get_communication_pairs(
        self,
        person_a: str,
        person_b: str,
        date_from: str | None = None,
        date_to: str | None = None,
        matter_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return all emails exchanged between two people (bidirectional).

        Traverses ``SENT`` / ``SENT_TO`` / ``CC`` / ``BCC`` edges through
        ``:Email`` nodes.
        """
        date_filter = ""
        if date_from:
            date_filter += " AND em.date >= $date_from"
        if date_to:
            date_filter += " AND em.date <= $date_to"

        matter_filter = " AND em.matter_id = $matter_id" if matter_id else ""

        query = f"""
        MATCH (a:Entity {{name: $person_a}})-[:SENT|SENT_TO|CC|BCC]->(em:Email)
        WITH a, em
        MATCH (b:Entity {{name: $person_b}})-[:SENT|SENT_TO|CC|BCC]->(em)
        WHERE a <> b{date_filter}{matter_filter}
        RETURN DISTINCT em.id AS email_id,
               em.subject AS subject,
               em.date AS date,
               em.message_id AS message_id
        ORDER BY em.date
        """
        try:
            records = await self._run_query(
                query,
                {
                    "person_a": person_a,
                    "person_b": person_b,
                    "date_from": date_from,
                    "date_to": date_to,
                    "matter_id": matter_id,
                },
            )
            logger.debug(
                "graph.communication_pairs.fetched",
                person_a=person_a,
                person_b=person_b,
                count=len(records),
            )
            return records
        except Exception:
            logger.error(
                "graph.communication_pairs.failed",
                person_a=person_a,
                person_b=person_b,
            )
            raise

    async def get_reporting_chain(
        self,
        person: str,
        date: str | None = None,
        matter_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return the ``REPORTS_TO`` chain for a person (up to 10 hops).

        Optionally filters by point-in-time (``since <= date <= until``).
        """
        date_filter = ""
        if date:
            date_filter = " AND (r.since IS NULL OR r.since <= $date) AND (r.until IS NULL OR r.until >= $date)"

        matter_filter = " AND p.matter_id = $matter_id" if matter_id else ""

        query = f"""
        MATCH path = (start:Entity {{name: $person}})-[:REPORTS_TO*1..10]->(manager:Entity)
        WHERE ALL(r IN relationships(path) WHERE true{date_filter})
        AND ALL(p IN nodes(path) WHERE true{matter_filter})
        RETURN [n IN nodes(path) | n.name] AS chain,
               length(path) AS depth
        ORDER BY depth
        """
        try:
            records = await self._run_query(
                query,
                {"person": person, "date": date, "matter_id": matter_id},
            )
            logger.debug(
                "graph.reporting_chain.fetched",
                person=person,
                chains=len(records),
            )
            return records
        except Exception:
            logger.error("graph.reporting_chain.failed", person=person)
            raise

    async def find_path(
        self,
        entity_a: str,
        entity_b: str,
        max_hops: int = 5,
        relationship_types: list[str] | None = None,
        matter_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find the shortest path between two entities.

        Parameters
        ----------
        relationship_types:
            Optional filter — only traverse these edge types.
        """
        rel_pattern = "|".join(relationship_types) if relationship_types else ""
        rel_spec = f"[:{rel_pattern}*1..{max_hops}]" if rel_pattern else f"[*1..{max_hops}]"

        matter_filter = ""
        if matter_id:
            matter_filter = " AND ALL(n IN nodes(p) WHERE n.matter_id IS NULL OR n.matter_id = $matter_id)"

        query = f"""
        MATCH (a:Entity {{name: $entity_a}}), (b:Entity {{name: $entity_b}})
        MATCH p = shortestPath((a)-{rel_spec}-(b))
        WHERE a <> b{matter_filter}
        RETURN [n IN nodes(p) | n.name] AS nodes,
               [r IN relationships(p) | type(r)] AS relationships,
               length(p) AS hops
        """
        try:
            records = await self._run_query(
                query,
                {
                    "entity_a": entity_a,
                    "entity_b": entity_b,
                    "matter_id": matter_id,
                },
            )
            logger.debug(
                "graph.find_path.fetched",
                entity_a=entity_a,
                entity_b=entity_b,
                paths=len(records),
            )
            return records
        except Exception:
            logger.error(
                "graph.find_path.failed",
                entity_a=entity_a,
                entity_b=entity_b,
            )
            raise

    # ------------------------------------------------------------------
    # Topic / alias / batch operations (M11)
    # ------------------------------------------------------------------

    async def create_topic_node(
        self,
        topic_name: str,
        matter_id: str | None = None,
    ) -> None:
        """Create (or merge) a ``:Topic`` node."""
        query = """
        MERGE (t:Topic {name: $name, matter_id: $matter_id})
        ON CREATE SET t.created_at = datetime()
        """
        try:
            await self._run_write(
                query,
                {"name": topic_name, "matter_id": matter_id},
            )
            logger.debug("graph.topic.created", topic=topic_name)
        except Exception:
            logger.error("graph.topic.create_failed", topic=topic_name)
            raise

    async def create_discusses_edge(
        self,
        source_id: str,
        source_label: str,
        topic_name: str,
        matter_id: str | None = None,
    ) -> None:
        """Create a ``DISCUSSES`` edge from an Email or Document to a Topic.

        Parameters
        ----------
        source_label:
            ``"Email"`` or ``"Document"``.
        """
        if source_label not in ("Email", "Document"):
            raise ValueError(f"source_label must be 'Email' or 'Document', got '{source_label}'")

        query = f"""
        MATCH (src:{source_label} {{id: $source_id}})
        MERGE (t:Topic {{name: $topic_name, matter_id: $matter_id}})
        ON CREATE SET t.created_at = datetime()
        MERGE (src)-[:DISCUSSES]->(t)
        """
        try:
            await self._run_write(
                query,
                {
                    "source_id": source_id,
                    "topic_name": topic_name,
                    "matter_id": matter_id,
                },
            )
            logger.debug(
                "graph.discusses.created",
                source_id=source_id,
                topic=topic_name,
            )
        except Exception:
            logger.error(
                "graph.discusses.create_failed",
                source_id=source_id,
                topic=topic_name,
            )
            raise

    async def create_alias_edge(
        self,
        term: str,
        canonical_name: str,
        entity_type: str,
        matter_id: str | None = None,
    ) -> None:
        """Create an ``ALIAS_OF`` edge from a defined term to its canonical entity.

        Bridges M9b case-intelligence defined terms to graph entity nodes.
        """
        query = """
        MERGE (alias:Entity {name: $term, type: $entity_type, matter_id: $matter_id})
        ON CREATE SET alias.first_seen = datetime(),
                      alias.mention_count = 0
        WITH alias
        MATCH (canonical:Entity {name: $canonical_name, type: $entity_type, matter_id: $matter_id})
        MERGE (alias)-[:ALIAS_OF]->(canonical)
        """
        try:
            await self._run_write(
                query,
                {
                    "term": term,
                    "canonical_name": canonical_name,
                    "entity_type": entity_type,
                    "matter_id": matter_id,
                },
            )
            logger.debug(
                "graph.alias.created",
                term=term,
                canonical=canonical_name,
            )
        except Exception:
            logger.error(
                "graph.alias.create_failed",
                term=term,
                canonical=canonical_name,
            )
            raise

    async def repair_entity_matter_ids(self) -> int:
        """Backfill ``matter_id`` on entities that are missing it.

        Infers the correct ``matter_id`` from linked ``Document`` nodes via
        the ``MENTIONED_IN`` relationship.  Returns the number of entities
        updated.
        """
        query = """
        MATCH (e:Entity)-[:MENTIONED_IN]->(d:Document)
        WHERE e.matter_id IS NULL AND d.matter_id IS NOT NULL
        WITH e, collect(DISTINCT d.matter_id)[0] AS inferred
        SET e.matter_id = inferred
        RETURN count(e) AS updated
        """
        try:
            records = await self._run_query(query)
            updated = records[0]["updated"] if records else 0
            logger.info("graph.repair_matter_ids.complete", updated=updated)
            return updated
        except Exception:
            logger.error("graph.repair_matter_ids.failed")
            raise

    async def get_entities_by_names(
        self,
        names: list[str],
        matter_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Batch-fetch entities by name for Qdrant <-> Neo4j cross-reference.

        Returns entity nodes matching any of the provided names, optionally
        filtered by ``matter_id``.
        """
        if not names:
            return []

        matter_filter = " AND e.matter_id = $matter_id" if matter_id else ""
        query = f"""
        MATCH (e:Entity)
        WHERE e.name IN $names{matter_filter}
        RETURN e.name AS name,
               e.type AS type,
               e.mention_count AS mention_count,
               labels(e) AS labels,
               coalesce(e.aliases, []) AS aliases
        """
        try:
            records = await self._run_query(
                query,
                {"names": names, "matter_id": matter_id},
            )
            logger.debug(
                "graph.entities_by_names.fetched",
                requested=len(names),
                found=len(records),
            )
            return records
        except Exception:
            logger.error("graph.entities_by_names.failed", count=len(names))
            raise

    async def mark_pending_merge(
        self,
        entity_name: str,
        entity_type: str,
        merge_candidates: list[dict],
        matter_id: str | None = None,
    ) -> None:
        """Flag an entity for manual merge review.

        Sets ``pending_merge = true`` and stores the candidate list as a
        JSON-encoded property on the Entity node.
        """
        import json as _json

        query = """
        MATCH (e:Entity {name: $name, type: $entity_type})
        SET e.pending_merge = true,
            e.merge_candidates = $candidates
        """
        try:
            await self._run_write(
                query,
                {
                    "name": entity_name,
                    "entity_type": entity_type,
                    "candidates": _json.dumps(merge_candidates),
                },
            )
            logger.info(
                "graph.entity.marked_pending_merge",
                entity=entity_name,
                candidates=len(merge_candidates),
            )
        except Exception:
            logger.error(
                "graph.entity.mark_pending_merge_failed",
                entity=entity_name,
            )
            raise

    # ------------------------------------------------------------------
    # Graph statistics
    # ------------------------------------------------------------------

    async def get_graph_stats(self, matter_id: str | None = None) -> dict[str, Any]:
        """Return aggregate node and edge counts for the knowledge graph."""
        if matter_id:
            node_query = """
            MATCH (n) WHERE n.matter_id = $matter_id
            RETURN labels(n)[0] AS label, count(n) AS count
            """
            edge_query = """
            MATCH (a)-[r]->(b)
            WHERE a.matter_id = $matter_id OR b.matter_id = $matter_id
            RETURN type(r) AS type, count(r) AS count
            """
            params: dict[str, Any] = {"matter_id": matter_id}
        else:
            node_query = """
            MATCH (n)
            RETURN labels(n)[0] AS label, count(n) AS count
            """
            edge_query = """
            MATCH ()-[r]->()
            RETURN type(r) AS type, count(r) AS count
            """
            params = {}
        try:
            node_records = await self._run_query(node_query, params)
            edge_records = await self._run_query(edge_query, params)

            node_counts: dict[str, int] = {rec["label"]: rec["count"] for rec in node_records}
            edge_counts: dict[str, int] = {rec["type"]: rec["count"] for rec in edge_records}
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

    # ------------------------------------------------------------------
    # Centrality analysis (GDS)
    # ------------------------------------------------------------------

    async def compute_centrality(
        self,
        matter_id: str,
        metric: str,
    ) -> list[dict[str, Any]]:
        """Compute a centrality metric for entities within a matter using Neo4j GDS.

        Creates a temporary GDS graph projection scoped to the matter, runs
        the requested algorithm, returns ranked results, and drops the
        projection.  Pre-M11 fallback: projects over ``MENTIONED_IN`` +
        ``RELATED_TO`` edges (co-occurrence centrality).

        Parameters
        ----------
        matter_id:
            Scope the projection to entities belonging to this matter.
        metric:
            One of ``"degree"``, ``"pagerank"``, or ``"betweenness"``.

        Returns
        -------
        list[dict[str, Any]]
            Dicts with keys ``name``, ``type``, ``score`` sorted by score
            descending.
        """
        allowed_metrics = {"degree", "pagerank", "betweenness"}
        if metric not in allowed_metrics:
            raise ValueError(f"Invalid centrality metric: {metric}. Allowed: {sorted(allowed_metrics)}")

        graph_name = f"centrality_{matter_id}_{metric}"

        # GDS algorithm procedure names
        algorithm_map = {
            "degree": "gds.degree.stream",
            "pagerank": "gds.pageRank.stream",
            "betweenness": "gds.betweenness.stream",
        }

        logger.info(
            "graph.centrality.start",
            matter_id=matter_id,
            metric=metric,
            graph_name=graph_name,
        )

        try:
            # 1. Create a GDS graph projection scoped to the matter.
            #    Include Entity nodes where matter_id matches OR is NULL,
            #    and project MENTIONED_IN + RELATED_TO edges for
            #    co-occurrence centrality.
            project_query = """
            CALL gds.graph.project(
                $graph_name,
                {
                    Entity: {
                        label: 'Entity',
                        properties: ['name', 'type'],
                        filter: 'WHERE n.matter_id = $matter_id OR n.matter_id IS NULL'
                    }
                },
                {
                    MENTIONED_IN: {
                        type: 'MENTIONED_IN',
                        orientation: 'UNDIRECTED'
                    },
                    RELATED_TO: {
                        type: 'RELATED_TO',
                        orientation: 'UNDIRECTED'
                    }
                }
            )
            """
            await self._run_write(
                project_query,
                {"graph_name": graph_name, "matter_id": matter_id},
            )
            logger.debug(
                "graph.centrality.projected",
                graph_name=graph_name,
            )

            # 2. Run the appropriate GDS algorithm.
            algo_proc = algorithm_map[metric]
            stream_query = f"""
            CALL {algo_proc}($graph_name)
            YIELD nodeId, score
            RETURN gds.util.asNode(nodeId).name AS name,
                   gds.util.asNode(nodeId).type AS type,
                   score
            ORDER BY score DESC
            """
            records = await self._run_query(
                stream_query,
                {"graph_name": graph_name},
            )

            logger.info(
                "graph.centrality.complete",
                matter_id=matter_id,
                metric=metric,
                result_count=len(records),
            )
            return records

        except Exception:
            logger.error(
                "graph.centrality.failed",
                matter_id=matter_id,
                metric=metric,
                graph_name=graph_name,
            )
            raise
        finally:
            # 3. Always drop the projection to avoid leaking memory.
            try:
                drop_query = "CALL gds.graph.drop($graph_name)"
                await self._run_write(drop_query, {"graph_name": graph_name})
                logger.debug(
                    "graph.centrality.projection_dropped",
                    graph_name=graph_name,
                )
            except Exception:
                logger.warning(
                    "graph.centrality.projection_drop_failed",
                    graph_name=graph_name,
                )

    # ------------------------------------------------------------------
    # T1-2: Execute arbitrary read-only Cypher (text-to-Cypher)
    # ------------------------------------------------------------------

    async def execute_read_only(
        self,
        cypher: str,
        params: dict[str, Any],
        *,
        matter_id: str = "",
        timeout: float = 10.0,
    ) -> list[dict[str, Any]]:
        """Execute a read-only Cypher query with safety checks.

        Args:
            cypher: The Cypher query string (must be read-only).
            params: Query parameters (matter_id is always injected).
            matter_id: Matter scope (injected into params if not present).
            timeout: Max execution time in seconds.

        Returns:
            List of result records as dicts.

        Raises:
            ValueError: If the query contains write operations.
        """
        import re

        # Final safety check: reject write operations
        write_ops = re.compile(
            r"\b(CREATE|SET|MERGE|DELETE|REMOVE|DROP|DETACH|CALL\s+\{)\b",
            re.IGNORECASE,
        )
        if write_ops.search(cypher):
            raise ValueError("Write operations are not allowed in read-only queries")

        # Ensure matter_id is in params
        if matter_id:
            params["matter_id"] = matter_id

        logger.info("graph.execute_read_only", cypher=cypher[:200], params_keys=list(params.keys()))

        async with self._driver.session() as session:
            result = await session.run(cypher, params, timeout=timeout)
            records = []
            async for record in result:
                row = {}
                for key in record.keys():
                    row[key] = self._serialize_value(record[key])
                records.append(row)
            return records

    # ------------------------------------------------------------------
    # Interactive graph editing (T3-5)
    # ------------------------------------------------------------------

    async def rename_entity(
        self,
        matter_id: str,
        old_name: str,
        new_name: str,
    ) -> dict[str, Any] | None:
        """Rename an entity node. Returns updated entity or None if not found."""
        entity = await self.get_entity_by_name(old_name, matter_id=matter_id)
        if entity is None:
            return None

        query = """
        MATCH (e:Entity {name: $old_name, matter_id: $matter_id})
        SET e.name = $new_name
        RETURN e.name AS id, e.name AS name, e.type AS type,
               e.mention_count AS mention_count,
               coalesce(e.aliases, []) AS aliases
        """
        try:
            records = await self._run_query(
                query,
                {"old_name": old_name, "new_name": new_name, "matter_id": matter_id},
            )
            logger.info(
                "graph.entity.renamed",
                old_name=old_name,
                new_name=new_name,
                matter_id=matter_id,
            )
            return records[0] if records else None
        except Exception:
            logger.error(
                "graph.entity.rename_failed",
                old_name=old_name,
                new_name=new_name,
                matter_id=matter_id,
            )
            raise

    async def update_entity_type(
        self,
        matter_id: str,
        name: str,
        new_type: str,
    ) -> dict[str, Any] | None:
        """Update the type property of an entity. Returns updated entity or None."""
        entity = await self.get_entity_by_name(name, matter_id=matter_id)
        if entity is None:
            return None

        label = get_neo4j_label(new_type)
        label_clause = f"SET e:{label}" if label else ""

        query = f"""
        MATCH (e:Entity {{name: $name, matter_id: $matter_id}})
        SET e.type = $new_type
        {label_clause}
        RETURN e.name AS id, e.name AS name, e.type AS type,
               e.mention_count AS mention_count,
               coalesce(e.aliases, []) AS aliases
        """
        try:
            records = await self._run_query(
                query,
                {"name": name, "new_type": new_type, "matter_id": matter_id},
            )
            logger.info(
                "graph.entity.type_updated",
                name=name,
                new_type=new_type,
                matter_id=matter_id,
            )
            return records[0] if records else None
        except Exception:
            logger.error(
                "graph.entity.type_update_failed",
                name=name,
                new_type=new_type,
                matter_id=matter_id,
            )
            raise

    async def delete_entity(
        self,
        matter_id: str,
        name: str,
    ) -> bool:
        """Delete an entity and all its relationships. Returns True if found."""
        entity = await self.get_entity_by_name(name, matter_id=matter_id)
        if entity is None:
            return False

        query = """
        MATCH (e:Entity {name: $name, matter_id: $matter_id})
        DETACH DELETE e
        """
        try:
            await self._run_write(
                query,
                {"name": name, "matter_id": matter_id},
            )
            logger.info(
                "graph.entity.deleted",
                name=name,
                matter_id=matter_id,
            )
            return True
        except Exception:
            logger.error(
                "graph.entity.delete_failed",
                name=name,
                matter_id=matter_id,
            )
            raise

    async def delete_relationship(
        self,
        matter_id: str,
        source_name: str,
        target_name: str,
        relationship_type: str,
    ) -> bool:
        """Delete a specific relationship between two entities.

        Returns True if the relationship was found and deleted.
        """
        source = await self.get_entity_by_name(source_name, matter_id=matter_id)
        target = await self.get_entity_by_name(target_name, matter_id=matter_id)
        if source is None or target is None:
            return False

        query = """
        MATCH (src:Entity {name: $source_name, matter_id: $matter_id})
              -[r:RELATED_TO {type: $rel_type}]->
              (tgt:Entity {name: $target_name, matter_id: $matter_id})
        DELETE r
        """
        try:
            await self._run_write(
                query,
                {
                    "source_name": source_name,
                    "target_name": target_name,
                    "rel_type": relationship_type,
                    "matter_id": matter_id,
                },
            )
            logger.info(
                "graph.relationship.deleted",
                source=source_name,
                target=target_name,
                type=relationship_type,
                matter_id=matter_id,
            )
            return True
        except Exception:
            logger.error(
                "graph.relationship.delete_failed",
                source=source_name,
                target=target_name,
                type=relationship_type,
                matter_id=matter_id,
            )
            raise

    async def create_relationship(
        self,
        matter_id: str,
        source_name: str,
        target_name: str,
        relationship_type: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Create a relationship between two entities.

        Returns relationship info or None if either entity is not found.
        """
        source = await self.get_entity_by_name(source_name, matter_id=matter_id)
        target = await self.get_entity_by_name(target_name, matter_id=matter_id)
        if source is None or target is None:
            return None

        props = properties or {}

        query = """
        MATCH (src:Entity {name: $source_name, matter_id: $matter_id})
        MATCH (tgt:Entity {name: $target_name, matter_id: $matter_id})
        MERGE (src)-[r:RELATED_TO {type: $rel_type}]->(tgt)
        SET r += $props
        RETURN src.name AS source, tgt.name AS target, r.type AS relationship_type
        """
        try:
            records = await self._run_query(
                query,
                {
                    "source_name": source_name,
                    "target_name": target_name,
                    "rel_type": relationship_type,
                    "props": props,
                    "matter_id": matter_id,
                },
            )
            logger.info(
                "graph.relationship.created",
                source=source_name,
                target=target_name,
                type=relationship_type,
                matter_id=matter_id,
            )
            return records[0] if records else None
        except Exception:
            logger.error(
                "graph.relationship.create_failed",
                source=source_name,
                target=target_name,
                type=relationship_type,
                matter_id=matter_id,
            )
            raise
