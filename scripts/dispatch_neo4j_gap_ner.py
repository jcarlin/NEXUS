#!/usr/bin/env python3
"""Dispatch NER tasks for documents missing Neo4j entity links.

Finds the gap: documents with entity_count > 0 in PostgreSQL but no
MENTIONED_IN relationships in Neo4j. Dispatches `extract_entities_for_job`
Celery tasks for each gap document to re-extract entities via GLiNER
and index them to Neo4j.

Root cause: the HF import Run 2 (--resume) wrote entity_count to PG
but failed to persist entities to Neo4j, leaving ~502K documents
invisible to the knowledge graph.

Usage::

    # Dry run — count gap, estimate time
    python scripts/dispatch_neo4j_gap_ner.py \\
        --matter-id 00000000-0000-0000-0000-000000000002 --dry-run

    # Test with 100 docs first
    python scripts/dispatch_neo4j_gap_ner.py \\
        --matter-id 00000000-0000-0000-0000-000000000002 --limit 100

    # Full dispatch
    python scripts/dispatch_neo4j_gap_ner.py \\
        --matter-id 00000000-0000-0000-0000-000000000002
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_MATTER_ID = "00000000-0000-0000-0000-000000000002"


def _get_neo4j_docs_with_entities(neo4j_driver, matter_id: str) -> set[str]:
    """Get set of document IDs that have MENTIONED_IN edges in Neo4j."""
    print("  Querying Neo4j for docs with entity links...", flush=True)
    with neo4j_driver.session() as s:
        result = s.run(
            "MATCH (e:Entity)-[:MENTIONED_IN]->(d:Document {matter_id: $mid}) RETURN DISTINCT d.id AS doc_id",
            mid=matter_id,
        )
        doc_ids = {r["doc_id"] for r in result}
    print(f"  Neo4j: {len(doc_ids):,} docs have entity links", flush=True)
    return doc_ids


def _get_pg_docs_with_entities(engine, matter_id: str) -> list[dict]:
    """Get docs with entity_count > 0 from PostgreSQL."""
    from sqlalchemy import text

    print("  Querying PG for docs with entity_count > 0...", flush=True)
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT d.id::text AS doc_id, d.filename, d.chunk_count, d.entity_count
                FROM documents d
                WHERE d.matter_id = :mid
                  AND (d.entity_count > 0 OR d.entity_count IS NULL)
                ORDER BY d.created_at
            """),
            {"mid": matter_id},
        ).fetchall()
    print(f"  PG: {len(rows):,} docs have entity_count > 0", flush=True)
    return [dict(r._mapping) for r in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description="Dispatch NER for docs missing Neo4j entity links")
    parser.add_argument("--matter-id", default=DEFAULT_MATTER_ID)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--pause", type=float, default=2.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, help="Only dispatch this many docs (for testing)")
    parser.add_argument(
        "--include-zero",
        action="store_true",
        help="Also include docs with entity_count = 0 (the 15.9K NER backlog)",
    )
    args = parser.parse_args()

    from neo4j import GraphDatabase
    from sqlalchemy import create_engine

    from app.config import Settings

    settings = Settings()
    engine = create_engine(settings.postgres_url_sync, pool_pre_ping=True)
    neo4j_driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

    # Step 1: Get doc IDs with MENTIONED_IN in Neo4j
    neo4j_doc_ids = _get_neo4j_docs_with_entities(neo4j_driver, args.matter_id)

    # Step 2: Get docs with entity_count > 0 in PG
    pg_docs = _get_pg_docs_with_entities(engine, args.matter_id)

    # Step 3: Compute the gap
    gap_docs = [d for d in pg_docs if d["doc_id"] not in neo4j_doc_ids]

    # Optionally include entity_count = 0 docs (the NER backlog)
    if args.include_zero:
        from sqlalchemy import text

        with engine.connect() as conn:
            zero_rows = conn.execute(
                text("""
                    SELECT d.id::text AS doc_id, d.filename, d.chunk_count, d.entity_count
                    FROM documents d
                    WHERE d.matter_id = :mid
                      AND d.entity_count = 0
                    ORDER BY d.created_at
                """),
                {"mid": args.matter_id},
            ).fetchall()
        zero_docs = [dict(r._mapping) for r in zero_rows]
        gap_docs.extend(zero_docs)
        print(f"  Including {len(zero_docs):,} docs with entity_count = 0")

    total_gap = len(gap_docs)
    total_chunks = sum(d.get("chunk_count") or 1 for d in gap_docs)

    print("\n=== Neo4j Entity Gap Analysis ===")
    print(f"  Neo4j docs with entities:  {len(neo4j_doc_ids):,}")
    print(f"  PG docs with entities:     {len(pg_docs):,}")
    print(f"  Gap (needs NER+Neo4j):     {total_gap:,}")
    print(f"  Total chunks to process:   {total_chunks:,}")

    # Show entity_count distribution of gap docs
    ec_dist: dict[int, int] = {}
    for d in gap_docs:
        ec = d.get("entity_count") or 0
        bucket = 0 if ec == 0 else (1 if ec == 1 else (5 if ec <= 5 else 20))
        ec_dist[bucket] = ec_dist.get(bucket, 0) + 1
    print(f"  Gap entity_count distribution: {ec_dist}")

    if total_gap == 0:
        print("  No gap documents found. Done.")
        neo4j_driver.close()
        engine.dispose()
        return 0

    if args.limit:
        gap_docs = gap_docs[: args.limit]
        total_gap = len(gap_docs)
        total_chunks = sum(d.get("chunk_count") or 1 for d in gap_docs)
        print(f"\n  [LIMITED] Processing first {total_gap:,} docs ({total_chunks:,} chunks)")

    est_hours_1w = total_chunks * 0.05 / 3600  # ~50ms per chunk
    est_hours_6w = est_hours_1w / 6
    print(f"  Estimated time: ~{est_hours_1w:.1f}h (1 worker) / ~{est_hours_6w:.1f}h (6 workers)")

    if args.dry_run:
        print("\n  [DRY RUN] Would dispatch NER for these documents.")
        neo4j_driver.close()
        engine.dispose()
        return 0

    # Step 4: Dispatch Celery tasks
    from app.ingestion.tasks import extract_entities_for_job

    print(f"\n=== Dispatching {total_gap:,} NER tasks ===")
    dispatched = 0
    t0 = time.time()

    for i in range(0, total_gap, args.batch_size):
        batch = gap_docs[i : i + args.batch_size]
        for doc in batch:
            extract_entities_for_job.apply_async(
                args=[doc["doc_id"], args.matter_id],
                queue="ner",
            )
            dispatched += 1

        elapsed = time.time() - t0
        pct = dispatched * 100 // total_gap
        print(
            f"  Dispatched {dispatched:,}/{total_gap:,} ({pct}%) — {elapsed:.0f}s",
            flush=True,
        )

        if i + args.batch_size < total_gap:
            time.sleep(args.pause)

    elapsed = time.time() - t0
    print(f"\n=== Dispatched {dispatched:,} NER tasks to 'ner' queue in {elapsed:.0f}s ===")
    print(f"  Estimated completion: ~{est_hours_6w:.1f}h at 6 workers")
    print("  Monitor: Admin > Pipeline > Workers & Queues tab")

    neo4j_driver.close()
    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
