#!/usr/bin/env python3
"""Backfill EXTRACTED_FROM (Entity→Chunk) and CO_OCCURS (Entity↔Entity) edges.

The HF import linked entities to documents (MENTIONED_IN) but not to chunks.
This script matches entities to their chunks by text search, creates
EXTRACTED_FROM edges, then generates chunk-level CO_OCCURS edges.

Idempotent — uses MERGE for edges and a marker property on Document nodes
to skip already-processed documents on re-run.

Usage::

    # Dry run — estimate work
    python scripts/backfill_entity_chunks.py --dry-run

    # Full backfill
    python scripts/backfill_entity_chunks.py

    # Limit to first 1000 docs (testing)
    python scripts/backfill_entity_chunks.py --limit 1000

    # Custom batch size and concurrency
    python scripts/backfill_entity_chunks.py --batch-size 500 --neo4j-batch 200
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import structlog

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = structlog.get_logger(__name__)

IMPORT_SOURCE = "kabasshouse/epstein-data"
DOC_BATCH_SIZE = 1000
NEO4J_BATCH_SIZE = 500
MARKER_PROPERTY = "entity_chunks_linked"


def _get_settings():
    from app.config import Settings

    return Settings()


def _get_engine(settings):
    from sqlalchemy import create_engine

    return create_engine(settings.postgres_url_sync)


def _get_neo4j_driver(settings):
    from neo4j import GraphDatabase

    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )


def _get_qdrant_client(settings):
    from qdrant_client import QdrantClient

    return QdrantClient(url=settings.qdrant_url, timeout=60)


def get_unprocessed_doc_ids(engine, matter_id: str, limit: int | None, offset: int = 0) -> list[str]:
    """Get document IDs that haven't been processed yet."""
    from sqlalchemy import text

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id FROM documents
                WHERE matter_id = :mid
                  AND import_source = :src
                ORDER BY id
                OFFSET :off LIMIT :lim
            """),
            {"mid": matter_id, "src": IMPORT_SOURCE, "off": offset, "lim": limit or 10_000_000},
        ).fetchall()
        return [str(r[0]) for r in rows]


def get_entities_for_doc(neo4j_driver, doc_id: str) -> list[dict]:
    """Get all entities linked to a document via MENTIONED_IN."""
    with neo4j_driver.session() as session:
        result = session.run(
            """
            MATCH (e:Entity)-[:MENTIONED_IN]->(d:Document {id: $doc_id})
            RETURN e.name AS name, e.type AS type
            """,
            doc_id=doc_id,
        )
        return [{"name": r["name"], "type": r["type"]} for r in result]


def get_chunks_for_doc(qdrant_client, doc_id: str, collection: str) -> list[dict]:
    """Get all chunks for a document from Qdrant."""
    chunks = []
    offset = None
    while True:
        points, offset = qdrant_client.scroll(
            collection_name=collection,
            scroll_filter={
                "must": [{"key": "doc_id", "match": {"value": doc_id}}],
            },
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for pt in points:
            chunks.append(
                {
                    "id": str(pt.id),
                    "text": (pt.payload.get("chunk_text") or "").lower(),
                    "chunk_index": pt.payload.get("chunk_index", 0),
                }
            )
        if offset is None:
            break
    return chunks


def is_doc_processed(neo4j_driver, doc_id: str) -> bool:
    """Check if a document has already been processed."""
    with neo4j_driver.session() as session:
        result = session.run(
            f"MATCH (d:Document {{id: $doc_id}}) RETURN d.{MARKER_PROPERTY} AS done",
            doc_id=doc_id,
        )
        record = result.single()
        return bool(record and record["done"])


def match_entities_to_chunks(
    entities: list[dict],
    chunks: list[dict],
) -> list[tuple[str, str, str]]:
    """Match entities to chunks by text containment.

    Returns list of (entity_name, entity_type, chunk_id) tuples.
    """
    matches = []
    for ent in entities:
        name_lower = ent["name"].lower()
        if len(name_lower) < 2:
            continue
        for chunk in chunks:
            if name_lower in chunk["text"]:
                matches.append((ent["name"], ent["type"], chunk["id"]))
    return matches


def write_extracted_from_edges(
    neo4j_driver, matches: list[tuple[str, str, str]], matter_id: str, batch_size: int = NEO4J_BATCH_SIZE
) -> int:
    """Create EXTRACTED_FROM edges in Neo4j."""
    if not matches:
        return 0

    created = 0
    for i in range(0, len(matches), batch_size):
        batch = [{"name": m[0], "type": m[1], "chunk_id": m[2]} for m in matches[i : i + batch_size]]
        with neo4j_driver.session() as session:
            session.run(
                """
                UNWIND $edges AS e
                MATCH (ent:Entity {name: e.name, type: e.type, matter_id: $mid})
                MATCH (c:Chunk {id: e.chunk_id})
                MERGE (ent)-[:EXTRACTED_FROM]->(c)
                """,
                edges=batch,
                mid=matter_id,
            )
            created += len(batch)
    return created


def create_co_occurs_for_doc(neo4j_driver, doc_id: str, matter_id: str) -> int:
    """Generate CO_OCCURS edges from shared chunks for a document.

    Uses HAS_CHUNK (Document→Chunk) direction since that's what the HF import created.
    """
    with neo4j_driver.session() as session:
        result = session.run(
            """
            MATCH (d:Document {id: $doc_id, matter_id: $mid})-[:HAS_CHUNK]->(c:Chunk)
            WITH c
            MATCH (e1:Entity)-[:EXTRACTED_FROM]->(c)<-[:EXTRACTED_FROM]-(e2:Entity)
            WHERE id(e1) < id(e2)
            WITH e1, e2, count(DISTINCT c) AS shared_chunks
            MERGE (e1)-[r:CO_OCCURS]->(e2)
            SET r.weight = shared_chunks
            RETURN count(r) AS edges
            """,
            doc_id=doc_id,
            mid=matter_id,
        )
        record = result.single()
        return record["edges"] if record else 0


def mark_doc_processed(neo4j_driver, doc_id: str) -> None:
    """Mark a document as processed."""
    with neo4j_driver.session() as session:
        session.run(
            f"MATCH (d:Document {{id: $doc_id}}) SET d.{MARKER_PROPERTY} = true",
            doc_id=doc_id,
        )


def count_unprocessed(neo4j_driver, matter_id: str) -> int:
    """Count documents not yet processed."""
    with neo4j_driver.session() as session:
        result = session.run(
            f"""
            MATCH (d:Document)
            WHERE d.matter_id = $mid AND (d.{MARKER_PROPERTY} IS NULL OR d.{MARKER_PROPERTY} = false)
            RETURN count(d) AS cnt
            """,
            mid=matter_id,
        )
        record = result.single()
        return record["cnt"] if record else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill EXTRACTED_FROM + CO_OCCURS edges")
    parser.add_argument("--dry-run", action="store_true", help="Count work without writing")
    parser.add_argument("--limit", type=int, help="Max documents to process")
    parser.add_argument("--batch-size", type=int, default=DOC_BATCH_SIZE, help="PG doc batch size")
    parser.add_argument("--neo4j-batch", type=int, default=NEO4J_BATCH_SIZE, help="Neo4j write batch")
    parser.add_argument(
        "--matter-id",
        default="00000000-0000-0000-0000-000000000002",
        help="Matter UUID",
    )
    args = parser.parse_args()

    neo4j_batch = args.neo4j_batch

    settings = _get_settings()
    engine = _get_engine(settings)
    neo4j_driver = _get_neo4j_driver(settings)
    qdrant = _get_qdrant_client(settings)

    from app.common.vector_store import TEXT_COLLECTION

    t0 = time.time()

    # Count unprocessed
    unprocessed = count_unprocessed(neo4j_driver, args.matter_id)
    logger.info("unprocessed_docs", count=unprocessed)

    if args.dry_run:
        print(f"Documents to process: {unprocessed:,}")
        print(f"Estimated time: {unprocessed * 0.01:.0f}s ({unprocessed * 0.01 / 3600:.1f}h)")
        neo4j_driver.close()
        return

    # Register with TaskTracker
    tracker = None
    try:
        from scripts.lib.task_tracker import TaskTracker

        tracker = TaskTracker(
            "Entity-Chunk Backfill",
            "backfill_entity_chunks.py",
            total=unprocessed,
        )
    except Exception:
        logger.warning("task_tracker.unavailable")

    # Process documents in batches
    stats = {
        "docs_processed": 0,
        "docs_skipped": 0,
        "extracted_from_created": 0,
        "co_occurs_created": 0,
        "docs_no_entities": 0,
        "docs_no_chunks": 0,
        "errors": 0,
    }

    all_doc_ids = get_unprocessed_doc_ids(engine, args.matter_id, args.limit)
    total_docs = len(all_doc_ids)
    logger.info("total_docs_to_check", count=total_docs)

    for i, doc_id in enumerate(all_doc_ids):
        try:
            # Skip if already processed
            if is_doc_processed(neo4j_driver, doc_id):
                stats["docs_skipped"] += 1
                continue

            # 1. Get entities for this doc
            entities = get_entities_for_doc(neo4j_driver, doc_id)
            if not entities:
                stats["docs_no_entities"] += 1
                mark_doc_processed(neo4j_driver, doc_id)
                continue

            # 2. Get chunks from Qdrant
            chunks = get_chunks_for_doc(qdrant, doc_id, TEXT_COLLECTION)
            if not chunks:
                stats["docs_no_chunks"] += 1
                mark_doc_processed(neo4j_driver, doc_id)
                continue

            # 3. Match entities to chunks
            matches = match_entities_to_chunks(entities, chunks)

            # 4. Write EXTRACTED_FROM edges
            if matches:
                ef_count = write_extracted_from_edges(neo4j_driver, matches, args.matter_id, neo4j_batch)
                stats["extracted_from_created"] += ef_count

                # 5. Generate CO_OCCURS for this document
                co_count = create_co_occurs_for_doc(neo4j_driver, doc_id, args.matter_id)
                stats["co_occurs_created"] += co_count

            # 6. Mark as processed
            mark_doc_processed(neo4j_driver, doc_id)
            stats["docs_processed"] += 1

        except Exception as e:
            stats["errors"] += 1
            logger.warning("doc.error", doc_id=doc_id, error=str(e))
            continue

        # Progress logging
        if (i + 1) % 1000 == 0:
            elapsed = time.time() - t0
            rate = (stats["docs_processed"] + stats["docs_skipped"]) / elapsed if elapsed > 0 else 0
            logger.info(
                "progress",
                checked=i + 1,
                processed=stats["docs_processed"],
                skipped=stats["docs_skipped"],
                extracted_from=stats["extracted_from_created"],
                co_occurs=stats["co_occurs_created"],
                rate=f"{rate:.1f}/sec",
                elapsed=f"{elapsed:.0f}s",
            )
            if tracker:
                tracker.update(processed=stats["docs_processed"] + stats["docs_skipped"])

    # Summary
    elapsed = time.time() - t0
    print(f"\nSummary ({elapsed:.0f}s):")
    for k, v in stats.items():
        print(f"  {k}: {v:,}")

    if tracker:
        tracker.complete()

    neo4j_driver.close()


if __name__ == "__main__":
    main()
