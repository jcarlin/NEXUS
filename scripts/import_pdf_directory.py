#!/usr/bin/env python3
"""Import PDF files from a local directory into NEXUS.

Recursively discovers PDF files, uploads each to MinIO, and dispatches
``process_document`` Celery tasks for full Docling parsing + ingestion.
This is the PDF equivalent of ``import_dataset.py`` — use it when you
have a directory of raw PDFs that need OCR/parsing (as opposed to
pre-extracted text).

Usage examples::

    # Import all PDFs from a directory
    python scripts/import_pdf_directory.py \\
        --dir /path/to/pdfs --matter-id <UUID>

    # Dry-run (count files, no dispatch)
    python scripts/import_pdf_directory.py \\
        --dir /path/to/pdfs --matter-id <UUID> --dry-run

    # Resume (skip already-imported PDFs by content hash)
    python scripts/import_pdf_directory.py \\
        --dir /path/to/pdfs --matter-id <UUID> --resume

    # Limit to first 50 PDFs, assign to a dataset
    python scripts/import_pdf_directory.py \\
        --dir /path/to/pdfs --matter-id <UUID> \\
        --dataset-name "Depositions 2024" --limit 50

    # Disable HNSW during import for faster vector inserts
    python scripts/import_pdf_directory.py \\
        --dir /path/to/pdfs --matter-id <UUID> --disable-hnsw
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
import time
import uuid
from pathlib import Path

import structlog

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingestion.bulk_import import (
    _get_sync_engine,
    check_resume,
    complete_bulk_job,
    create_bulk_import_job,
    create_job_row,
    dispatch_post_ingestion_hooks,
    increment_skipped,
)

logger = structlog.get_logger(__name__)

# Directories and files to skip during recursive discovery
_SKIP_DIRS = {"__MACOSX", ".git", ".svn", "__pycache__", "node_modules"}
_SKIP_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}


def discover_pdfs(root: Path, *, limit: int | None = None) -> list[Path]:
    """Recursively find PDF files under *root*, skipping hidden/OS artifacts.

    Returns a sorted list of Path objects (sorted for deterministic ordering).
    If *limit* is set, returns at most *limit* paths.
    """
    pdfs: list[Path] = []
    for path in sorted(root.rglob("*")):
        # Skip hidden files/directories
        if any(part.startswith(".") for part in path.parts[len(root.parts) :]):
            continue
        # Skip known artifact directories
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        # Skip known artifact files
        if path.name in _SKIP_FILES:
            continue
        # Match .pdf extension (case-insensitive)
        if path.is_file() and path.suffix.lower() == ".pdf":
            pdfs.append(path)
            if limit is not None and len(pdfs) >= limit:
                break
    return pdfs


def _get_minio_client():
    """Create a sync boto3 S3 client pointed at MinIO."""
    import boto3
    from botocore.config import Config as BotoConfig

    from app.config import Settings

    settings = Settings()
    scheme = "https" if settings.minio_use_ssl else "http"
    endpoint_url = f"{scheme}://{settings.minio_endpoint}"

    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )
    return client, settings.minio_bucket


def lookup_dataset_id(engine, matter_id: str, dataset_name: str) -> str | None:
    """Find a dataset ID by name within a matter."""
    from sqlalchemy import text

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id FROM datasets WHERE matter_id = :mid AND name = :name LIMIT 1"),
            {"mid": matter_id, "name": dataset_name},
        ).first()
        return str(row.id) if row else None


def main() -> int:  # noqa: C901
    parser = argparse.ArgumentParser(
        description="NEXUS PDF directory import CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dir", type=Path, required=True, help="Directory containing PDF files")
    parser.add_argument("--matter-id", required=True, help="Target matter UUID")
    parser.add_argument("--dataset-name", default=None, help="Assign imported docs to this dataset (by name)")
    parser.add_argument("--limit", type=int, default=None, help="Import first N PDFs only")
    parser.add_argument("--batch-size", type=int, default=100, help="Progress print interval")
    parser.add_argument("--dry-run", action="store_true", help="Count PDFs and exit without importing")
    parser.add_argument("--resume", action="store_true", help="Skip PDFs whose content hash already exists")
    parser.add_argument("--disable-hnsw", action="store_true", help="Disable HNSW during import for faster inserts")

    args = parser.parse_args()

    # Validate matter_id
    try:
        uuid.UUID(args.matter_id)
    except ValueError:
        print(f"Error: '{args.matter_id}' is not a valid UUID", file=sys.stderr)
        return 1

    # Validate directory
    if not args.dir.exists():
        print(f"Error: directory '{args.dir}' does not exist", file=sys.stderr)
        return 1
    if not args.dir.is_dir():
        print(f"Error: '{args.dir}' is not a directory", file=sys.stderr)
        return 1

    # --- First pass: discover PDFs ---
    print(f"Scanning for PDFs in {args.dir} ...")
    pdf_paths = discover_pdfs(args.dir, limit=args.limit)
    pdf_count = len(pdf_paths)
    print(f"Found {pdf_count} PDF file(s)")

    if pdf_count == 0:
        print("No PDFs found. Exiting.")
        return 0

    # --- Dry-run path ---
    if args.dry_run:
        total_bytes = sum(p.stat().st_size for p in pdf_paths)
        print("\n--- Dry Run Summary ---")
        print(f"PDF files found:  {pdf_count}")
        print(f"Total size:       {total_bytes / (1024 * 1024):.1f} MB")
        return 0

    # --- Real import path ---
    from app.ingestion.tasks import process_document

    engine = _get_sync_engine()
    minio_client, minio_bucket = _get_minio_client()

    # Resolve dataset_id if --dataset-name was given
    dataset_id: str | None = None
    if args.dataset_name:
        dataset_id = lookup_dataset_id(engine, args.matter_id, args.dataset_name)
        if dataset_id is None:
            print(f"Error: dataset '{args.dataset_name}' not found for matter {args.matter_id}", file=sys.stderr)
            engine.dispose()
            return 1
        print(f"Dataset: {args.dataset_name} ({dataset_id})")

    # Disable HNSW if requested
    qdrant_client = None
    if args.disable_hnsw:
        from app.common.vector_store import TEXT_COLLECTION, VectorStoreClient
        from app.config import Settings

        settings = Settings()
        qdrant_client = VectorStoreClient(settings)
        print("Disabling HNSW indexing for bulk insert...")
        qdrant_client.disable_hnsw_indexing(TEXT_COLLECTION)

    # Create bulk import job
    source_path = str(args.dir)
    bulk_job_id = create_bulk_import_job(engine, args.matter_id, "pdf_directory", source_path, pdf_count)
    print(f"Bulk import job: {bulk_job_id}")

    # --- Second pass: upload + dispatch ---
    dispatched = 0
    skipped = 0
    start_time = time.time()

    try:
        for pdf_path in pdf_paths:
            filename = pdf_path.name

            # Read file bytes
            file_bytes = pdf_path.read_bytes()

            if len(file_bytes) == 0:
                skipped += 1
                increment_skipped(engine, bulk_job_id)
                continue

            # Compute content hash (SHA-256, truncated to 16 chars like compute_content_hash)
            content_hash = hashlib.sha256(file_bytes).hexdigest()[:16]

            # Resume: skip if content hash already exists for this matter
            if args.resume and check_resume(engine, content_hash, args.matter_id):
                skipped += 1
                increment_skipped(engine, bulk_job_id)
                continue

            # Generate job ID
            job_id = str(uuid.uuid4())
            minio_path = f"raw/{job_id}/{filename}"

            # Upload to MinIO
            minio_client.put_object(
                Bucket=minio_bucket,
                Key=minio_path,
                Body=io.BytesIO(file_bytes),
                ContentType="application/pdf",
            )

            # Create job row in PostgreSQL
            create_job_row(
                engine,
                job_id,
                filename,
                args.matter_id,
                dataset_id=dataset_id,
                bulk_import_job_id=bulk_job_id,
            )

            # Dispatch Celery task to bulk queue
            process_document.apply_async(args=[job_id, minio_path], queue="bulk")

            dispatched += 1

            # Progress output every batch_size docs
            if dispatched % args.batch_size == 0:
                elapsed = time.time() - start_time
                rate = dispatched / elapsed if elapsed > 0 else 0
                print(f"  Dispatched {dispatched}/{pdf_count} ({skipped} skipped) — {rate:.1f} docs/sec")

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
