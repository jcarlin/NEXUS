#!/usr/bin/env python3
"""Deferred NER pass for documents imported with --skip-ner.

Finds documents with entity_count=0, fetches chunk text from Qdrant,
runs GLiNER NER, indexes entities to Neo4j, and updates PG entity counts.

Usage::

    # Dry run — see how many docs need NER
    python scripts/run_ner_pass.py \
        --matter-id 00000000-0000-0000-0000-000000000002 \
        --dry-run

    # Process first 100 docs with 4 parallel workers
    python scripts/run_ner_pass.py \
        --matter-id 00000000-0000-0000-0000-000000000002 \
        --concurrency 4 --limit 100

    # Single-threaded (debugging)
    python scripts/run_ner_pass.py \
        --matter-id 00000000-0000-0000-0000-000000000002 \
        --concurrency 1 --limit 10
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import structlog

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = structlog.get_logger(__name__)

NER_MAX_CHARS = 4_000


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _get_engine():
    from sqlalchemy import create_engine

    from app.config import Settings

    settings = Settings()
    return create_engine(settings.postgres_url_sync, pool_pre_ping=True)


def _get_settings():
    from app.config import Settings

    return Settings()


def find_docs_needing_ner(engine, matter_id: str, limit: int | None = None) -> list[dict]:
    """Find documents with entity_count=0 in the given matter."""
    from sqlalchemy import text

    query = """
        SELECT id, job_id, filename, chunk_count
        FROM documents
        WHERE matter_id = :mid AND entity_count = 0 AND job_id IS NOT NULL
        ORDER BY created_at
    """
    if limit:
        query += f" LIMIT {int(limit)}"

    with engine.connect() as conn:
        rows = conn.execute(text(query), {"mid": matter_id}).fetchall()
        return [
            {
                "id": str(r.id),  # Qdrant doc_id payload uses documents.id
                "neo4j_id": str(r.job_id),  # Neo4j Document.id uses job_id
                "filename": r.filename,
                "chunk_count": r.chunk_count,
            }
            for r in rows
        ]


def fetch_chunks_from_qdrant(settings, doc_id: str) -> list[dict]:
    """Fetch all chunk texts for a document from Qdrant."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    from app.common.vector_store import TEXT_COLLECTION

    client = QdrantClient(url=settings.qdrant_url)
    chunks: list[dict] = []

    offset = None
    while True:
        results = client.scroll(
            collection_name=TEXT_COLLECTION,
            scroll_filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]),
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points, next_offset = results
        for point in points:
            chunks.append(
                {
                    "text": point.payload.get("chunk_text", ""),
                    "page_number": point.payload.get("page_number"),
                    "chunk_index": point.payload.get("chunk_index", 0),
                    "qdrant_point_id": point.id,
                }
            )
        if next_offset is None:
            break
        offset = next_offset

    return sorted(chunks, key=lambda c: c["chunk_index"])


def update_entity_count(engine, doc_id: str, count: int) -> None:
    """Update entity_count on a document row."""
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(
            text("UPDATE documents SET entity_count = :count, updated_at = now() WHERE id = CAST(:id AS uuid)"),
            {"count": count, "id": doc_id},
        )
        conn.commit()


# ---------------------------------------------------------------------------
# NER worker (runs in separate process for true CPU parallelism)
# ---------------------------------------------------------------------------


def _run_ner_on_doc(doc_id: str, neo4j_id: str, doc_filename: str, matter_id: str) -> tuple[str, int]:
    """Run NER on a single document. Called in a worker process.

    *doc_id* is ``documents.id`` (used for Qdrant lookups).
    *neo4j_id* is ``documents.job_id`` (used for Neo4j Document node matching).

    Each worker loads its own GLiNER model. Returns (doc_id, entity_count).
    """
    from app.config import Settings
    from app.entities.extractor import EntityExtractor, normalize_entity_name

    settings = Settings()
    extractor = EntityExtractor(model_name=settings.gliner_model)

    # Fetch chunks from Qdrant (uses documents.id as doc_id payload)
    chunks = fetch_chunks_from_qdrant(settings, doc_id)
    if not chunks:
        return doc_id, 0

    # Extract entities
    seen: set[tuple[str, str]] = set()
    entities: list[dict] = []

    for chunk in chunks:
        text = chunk["text"][:NER_MAX_CHARS]
        if not text.strip():
            continue
        extracted = extractor.extract(text)
        for ent in extracted:
            name = normalize_entity_name(ent.text)
            key = (name.lower(), ent.type)
            if key not in seen:
                seen.add(key)
                entities.append(
                    {
                        "name": name,
                        "type": ent.type,
                        "page_number": chunk.get("page_number"),
                        "chunk_id": chunk.get("qdrant_point_id"),
                    }
                )

    if not entities:
        return doc_id, 0

    # Index to Neo4j (uses job_id as Document node ID)
    try:
        asyncio.run(_index_entities_neo4j(settings, neo4j_id, entities, matter_id))
    except Exception:
        logger.warning("ner_pass.neo4j_failed", doc_id=doc_id, exc_info=True)

    # Update PG entity count
    from sqlalchemy import create_engine

    engine = create_engine(settings.postgres_url_sync, pool_pre_ping=True)
    update_entity_count(engine, doc_id, len(entities))
    engine.dispose()

    return doc_id, len(entities)


