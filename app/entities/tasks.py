"""Celery tasks for entity resolution (post-ingestion).

The ``resolve_entities`` task fetches all entities of a given type from
Neo4j, runs fuzzy matching, and merges duplicates.
"""

from __future__ import annotations

import asyncio

import structlog
from celery import shared_task

logger = structlog.get_logger(__name__)


async def _run_resolution(entity_type: str | None = None) -> dict:
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
            entities = await gs.get_all_entities_by_type(etype)
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
def resolve_entities(self, entity_type: str | None = None) -> dict:
    """Run cross-document entity resolution.

    Fetches entities from Neo4j by type, finds fuzzy matches, and
    executes merges in the knowledge graph.

    Parameters
    ----------
    entity_type:
        Optional — resolve only this entity type. If None, resolves all types.

    Returns
    -------
    Dict with ``merges_performed`` and ``entity_types_processed``.
    """
    logger.info("task.resolve_entities.start", entity_type=entity_type)

    try:
        result = asyncio.run(_run_resolution(entity_type))
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
