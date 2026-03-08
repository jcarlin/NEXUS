"""One-time repair: backfill matter_id on Neo4j Entity nodes.

Entities created before the matter_id-scoped MERGE fix may have
matter_id = null.  This script infers the correct matter_id from
linked Document nodes and sets it.

Usage:
    python -m scripts.repair_neo4j_matter_ids
"""

from __future__ import annotations

import asyncio

import structlog

logger = structlog.get_logger(__name__)


async def main() -> None:
    from neo4j import AsyncGraphDatabase

    from app.config import Settings
    from app.entities.graph_service import GraphService

    settings = Settings()
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

    try:
        gs = GraphService(driver)
        updated = await gs.repair_entity_matter_ids()
        print(f"Repaired {updated} entities with missing matter_id")
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
