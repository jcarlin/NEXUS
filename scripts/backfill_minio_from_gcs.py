#!/usr/bin/env python3
"""Backfill MinIO with original PDFs from GCS for HF-imported documents.

The HF import (import_epstein_hf.py) was run with --skip-minio, so
documents have minio_path entries but no actual files. This script
downloads the original PDFs from gs://nexus-epstein-data/ and uploads
them to MinIO at the existing minio_path locations.

Idempotent — checks MinIO before uploading, safe to re-run.
Resume-safe — skips files already in MinIO.

Usage::

    # Dry run — count matches
    python scripts/backfill_minio_from_gcs.py --dry-run

    # Full backfill with 2 workers (gentle on CPU)
    python scripts/backfill_minio_from_gcs.py --workers 2

    # Process a single HF dataset
    python scripts/backfill_minio_from_gcs.py --hf-dataset DataSet1
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import time
from pathlib import Path

import structlog

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = structlog.get_logger(__name__)

GCS_BUCKET = "gs://nexus-epstein-data"
GCS_INDEX_PATH = "/tmp/gcs_efta_index.json"
IMPORT_SOURCE = "kabasshouse/epstein-data"
BATCH_SIZE = 500


def _get_engine():
    from sqlalchemy import create_engine

    from app.config import Settings

    settings = Settings()
    return create_engine(settings.postgres_url_sync)


def _get_minio_client():
    import boto3
    from botocore.config import Config as BotoConfig

    from app.config import Settings

    settings = Settings()
    scheme = "https" if settings.minio_use_ssl else "http"
    client = boto3.client(
        "s3",
        endpoint_url=f"{scheme}://{settings.minio_endpoint}",
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )
    bucket = settings.minio_bucket
    return client, bucket


def _get_gcs_client():
    from google.cloud import storage

    return storage.Client()


def build_gcs_index(force_rebuild: bool = False) -> dict[str, str]:
    """Build a mapping of EFTA key -> GCS blob path.

    Caches to disk at GCS_INDEX_PATH for restart resilience.
    """
    if not force_rebuild and os.path.exists(GCS_INDEX_PATH):
        logger.info("gcs_index.loading_cached", path=GCS_INDEX_PATH)
        with open(GCS_INDEX_PATH) as f:
            index = json.load(f)
        logger.info("gcs_index.loaded", count=len(index))
        return index

    logger.info("gcs_index.building", bucket=GCS_BUCKET)
    t0 = time.time()

    index: dict[str, str] = {}

    # Use google-cloud-storage Python client
    from google.cloud import storage as gcs_storage

    bucket_name = GCS_BUCKET.replace("gs://", "")
    client = gcs_storage.Client()
    bucket = client.bucket(bucket_name)
    count = 0

    for blob in bucket.list_blobs():
        count += 1
        name = blob.name
        # Extract the filename (without extension) as the key
        # e.g., ds1/0001/EFTA00000001.pdf -> EFTA00000001
        filename = name.rsplit("/", 1)[-1] if "/" in name else name
        key = filename.rsplit(".", 1)[0] if "." in filename else filename
        index[key] = f"gs://{bucket_name}/{name}"
        if count % 100_000 == 0:
            logger.info("gcs_index.progress", count=count)

    elapsed = time.time() - t0
    logger.info("gcs_index.built", count=len(index), elapsed=f"{elapsed:.1f}s")

    # Cache to disk
    with open(GCS_INDEX_PATH, "w") as f:
        json.dump(index, f)
    logger.info("gcs_index.cached", path=GCS_INDEX_PATH)

    return index


def minio_object_exists(minio_client, bucket: str, key: str) -> bool:
    """Check if an object exists in MinIO."""
    from botocore.exceptions import ClientError

    try:
        minio_client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        raise


_gcs_client = None


def _get_gcs_storage_client():
    global _gcs_client
    if _gcs_client is None:
        from google.cloud import storage

        _gcs_client = storage.Client()
    return _gcs_client


def download_gcs_blob(gcs_path: str) -> bytes:
    """Download a blob from GCS and return its bytes."""
    # Parse gs://bucket/key
    parts = gcs_path.replace("gs://", "").split("/", 1)
    bucket_name = parts[0]
    blob_name = parts[1]

    client = _get_gcs_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    return blob.download_as_bytes()


def process_document(
    doc: dict,
    gcs_index: dict[str, str],
    minio_client,
    minio_bucket: str,
) -> str:
    """Process a single document. Returns status string."""
    doc_id = doc["id"]
    minio_path = doc["minio_path"]
    file_key = doc["file_key"]

    # 1. Already in MinIO?
    if minio_object_exists(minio_client, minio_bucket, minio_path):
        return "skipped_exists"

    # 2. Find in GCS
    gcs_path = gcs_index.get(file_key)
    if not gcs_path:
        return "skipped_no_gcs"

    # 3. Download from GCS
    try:
        data = download_gcs_blob(gcs_path)
    except Exception as e:
        logger.warning("gcs.download_failed", doc_id=str(doc_id), error=str(e))
        return "failed_download"

    # 4. Upload to MinIO
    try:
        content_type = "application/pdf" if gcs_path.endswith(".pdf") else "application/octet-stream"
        minio_client.put_object(
            Bucket=minio_bucket,
            Key=minio_path,
            Body=data,
            ContentType=content_type,
        )
    except Exception as e:
        logger.warning("minio.upload_failed", doc_id=str(doc_id), error=str(e))
        return "failed_upload"

    return "uploaded"


def get_documents_batch(engine, offset: int, limit: int, hf_dataset: str | None = None) -> list[dict]:
    """Fetch a batch of documents needing MinIO backfill."""
    from sqlalchemy import text

    where = "WHERE d.import_source = :src"
    params: dict = {"src": IMPORT_SOURCE, "lim": limit, "off": offset}

    if hf_dataset:
        where += " AND d.metadata_->>'dataset' = :hf_ds"
        params["hf_ds"] = hf_dataset

    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT d.id, d.minio_path, d.filename,
                       d.metadata_->>'original_file_key' AS file_key
                FROM documents d
                {where}
                ORDER BY d.id
                OFFSET :off LIMIT :lim
            """),
            params,
        ).fetchall()
        return [{"id": str(r[0]), "minio_path": r[1], "filename": r[2], "file_key": r[3]} for r in rows]


