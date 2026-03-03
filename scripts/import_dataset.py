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
import json
import sys
import time
import uuid
from pathlib import Path

import structlog

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text

logger = structlog.get_logger(__name__)

# Average chunks per document (empirical from legal corpus)
_AVG_CHUNKS_PER_DOC = 4.5

# OpenAI text-embedding-3-large pricing: $0.13 per 1M tokens
_EMBEDDING_COST_PER_M_TOKENS = 0.13

# Average tokens per chunk
_AVG_TOKENS_PER_CHUNK = 350


def dispatch_post_ingestion_hooks(matter_id: str) -> list[str]:
    """Dispatch post-ingestion Celery tasks by name string.

    Uses ``celery_app.send_task()`` to dispatch by name, so tasks that
    don't exist yet (M10b, M11) are logged and skipped rather than
    causing import errors.

    Returns list of successfully dispatched task names.
    """
    from workers.celery_app import celery_app

    dispatched: list[str] = []
    hooks = [
        ("entities.resolve_entities", {}),
        ("ingestion.detect_inclusive_emails", {"matter_id": matter_id}),
        ("agents.hot_document_scan", {"matter_id": matter_id}),
        ("agents.entity_resolution_agent", {"matter_id": matter_id}),
    ]

    for task_name, kwargs in hooks:
        try:
            celery_app.send_task(task_name, kwargs=kwargs)
            dispatched.append(task_name)
            logger.info("post_ingestion.dispatched", task=task_name)
        except Exception:
            logger.warning("post_ingestion.skipped", task=task_name, exc_info=True)

    return dispatched


def _get_sync_engine():
    """Create a sync engine from settings."""
    from app.config import Settings

    settings = Settings()
    return create_engine(settings.postgres_url_sync, pool_pre_ping=True)


def _check_resume(engine, content_hash: str, matter_id: str) -> bool:
    """Return True if a document with this content hash already exists."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT id FROM documents WHERE content_hash = :hash AND matter_id = :matter_id LIMIT 1"),
            {"hash": content_hash, "matter_id": matter_id},
        )
        return result.first() is not None


def _create_bulk_import_job(engine, matter_id: str, adapter_type: str, source_path: str, total: int) -> str:
    """Insert a bulk_import_jobs row (sync) and return its UUID string."""
    job_id = str(uuid.uuid4())
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO bulk_import_jobs
                    (id, matter_id, adapter_type, source_path, status,
                     total_documents, processed_documents, failed_documents,
                     skipped_documents, metadata_, created_at, updated_at)
                VALUES
                    (:id, :matter_id, :adapter_type, :source_path, 'processing',
                     :total, 0, 0, 0, :metadata_, now(), now())
                """
            ),
            {
                "id": job_id,
                "matter_id": matter_id,
                "adapter_type": adapter_type,
                "source_path": source_path,
                "total": total,
                "metadata_": json.dumps({}),
            },
        )
        conn.commit()
    return job_id


def _create_job_row(engine, job_id: str, filename: str, matter_id: str) -> None:
    """Create a job row in the jobs table (sync)."""
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO jobs (id, filename, status, stage, progress, error,
                                  parent_job_id, matter_id, metadata_, created_at, updated_at)
                VALUES (:id, :filename, 'pending', 'uploading', '{}', NULL,
                        NULL, :matter_id, :metadata_, now(), now())
                """
            ),
            {
                "id": job_id,
                "filename": filename,
                "matter_id": matter_id,
                "metadata_": json.dumps({}),
            },
        )
        conn.commit()


def _complete_bulk_job(engine, bulk_job_id: str, status: str = "complete", error: str | None = None) -> None:
    """Mark a bulk import job as complete or failed."""
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                UPDATE bulk_import_jobs
                SET status = :status,
                    error = :error,
                    completed_at = now(),
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {"id": bulk_job_id, "status": status, "error": error},
        )
        conn.commit()


def _increment_skipped(engine, bulk_job_id: str) -> None:
    """Atomically increment the skipped counter on a bulk import job."""
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                UPDATE bulk_import_jobs
                SET skipped_documents = skipped_documents + 1,
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {"id": bulk_job_id},
        )
        conn.commit()


def main() -> int:  # noqa: C901
    parser = argparse.ArgumentParser(
        description="NEXUS bulk dataset import CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "adapter",
        choices=["directory", "edrm_xml", "concordance_dat", "huggingface_csv"],
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
    elif args.adapter == "huggingface_csv":
        if not args.file:
            print("Error: --file is required for the huggingface_csv adapter", file=sys.stderr)
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

        est_chunks = int(doc_count * _AVG_CHUNKS_PER_DOC)
        est_tokens = est_chunks * _AVG_TOKENS_PER_CHUNK
        est_cost = (est_tokens / 1_000_000) * _EMBEDDING_COST_PER_M_TOKENS

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
    bulk_job_id = _create_bulk_import_job(engine, args.matter_id, args.adapter, source_path, doc_count)
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
                _increment_skipped(engine, bulk_job_id)
                continue

            # Resume: skip if content hash exists
            if args.resume and _check_resume(engine, doc.content_hash, args.matter_id):
                skipped += 1
                _increment_skipped(engine, bulk_job_id)
                continue

            # Create job row
            job_id = str(uuid.uuid4())
            _create_job_row(engine, job_id, doc.filename, args.matter_id)

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
        _complete_bulk_job(engine, bulk_job_id, "failed", str(exc))
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
    _complete_bulk_job(engine, bulk_job_id, "complete")

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