async def _index_entities_neo4j(settings, doc_id: str, entities: list[dict], matter_id: str) -> None:
    """Index extracted entities to Neo4j."""
    from neo4j import AsyncGraphDatabase

    from app.entities.graph_service import GraphService

    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        gs = GraphService(driver)
        await gs.index_entities_for_document(
            doc_id=doc_id,
            entities=entities,
            matter_id=matter_id,
        )
    finally:
        await driver.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deferred NER pass for documents imported with --skip-ner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--matter-id", required=True, help="Target matter UUID")
    parser.add_argument("--concurrency", type=int, default=4, help="Worker processes (each loads ~600MB GLiNER model)")
    parser.add_argument("--limit", type=int, default=None, help="Process first N docs only")
    parser.add_argument("--dry-run", action="store_true", help="Count docs needing NER, don't process")
    parser.add_argument("--resume", action="store_true", help="Skip docs that already have entities (default behavior)")
    parser.add_argument("--resolve", action="store_true", help="Run batch entity resolution after NER extraction")

    args = parser.parse_args()

    try:
        uuid.UUID(args.matter_id)
    except ValueError:
        print(f"Error: '{args.matter_id}' is not a valid UUID", file=sys.stderr)
        return 1

    print("\n=== NEXUS Deferred NER Pass ===")
    print(f"  Matter:      {args.matter_id}")
    print(f"  Concurrency: {args.concurrency} processes")
    if args.limit:
        print(f"  Limit:       {args.limit} docs")

    engine = _get_engine()
    docs = find_docs_needing_ner(engine, args.matter_id, limit=args.limit)

    total_chunks = sum(d["chunk_count"] for d in docs)
    est_hours = (total_chunks * 2) / 3600  # ~2s/chunk on CPU
    est_hours_parallel = est_hours / max(args.concurrency, 1)

    print(f"\n  Documents needing NER: {len(docs):,}")
    print(f"  Total chunks:          {total_chunks:,}")
    print(f"  Est. time (serial):    {est_hours:.1f} hours (~2s/chunk)")
    print(f"  Est. time ({args.concurrency} workers): {est_hours_parallel:.1f} hours")
    print(f"  Est. memory:           ~{args.concurrency * 600}MB ({args.concurrency} x 600MB GLiNER)")

    if args.dry_run:
        if docs:
            print("\n  Sample documents:")
            for d in docs[:10]:
                print(f"    {d['filename']} ({d['chunk_count']} chunks)")
            if len(docs) > 10:
                print(f"    ... and {len(docs) - 10} more")
        engine.dispose()
        return 0

    if not docs:
        print("\n  No documents need NER. All done!")
        engine.dispose()
        return 0

    start_time = time.time()
    processed = 0
    total_entities = 0
    errors = 0

    print(f"\n  Processing {len(docs):,} documents...")

    try:
        if args.concurrency <= 1:
            # Sequential (single process, useful for debugging)
            for doc in docs:
                try:
                    doc_id, ent_count = _run_ner_on_doc(doc["id"], doc["neo4j_id"], doc["filename"], args.matter_id)
                    processed += 1
                    total_entities += ent_count
                    if processed % 10 == 0 or processed == 1:
                        elapsed = time.time() - start_time
                        rate = processed / elapsed if elapsed > 0 else 0
                        print(f"  [{processed}/{len(docs)}] {total_entities:,} entities, {rate:.1f} docs/sec")
                except Exception:
                    errors += 1
                    logger.error("ner_pass.doc_failed", doc_id=doc["id"], exc_info=True)
        else:
            # Parallel (ProcessPoolExecutor for true CPU parallelism)
            with ProcessPoolExecutor(max_workers=args.concurrency) as pool:
                futures = {
                    pool.submit(_run_ner_on_doc, doc["id"], doc["neo4j_id"], doc["filename"], args.matter_id): doc
                    for doc in docs
                }
                for future in as_completed(futures):
                    try:
                        doc_id, ent_count = future.result()
                        processed += 1
                        total_entities += ent_count
                        if processed % 10 == 0 or processed == 1:
                            elapsed = time.time() - start_time
                            rate = processed / elapsed if elapsed > 0 else 0
                            print(f"  [{processed}/{len(docs)}] {total_entities:,} entities, {rate:.1f} docs/sec")
                    except Exception:
                        errors += 1
                        doc = futures[future]
                        logger.error("ner_pass.doc_failed", doc_id=doc["id"], exc_info=True)

    except KeyboardInterrupt:
        print(f"\n  Interrupted! Processed {processed}, {errors} errors.")

    elapsed = time.time() - start_time
    print("\n=== NER Pass Complete ===")
    print(f"  Processed:       {processed:,} documents")
    print(f"  Errors:          {errors:,}")
    print(f"  Total entities:  {total_entities:,}")
    print(f"  Elapsed:         {elapsed:.1f}s ({elapsed / 60:.1f}min)")
    if processed > 0:
        print(f"  Rate:            {processed / elapsed:.1f} docs/sec")

    engine.dispose()

    # Optional: run batch entity resolution
    if args.resolve and processed > 0:
        print("\n=== Running Batch Entity Resolution ===")
        try:
            from app.entities.resolution_agent import run_resolution_agent

            res_start = time.time()
            result = asyncio.run(run_resolution_agent(args.matter_id))
            res_elapsed = time.time() - res_start
            print(f"  Merges performed:   {result.get('merges_performed', 0):,}")
            print(f"  Uncertain merges:   {len(result.get('uncertain_merges', [])):,}")
            print(f"  Hierarchy edges:    {result.get('hierarchy_edges_created', 0):,}")
            print(f"  Linked terms:       {result.get('linked_terms', 0):,}")
            print(f"  Elapsed:            {res_elapsed:.1f}s")
        except Exception:
            logger.error("ner_pass.resolution_failed", exc_info=True)
            print("  Resolution failed — see logs for details")

    return 0


if __name__ == "__main__":
    sys.exit(main())
