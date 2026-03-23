#!/usr/bin/env python3
"""CLI orchestrator for bulk dataset imports.

Usage examples::

    # Import text files from a directory
    python scripts/import_dataset.py directory --data-dir /path/to/texts --matter-id <UUID>

    # Import from EDRM XML load file
    python scripts/import_dataset.py edrm_xml --file /path/to/loadfile.xml --matter-id <UUID>

    # Import from Concordance DAT load file
    python scripts/import_dataset.py concordance_dat --file /path/to/loadfile.dat --matter-id <UUID>

    # Import from HuggingFace CSV/Parquet dataset
    python scripts/import_dataset.py huggingface_csv --file /path/to/dataset.parquet --matter-id <UUID>

    # Dry-run (count + cost estimate, no dispatch)
    python scripts/import_dataset.py directory --data-dir /path/ --matter-id <UUID> --dry-run

    # Resume (skip already-imported docs by content hash)
    python scripts/import_dataset.py directory --data-dir /path/ --matter-id <UUID> --resume

    # Disable HNSW during import for faster inserts
    python scripts/import_dataset.py directory --data-dir /path/ --matter-id <UUID> --disable-hnsw
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

import structlog

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingestion.bulk_import import (
    AVG_CHUNKS_PER_DOC,
    AVG_TOKENS_PER_CHUNK,
    EMBEDDING_COST_PER_M_TOKENS,
    _get_sync_engine,
    check_resume,
    complete_bulk_job,
    create_bulk_import_job,
    create_job_row,
    dispatch_post_ingestion_hooks,
    increment_skipped,
)

logger = structlog.get_logger(__name__)


def main() -> int:  # noqa: C901
    parser = argparse.ArgumentParser(
        description="NEXUS bulk dataset import CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "adapter",
        choices=["directory", "edrm_xml", "concordance_dat", "huggingface_csv", "epstein_emails"],
        help="Dataset adapter to use",
    )
    parser.add_argument("--matter-id", required=True, help="Target matter UUID")
    parser.add_argument("--data-dir", type=Path, help="Directory path (for directory adapter)")
    parser.add_argument("--file", type=Path, help="Load file path (for edrm_xml / concordance_dat)")
    parser.add_argument("--content-dir", type=Path, help="Directory containing referenced files")
    parser.add_argument("--limit", type=int, default=None, help="Import first N documents only")
    parser.add_argument("--batch-size", type=int, default=100, help="Celery tasks per progress print")
    parser.add_argument("--dry-run", action="store_true", help="Count + estimate cost, dispatch nothing")
    parser.add_argument("--resume", action="store_true", help="Skip docs whose content_hash exists")
    parser.add_argument("--disable-hnsw", action="store_true", help="Disable HNSW during import")

    args = parser.parse_args()

    # Validate matter_id
    try:
        uuid.UUID(args.matter_id)
    except ValueError:
        print(f"Error: '{args.matter_id}' is not a valid UUID", file=sys.stderr)
        return 1

    # Build adapter
    from app.ingestion.adapters import ADAPTER_REGISTRY

    adapter_cls = ADAPTER_REGISTRY[args.adapter]

    if args.adapter == "directory":
        if not args.data_dir:
            print("Error: --data-dir is required for the directory adapter", file=sys.stderr)
            return 1
        if not args.data_dir.exists():
            print(f"Error: directory '{args.data_dir}' does not exist", file=sys.stderr)
            return 1
        adapter = adapter_cls(data_dir=args.data_dir)
    elif args.adapter in ("huggingface_csv", "epstein_emails"):
        if not args.file:
            print(f"Error: --file is required for the {args.adapter} adapter", file=sys.stderr)
            return 1
        if not args.file.exists():
            print(f"Error: file '{args.file}' does not exist", file=sys.stderr)
            return 1
        adapter = adapter_cls(file_path=args.file)
    elif args.adapter in ("edrm_xml", "concordance_dat"):
        if not args.file:
            print(f"Error: --file is required for the {args.adapter} adapter", file=sys.stderr)
            return 1
        if not args.file.exists():
            print(f"Error: file '{args.file}' does not exist", file=sys.stderr)
            return 1
        if args.adapter == "edrm_xml":
            adapter = adapter_cls(xml_path=args.file, content_dir=args.content_dir)
        else:
            adapter = adapter_cls(dat_path=args.file, content_dir=args.content_dir)
    else:
        print(f"Error: unknown adapter '{args.adapter}'", file=sys.stderr)
        return 1

    # --- Dry-run path ---
    if args.dry_run:
        print(f"Dry-run: scanning {args.adapter} source...")
        doc_count = 0
        total_chars = 0
        for doc in adapter.iter_documents(limit=args.limit):
            doc_count += 1
            total_chars += len(doc.text)

        est_chunks = int(doc_count * AVG_CHUNKS_PER_DOC)
        est_tokens = est_chunks * AVG_TOKENS_PER_CHUNK
        est_cost = (est_tokens / 1_000_000) * EMBEDDING_COST_PER_M_TOKENS

        print("\n--- Dry Run Summary ---")
        print(f"Documents found:     {doc_count}")
        print(f"Total characters:    {total_chars:,}")
        print(f"Est. chunks:         {est_chunks:,}")
        print(f"Est. tokens:         {est_tokens:,}")
        print(f"Est. embedding cost: ${est_cost:.2f}")
        return 0

    # --- Real import path ---
    from app.ingestion.tasks import import_text_document

    engine = _get_sync_engine()

    # Disable HNSW if requested
    qdrant_client = None
    if args.disable_hnsw:
        from app.common.vector_store import TEXT_COLLECTION, VectorStoreClient
        from app.config import Settings

        settings = Settings()
        qdrant_client = VectorStoreClient(settings)
        print("Disabling HNSW indexing for bulk insert...")
        qdrant_client.disable_hnsw_indexing(TEXT_COLLECTION)

    # First pass: count documents for bulk import job
    print(f"Counting documents from {args.adapter} source...")
    doc_count = sum(1 for _ in adapter.iter_documents(limit=args.limit))
    print(f"Found {doc_count} documents")

    if doc_count == 0:
        print("No documents found. Exiting.")
        engine.dispose()
        return 0

    # Create bulk import job
    source_path = str(args.data_dir or args.file)
    bulk_job_id = create_bulk_import_job(engine, args.matter_id, args.adapter, source_path, doc_count)
    print(f"Bulk import job: {bulk_job_id}")

    # Second pass: dispatch tasks
    dispatched = 0
    skipped = 0
    start_time = time.time()

    try:
        for doc in adapter.iter_documents(limit=args.limit):
            # Skip empty text
            if not doc.text.strip():
                skipped += 1
                increment_skipped(engine, bulk_job_id)
                continue

            # Resume: skip if content hash exists
            if args.resume and check_resume(engine, doc.content_hash, args.matter_id):
                skipped += 1
                increment_skipped(engine, bulk_job_id)
                continue

            # Create job row
            job_id = str(uuid.uuid4())
            create_job_row(engine, job_id, doc.filename, args.matter_id, bulk_import_job_id=bulk_job_id)

            # Dispatch Celery task
            import_text_document.delay(
                job_id=job_id,
                text=doc.text,
                filename=doc.filename,
                content_hash=doc.content_hash,
                matter_id=args.matter_id,
                doc_type=doc.doc_type,
                page_count=doc.page_count,
                metadata=doc.metadata,
                pre_entities=doc.entities if doc.entities else None,
                import_source=doc.source,
                bulk_import_job_id=bulk_job_id,
                email_headers=doc.email_headers,
            )

            dispatched += 1

            # Progress output every batch_size docs
            if dispatched % args.batch_size == 0:
                elapsed = time.time() - start_time
                rate = dispatched / elapsed if elapsed > 0 else 0
                print(f"  Dispatched {dispatched}/{doc_count} ({skipped} skipped) — {rate:.1f} docs/sec")

    except KeyboardInterrupt:
        print(f"\nInterrupted. Dispatched {dispatched} tasks, skipped {skipped}.")
    except Exception as exc:
        complete_bulk_job(engine, bulk_job_id, "failed", str(exc))
        raise

    # Rebuild HNSW if it was disabled
    if args.disable_hnsw and qdrant_client:
        from app.common.vector_store import TEXT_COLLECTION

        print("Rebuilding HNSW index (background)...")
        qdrant_client.rebuild_hnsw_index(TEXT_COLLECTION)

    # Dispatch post-ingestion hooks
    print("Dispatching post-ingestion hooks...")
    dispatched_hooks = dispatch_post_ingestion_hooks(args.matter_id)
    print(f"  Dispatched: {', '.join(dispatched_hooks) or 'none'}")

    # Mark bulk job complete (tasks still running in Celery)
    complete_bulk_job(engine, bulk_job_id, "complete")

    elapsed = time.time() - start_time
    print("\n--- Import Summary ---")
    print(f"Bulk import job: {bulk_job_id}")
    print(f"Dispatched:      {dispatched}")
    print(f"Skipped:         {skipped}")
    print(f"Elapsed:         {elapsed:.1f}s")
    print(f"Rate:            {dispatched / elapsed:.1f} docs/sec" if elapsed > 0 else "")

    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