def update_filenames_batch(engine, doc_ids: list[str]) -> int:
    """Add .pdf extension to filenames for documents that were uploaded."""
    from sqlalchemy import text

    if not doc_ids:
        return 0

    with engine.connect() as conn:
        result = conn.execute(
            text("""
                UPDATE documents
                SET filename = filename || '.pdf',
                    document_type = 'PDF',
                    updated_at = now()
                WHERE id = ANY(:ids::uuid[])
                  AND filename NOT LIKE '%.pdf'
            """),
            {"ids": doc_ids},
        )
        conn.commit()
        return result.rowcount


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill MinIO from GCS original PDFs")
    parser.add_argument("--dry-run", action="store_true", help="Count matches without uploading")
    parser.add_argument("--workers", type=int, default=2, help="Concurrent download/upload workers")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help="DB query batch size")
    parser.add_argument("--hf-dataset", type=str, help="Process only this HF dataset name")
    parser.add_argument("--rebuild-index", action="store_true", help="Force rebuild GCS index")
    parser.add_argument("--limit", type=int, help="Max documents to process")
    args = parser.parse_args()

    t0 = time.time()

    # 1. Build GCS index
    gcs_index = build_gcs_index(force_rebuild=args.rebuild_index)

    if args.dry_run:
        print(f"GCS index: {len(gcs_index):,} files")
        # Quick count of what would match
        engine = _get_engine()
        from sqlalchemy import text

        with engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT count(*) FROM documents
                    WHERE import_source = :src
                """),
                {"src": IMPORT_SOURCE},
            ).first()
            print(f"Documents to check: {row[0]:,}")
        return

    # 2. Setup clients
    engine = _get_engine()
    minio_client, minio_bucket = _get_minio_client()

    # 3. Optional TaskTracker
    tracker = None
    try:
        from scripts.lib.task_tracker import TaskTracker

        tracker = TaskTracker(
            "MinIO Backfill from GCS",
            "backfill_minio_from_gcs.py",
            total=0,  # Will update after first count
        )
    except Exception:
        logger.warning("task_tracker.unavailable")

    # 4. Process in batches
    stats = {"uploaded": 0, "skipped_exists": 0, "skipped_no_gcs": 0, "failed_download": 0, "failed_upload": 0}
    total_processed = 0
    offset = 0
    failed_ids: list[str] = []

    while True:
        docs = get_documents_batch(engine, offset, args.batch_size, args.hf_dataset)
        if not docs:
            break

        offset += len(docs)
        uploaded_ids = []

        # Process with thread pool for concurrent GCS downloads
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(process_document, doc, gcs_index, minio_client, minio_bucket): doc for doc in docs}
            for future in concurrent.futures.as_completed(futures):
                doc = futures[future]
                try:
                    status = future.result()
                    stats[status] += 1
                    if status == "uploaded":
                        uploaded_ids.append(doc["id"])
                    elif status.startswith("failed"):
                        failed_ids.append(doc["id"])
                except Exception as e:
                    logger.error("doc.error", doc_id=doc["id"], error=str(e))
                    stats["failed_download"] += 1
                    failed_ids.append(doc["id"])

        # Update filenames for uploaded docs
        if uploaded_ids:
            updated = update_filenames_batch(engine, uploaded_ids)
            logger.info("filenames.updated", count=updated)

        total_processed += len(docs)
        elapsed = time.time() - t0
        rate = total_processed / elapsed if elapsed > 0 else 0

        logger.info(
            "progress",
            processed=total_processed,
            uploaded=stats["uploaded"],
            skipped_exists=stats["skipped_exists"],
            skipped_no_gcs=stats["skipped_no_gcs"],
            failed=stats["failed_download"] + stats["failed_upload"],
            rate=f"{rate:.1f}/sec",
        )

        if tracker:
            tracker.update(
                processed=stats["uploaded"] + stats["skipped_exists"],
                failed=stats["failed_download"] + stats["failed_upload"],
                total=total_processed,
            )

        if args.limit and total_processed >= args.limit:
            logger.info("limit.reached", limit=args.limit)
            break

    # 5. Save failed IDs for retry
    if failed_ids:
        fail_path = "/tmp/failed_minio_backfill.json"
        with open(fail_path, "w") as f:
            json.dump(failed_ids, f)
        logger.info("failed_ids.saved", path=fail_path, count=len(failed_ids))

    # 6. Summary
    elapsed = time.time() - t0
    print(f"\nSummary ({elapsed:.0f}s):")
    for k, v in stats.items():
        print(f"  {k}: {v:,}")
    print(f"  total_processed: {total_processed:,}")

    if tracker:
        tracker.complete()


if __name__ == "__main__":
    main()
