#!/usr/bin/env python3
"""Fix page_count for PDF documents by reading actual page counts from MinIO.

The HF import set page_count=1 for all documents. This script downloads
each PDF from MinIO, counts the actual pages with pikepdf, and updates
the documents table.

Idempotent — only updates documents where page_count != actual.
Resume-safe — processes in batches with offset tracking.

Usage::

    # Dry run — show what would be updated
    python scripts/fix_page_counts.py --dry-run --limit 100

    # Fix page counts with 4 workers
    python scripts/fix_page_counts.py --workers 4 --batch-size 500

    # Fix a specific dataset
    python scripts/fix_page_counts.py --dataset "DOJ EFTA DS 9"
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import sys
from io import BytesIO

import structlog

# Allow importing from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy import text as sa_text

logger = structlog.get_logger()

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://nexus:nexus@localhost:5432/nexus",
)
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "documents")
MINIO_USE_SSL = os.environ.get("MINIO_USE_SSL", "false").lower() == "true"


def get_s3_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=f"{'https' if MINIO_USE_SSL else 'http'}://{MINIO_ENDPOINT}",
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
    )


def count_pdf_pages(s3, minio_path: str) -> int | None:
    """Download PDF from MinIO and count pages with pikepdf."""
    try:
        import pikepdf

        response = s3.get_object(Bucket=MINIO_BUCKET, Key=minio_path)
        data = response["Body"].read()
        pdf = pikepdf.open(BytesIO(data))
        count = len(pdf.pages)
        pdf.close()
        return count
    except Exception as e:
        logger.debug("page_count.error", path=minio_path, error=str(e))
        return None


def get_documents_batch(
    engine,
    offset: int,
    limit: int,
    dataset: str | None = None,
) -> list[dict]:
    """Fetch a batch of PDF documents that need page count fixes."""
    query = """
        SELECT d.id, d.minio_path, d.filename, d.page_count
        FROM documents d
    """
    params: dict = {"lim": limit, "off": offset}

    if dataset:
        query += """
            JOIN dataset_documents dd ON d.id = dd.document_id
            JOIN datasets ds ON dd.dataset_id = ds.id
            WHERE d.document_type = 'PDF'
              AND d.minio_path IS NOT NULL
              AND ds.name = :dataset
        """
        params["dataset"] = dataset
    else:
        query += """
            WHERE d.document_type = 'PDF'
              AND d.minio_path IS NOT NULL
        """

    query += " ORDER BY d.created_at OFFSET :off LIMIT :lim"

    with engine.connect() as conn:
        rows = conn.execute(sa_text(query), params).fetchall()
        return [
            {
                "id": str(r[0]),
                "minio_path": r[1],
                "filename": r[2],
                "page_count": r[3],
            }
            for r in rows
        ]


def process_document(doc: dict, s3) -> dict | None:
    """Count pages for a single document. Returns update dict or None."""
    actual = count_pdf_pages(s3, doc["minio_path"])
    if actual is None:
        return None
    if actual == doc["page_count"]:
        return None  # already correct
    return {"id": doc["id"], "page_count": actual}


def main():
    parser = argparse.ArgumentParser(description="Fix page_count for PDF documents")
    parser.add_argument("--dry-run", action="store_true", help="Don't update, just report")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent download workers")
    parser.add_argument("--batch-size", type=int, default=500, help="Documents per batch")
    parser.add_argument("--limit", type=int, default=0, help="Max documents to process (0=all)")
    parser.add_argument("--dataset", type=str, default=None, help="Filter to specific dataset name")
    args = parser.parse_args()

    engine = create_engine(DATABASE_URL)
    s3 = get_s3_client()

    offset = 0
    total_updated = 0
    total_processed = 0
    total_errors = 0

    try:
        from scripts.lib.task_tracker import TaskTracker

        tracker_ctx = TaskTracker(
            "Fix Page Counts",
            "fix_page_counts.py",
            total=args.limit or None,
        )
    except Exception:
        tracker_ctx = None

    tracker = tracker_ctx.__enter__() if tracker_ctx else None

    try:
        while True:
            docs = get_documents_batch(engine, offset, args.batch_size, args.dataset)
            if not docs:
                break

            updates = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = {pool.submit(process_document, doc, s3): doc for doc in docs}
                for future in concurrent.futures.as_completed(futures):
                    total_processed += 1
                    try:
                        result = future.result()
                        if result:
                            updates.append(result)
                    except Exception:
                        total_errors += 1

            if updates and not args.dry_run:
                with engine.connect() as conn:
                    for u in updates:
                        conn.execute(
                            sa_text(
                                "UPDATE documents SET page_count = :pc, updated_at = now() WHERE id = CAST(:id AS uuid)"
                            ),
                            {"id": u["id"], "pc": u["page_count"]},
                        )
                    conn.commit()

            total_updated += len(updates)
            logger.info(
                "batch.done",
                offset=offset,
                batch_size=len(docs),
                updates=len(updates),
                total_processed=total_processed,
                total_updated=total_updated,
            )

            if tracker:
                tracker.update(processed=total_processed)

            offset += args.batch_size
            if args.limit and total_processed >= args.limit:
                break

    finally:
        if tracker_ctx:
            tracker_ctx.__exit__(None, None, None)

    logger.info(
        "complete",
        total_processed=total_processed,
        total_updated=total_updated,
        total_errors=total_errors,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
