"""One-time repair: reconcile Qdrant doc_id payloads with PG documents.id.

Documents ingested via bulk import (process_text_import) stored chunks in
Qdrant with doc_id = job_id.  The PG documents table has a separate UUID
as documents.id.  The health check compares against documents.id, so all
bulk-imported docs appear as "missing" in Qdrant.

This script reads the job_id → documents.id mapping from PG and updates
each Qdrant point's doc_id payload to match documents.id.

Usage:
    python -m scripts.fix_qdrant_doc_ids
"""

from __future__ import annotations

import structlog
from qdrant_client import QdrantClient
from qdrant_client import models as qdrant_models
from sqlalchemy import create_engine, text

logger = structlog.get_logger(__name__)


def main() -> None:
    from app.config import Settings

    settings = Settings()
    engine = create_engine(settings.database_url.replace("+asyncpg", ""))

    # Fetch all documents that have a job_id different from their id
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, job_id FROM documents "
                "WHERE job_id IS NOT NULL AND id::text != job_id::text AND chunk_count > 0"
            )
        ).all()

    if not rows:
        print("No documents with mismatched job_id/id found. Nothing to fix.")
        return

    print(f"Found {len(rows)} documents with job_id != id. Updating Qdrant payloads...")

    from app.common.vector_store import TEXT_COLLECTION

    client = QdrantClient(url=settings.qdrant_url)
    fixed = 0
    skipped = 0

    for row in rows:
        doc_id = str(row._mapping["id"])
        job_id = str(row._mapping["job_id"])

        # Check if Qdrant still has points under the old job_id
        filter_ = qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="doc_id",
                    match=qdrant_models.MatchValue(value=job_id),
                )
            ]
        )

        count_result = client.count(collection_name=TEXT_COLLECTION, count_filter=filter_, exact=True)
        if count_result.count == 0:
            skipped += 1
            continue

        # Update doc_id payload from job_id → documents.id
        client.set_payload(
            collection_name=TEXT_COLLECTION,
            payload={"doc_id": doc_id},
            points=filter_,
        )

        fixed += 1
        if fixed % 100 == 0:
            print(f"  Progress: {fixed}/{len(rows)} documents updated...")

        logger.info("qdrant.doc_id_fixed", job_id=job_id, doc_id=doc_id, points=count_result.count)

    client.close()
    print(f"\nDone. Fixed: {fixed}, Skipped (no Qdrant points): {skipped}, Total: {len(rows)}")


if __name__ == "__main__":
    main()
