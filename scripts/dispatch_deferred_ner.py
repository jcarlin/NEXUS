#!/usr/bin/env python3
"""Dispatch deferred NER tasks for pre-embedded imports.

The import_fbi_dataset.py script skips NER (--skip-ner) for performance.
This script dispatches `extract_entities_for_job` Celery tasks to the
dedicated NER queue for all documents that have no entities yet.

The NER task scrolls Qdrant by doc_id to find chunks, so we pass the
document ID (not job_id) as the first argument.

Usage::

    # Dispatch NER for all pre-embedded docs with no entities
    python scripts/dispatch_deferred_ner.py \\
        --matter-id 00000000-0000-0000-0000-000000000002

    # Dry run — count docs, don't dispatch
    python scripts/dispatch_deferred_ner.py \\
        --matter-id 00000000-0000-0000-0000-000000000002 --dry-run

    # Limit batch size and dispatch rate
    python scripts/dispatch_deferred_ner.py \\
        --matter-id 00000000-0000-0000-0000-000000000002 \\
        --batch-size 200 --pause 5
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    parser = argparse.ArgumentParser(description="Dispatch deferred NER tasks for pre-embedded imports")
    parser.add_argument("--matter-id", required=True, help="Matter UUID to process")
    parser.add_argument("--import-source", default="huggingface_pre_embedded", help="Filter by import_source")
    parser.add_argument("--batch-size", type=int, default=500, help="Docs per dispatch batch (default: 500)")
    parser.add_argument("--pause", type=float, default=2.0, help="Seconds to pause between batches (default: 2)")
    parser.add_argument("--dry-run", action="store_true", help="Count only, don't dispatch")
    parser.add_argument(
        "--force-all",
        action="store_true",
        help="Re-dispatch all docs (including those with entities) for Neo4j backfill",
    )
    args = parser.parse_args()

    from sqlalchemy import create_engine, text

    from app.config import Settings

    settings = Settings()
    engine = create_engine(settings.postgres_url_sync, pool_pre_ping=True)

    # Find documents with no entities from pre-embedded imports
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT d.id AS doc_id, d.filename, d.chunk_count, j.id AS job_id
                FROM documents d
                JOIN jobs j ON j.id = d.job_id
                WHERE d.matter_id = :mid
                  AND d.import_source = :src
                  AND (d.entity_count = 0 OR :force_all)
                ORDER BY d.created_at
            """),
            {"mid": args.matter_id, "src": args.import_source, "force_all": args.force_all},
        ).fetchall()

    total_docs = len(rows)
    total_chunks = sum(r.chunk_count or 0 for r in rows)
    print("\n=== Deferred NER Dispatch ===")
    print(f"  Matter:       {args.matter_id}")
    print(f"  Source:       {args.import_source}")
    print(f"  Docs to NER:  {total_docs:,}")
    print(f"  Total chunks: {total_chunks:,}")
    print(f"  Batch size:   {args.batch_size}")

    if total_docs == 0:
        print("  No documents need NER. Done.")
        return 0

    if args.dry_run:
        print("\n  [DRY RUN] Would dispatch NER for these documents.")
        print(f"  Estimated time at 6 workers: ~{total_chunks * 2 / 6 / 3600:.1f} hours")
        return 0

    # Import Celery task
    from app.ingestion.tasks import extract_entities_for_job

    dispatched = 0
    for i in range(0, total_docs, args.batch_size):
        batch = rows[i : i + args.batch_size]
        for row in batch:
            # Pass doc_id as first arg — the NER task uses it to scroll Qdrant by doc_id field
            extract_entities_for_job.apply_async(
                args=[str(row.doc_id), args.matter_id],
                queue="ner",
            )
            dispatched += 1

        print(f"  Dispatched {dispatched:,}/{total_docs:,} ({dispatched * 100 // total_docs}%)")

        if i + args.batch_size < total_docs:
            time.sleep(args.pause)

    print(f"\n=== Dispatched {dispatched:,} NER tasks to 'ner' queue ===")
    print("  Monitor: Admin → Pipeline → Workers & Queues tab")
    print(f"  Estimated completion: ~{total_chunks * 2 / 6 / 3600:.1f} hours at 6 workers")

    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
