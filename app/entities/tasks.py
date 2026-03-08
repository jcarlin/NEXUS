"""Celery tasks for entity resolution (post-ingestion).

The ``resolve_entities`` task fetches all entities of a given type from
Neo4j, runs fuzzy matching, and merges duplicates.
"""

from __future__ import annotations

import asyncio

import structlog
from celery import shared_task

from workers.celery_app import celery_app  # noqa: F401 — ensures @shared_task binds to our app

logger = structlog.get_logger(__name__)


async def _run_resolution(entity_type: str | None = None, matter_id: str | None = None) -> dict:
    """Async implementation of entity resolution."""
    from neo4j import AsyncGraphDatabase

    from app.config import Settings
    from app.entities.graph_service import GraphService
    from app.entities.resolver import EntityResolver

    settings = Settings()
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

    try:
        gs = GraphService(driver)
        resolver = EntityResolver()

        types_to_process: list[str] = []
        if entity_type:
            types_to_process = [entity_type]
        else:
            # Get all distinct entity types from the graph
            # Entity nodes have a 'type' property — query for distinct types
            records = await gs._run_query("MATCH (e:Entity) RETURN DISTINCT e.type AS type")
            types_to_process = [r["type"] for r in records if r.get("type")]

        total_merges = 0

        for etype in types_to_process:
            entities = await gs.get_all_entities_by_type(etype, matter_id=matter_id)
            if len(entities) < 2:
                continue

            matches = resolver.find_fuzzy_matches(entities)
            if not matches:
                continue

            # Use union-find to compute transitive merge groups
            groups = resolver.compute_merge_groups(matches)

            for group in groups:
                for alias in group.aliases:
                    try:
                        await gs.merge_entities(
                            group.canonical,
                            alias,
                            group.entity_type,
                            matter_id=matter_id,
                        )
                        total_merges += 1
                        logger.info(
                            "resolver.merged",
                            canonical=group.canonical,
                            alias=alias,
                            type=group.entity_type,
                        )
                    except Exception:
                        logger.error(
                            "resolver.merge_failed",
                            canonical=group.canonical,
                            alias=alias,
                        )

        return {
            "merges_performed": total_merges,
            "entity_types_processed": len(types_to_process),
        }
    finally:
        await driver.close()


@shared_task(
    bind=True,
    name="entities.resolve_entities",
    max_retries=1,
    default_retry_delay=60,
    acks_late=True,
)
def resolve_entities(self, entity_type: str | None = None, matter_id: str | None = None) -> dict:
    """Run cross-document entity resolution.

    Fetches entities from Neo4j by type, finds fuzzy matches, and
    executes merges in the knowledge graph.

    Parameters
    ----------
    entity_type:
        Optional — resolve only this entity type. If None, resolves all types.
    matter_id:
        Optional — scope resolution to this matter only.

    Returns
    -------
    Dict with ``merges_performed`` and ``entity_types_processed``.
    """
    logger.info("task.resolve_entities.start", entity_type=entity_type, matter_id=matter_id)

    try:
        result = asyncio.run(_run_resolution(entity_type, matter_id=matter_id))
        logger.info(
            "task.resolve_entities.complete",
            merges=result["merges_performed"],
            types=result["entity_types_processed"],
        )
        return result
    except Exception as exc:
        logger.error("task.resolve_entities.failed", error=str(exc))
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise


@shared_task(
    bind=True,
    name="agents.entity_resolution_agent",
    max_retries=1,
    default_retry_delay=60,
    acks_late=True,
)
def entity_resolution_agent(self, matter_id: str) -> dict:
    """Run the LangGraph entity resolution pipeline.

    Enhanced version of ``resolve_entities`` that also infers org hierarchy,
    links defined terms, and flags uncertain merges for review.

    Parameters
    ----------
    matter_id:
        The matter to resolve entities for.

    Returns
    -------
    Dict with pipeline summary (merges, hierarchy edges, linked terms, etc.).
    """
    logger.info("task.entity_resolution_agent.start", matter_id=matter_id)

    try:
        from app.entities.resolution_agent import run_resolution_agent

        result = asyncio.run(run_resolution_agent(matter_id))
        logger.info("task.entity_resolution_agent.complete", **result)
        return result
    except Exception as exc:
        logger.error("task.entity_resolution_agent.failed", error=str(exc))
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise


@shared_task(
    bind=True,
    name="entities.reprocess_entities_to_neo4j",
    max_retries=1,
    default_retry_delay=60,
    acks_late=True,
)
def reprocess_entities_to_neo4j(self, document_ids: list[str]) -> dict:
    """Re-index documents into Neo4j from Qdrant chunk payloads.

    For each document, reads chunks from Qdrant, extracts entities from
    chunk payloads, and creates Neo4j nodes/edges.

    Parameters
    ----------
    document_ids:
        List of document ID strings to reprocess.

    Returns
    -------
    Dict with ``processed`` count and ``failed`` count.
    """
    logger.info("task.reprocess_neo4j.start", doc_count=len(document_ids))

    async def _run() -> dict:
        from neo4j import AsyncGraphDatabase
        from qdrant_client import QdrantClient

        from app.config import Settings
        from app.entities.graph_service import GraphService

        settings = Settings()
        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        qdrant = QdrantClient(url=settings.qdrant_url)

        try:
            gs = GraphService(driver)
            processed = 0
            failed = 0

            for doc_id in document_ids:
                try:
                    # Read chunks from Qdrant for this document
                    from app.common.vector_store import TEXT_COLLECTION

                    scroll_result = qdrant.scroll(
                        collection_name=TEXT_COLLECTION,
                        scroll_filter={"must": [{"key": "doc_id", "match": {"value": doc_id}}]},
                        limit=1000,
                        with_payload=True,
                    )
                    points = scroll_result[0]

                    if not points:
                        logger.warning("task.reprocess_neo4j.no_chunks", doc_id=doc_id)
                        continue

                    # Extract document metadata from first chunk
                    first_payload = points[0].payload or {}
                    filename = first_payload.get("filename", "unknown")
                    doc_type = first_payload.get("doc_type", "unknown")
                    matter_id = first_payload.get("matter_id")

                    # Create document node
                    await gs.create_document_node(
                        doc_id=doc_id,
                        filename=filename,
                        doc_type=doc_type,
                        page_count=first_payload.get("page_count", 0),
                        minio_path=first_payload.get("minio_path", ""),
                        matter_id=matter_id,
                    )

                    # Collect entities from chunk payloads
                    all_entities: list[dict] = []
                    chunk_data: list[dict] = []
                    for pt in points:
                        payload = pt.payload or {}
                        entities = payload.get("entities", [])
                        if isinstance(entities, list):
                            all_entities.extend(entities)
                        chunk_data.append(
                            {
                                "chunk_id": payload.get("chunk_id", str(pt.id)),
                                "text_preview": (payload.get("text", ""))[:200],
                                "page_number": payload.get("page_number", 1),
                                "qdrant_point_id": str(pt.id),
                            }
                        )

                    # Index entities
                    if all_entities:
                        await gs.index_entities_for_document(
                            doc_id=doc_id,
                            entities=all_entities,
                            matter_id=matter_id,
                        )

                    # Create chunk nodes
                    for cd in chunk_data:
                        await gs.create_chunk_node(
                            chunk_id=cd["chunk_id"],
                            text_preview=cd["text_preview"],
                            page_number=cd["page_number"],
                            qdrant_point_id=cd["qdrant_point_id"],
                            doc_id=doc_id,
                        )

                    processed += 1
                    logger.info(
                        "task.reprocess_neo4j.doc_done",
                        doc_id=doc_id,
                        entities=len(all_entities),
                        chunks=len(chunk_data),
                    )
                except Exception:
                    failed += 1
                    logger.error("task.reprocess_neo4j.doc_failed", doc_id=doc_id, exc_info=True)

            return {"processed": processed, "failed": failed}
        finally:
            await driver.close()
            qdrant.close()

    try:
        result = asyncio.run(_run())
        logger.info("task.reprocess_neo4j.complete", **result)
        return result
    except Exception as exc:
        logger.error("task.reprocess_neo4j.failed", error=str(exc))
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise
