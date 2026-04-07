#!/usr/bin/env python3
"""Backfill the documents.document_date column from existing metadata.

Three phases, all idempotent and resumable:

  Phase 1 — PostgreSQL
    Select rows where ``document_date IS NULL`` and ``metadata_->>'date'``
    is non-empty. Parse via ``parse_email_date`` (RFC 2822 + ISO 8601 +
    dateutil fallback) and ``UPDATE documents SET document_date``. Rows
    whose raw date cannot be parsed stay NULL and are logged.

  Phase 2 — Neo4j
    For every document with a non-null ``document_date`` in PG, MERGE
    the matching ``:Document`` node and set ``d.document_date`` to the
    ISO 8601 string. Runs via a single UNWIND Cypher per batch.

  Phase 3 — Qdrant
    For every document with a non-null ``document_date``, issue one
    ``set_payload`` call filtered on ``doc_id`` so that every chunk
    payload for the document gains a ``document_date`` field.

Usage::

    # Dry run — count rows that would be updated
    python -m scripts.backfill_document_dates --dry-run

    # Scoped to a single matter
    python -m scripts.backfill_document_dates --matter-id <uuid>

    # Skip specific phases (e.g. for partial re-runs)
    python -m scripts.backfill_document_dates --skip-neo4j --skip-qdrant

    # Custom batch size
    python -m scripts.backfill_document_dates --batch 500
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.common.db_utils import parse_email_date  # noqa: E402
from scripts.lib.task_tracker import TaskTracker  # noqa: E402

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_engine():
    from app.config import Settings
    from app.ingestion.tasks import _get_sync_engine

    return _get_sync_engine(Settings())


def _where_matter(matter_id: str | None) -> str:
    return "AND matter_id = :matter_id" if matter_id else ""


# ---------------------------------------------------------------------------
# Phase 1 — PostgreSQL
# ---------------------------------------------------------------------------


def backfill_postgres(
    engine,
    *,
    matter_id: str | None,
    batch: int,
    dry_run: bool,
    tracker: TaskTracker | None,
) -> tuple[int, int]:
    """Parse metadata_->>'date' and write document_date.

    Uses **id-cursor pagination** rather than LIMIT/OFFSET. OFFSET pagination
    is broken here because each batch commits UPDATEs that shrink the
    ``WHERE document_date IS NULL`` matching set, so a fixed OFFSET skips
    rows. The cursor (``id > :last_id``) advances naturally regardless of
    whether each row was updated or left NULL (unparseable), so every
    matching row is visited exactly once.

    Returns ``(parsed, unparsable)``.
    """
    where_extra = _where_matter(matter_id)
    select_sql = text(
        f"""
        SELECT id, metadata_->>'date' AS raw_date
        FROM documents
        WHERE document_date IS NULL
          AND metadata_ ? 'date'
          AND length(metadata_->>'date') > 0
          AND id > :last_id
          {where_extra}
        ORDER BY id
        LIMIT :batch
        """
    )
    update_sql = text(
        """
        UPDATE documents
        SET document_date = :document_date,
            updated_at    = now()
        WHERE id = :doc_id
        """
    )

    parsed = 0
    unparsable = 0
    # Start cursor at the smallest possible UUID so the first query sees every row.
    last_id = "00000000-0000-0000-0000-000000000000"

    while True:
        params: dict[str, Any] = {"batch": batch, "last_id": last_id}
        if matter_id:
            params["matter_id"] = matter_id
        with engine.connect() as conn:
            rows = conn.execute(select_sql, params).fetchall()
            if not rows:
                break
            updates: list[dict[str, Any]] = []
            for row in rows:
                dt = parse_email_date(row.raw_date)
                if dt is None:
                    unparsable += 1
                    logger.warning(
                        "backfill.document_date.unparsable",
                        doc_id=str(row.id),
                        raw=(row.raw_date or "")[:200],
                    )
                    continue
                updates.append({"doc_id": str(row.id), "document_date": dt})
            if updates and not dry_run:
                conn.execute(update_sql, updates)
                conn.commit()
            parsed += len(updates)
            # Advance cursor past the largest id in this batch (rows are
            # ORDER BY id so the last row has the max id).
            last_id = str(rows[-1].id)
        if tracker:
            tracker.update(processed=parsed, failed=unparsable)
        print(f"  PG batch last_id={last_id}: parsed={parsed} unparsable={unparsable}")

    return parsed, unparsable


# ---------------------------------------------------------------------------
# Phase 2 — Neo4j
# ---------------------------------------------------------------------------


async def backfill_neo4j(
    engine,
    *,
    matter_id: str | None,
    batch: int,
    dry_run: bool,
    tracker: TaskTracker | None,
) -> int:
    """Set ``d.document_date`` on :Document nodes for all PG rows with a date.

    Returns total docs updated.
    """
    from neo4j import AsyncGraphDatabase

    from app.config import Settings

    settings = Settings()
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

    where_extra = _where_matter(matter_id)
    select_sql = text(
        f"""
        SELECT id, document_date
        FROM documents
        WHERE document_date IS NOT NULL
          {where_extra}
        ORDER BY id
        LIMIT :batch OFFSET :offset
        """
    )

    cypher = """
    UNWIND $rows AS row
    MATCH (d:Document {id: row.doc_id})
    SET d.document_date = row.document_date
    """

    total = 0
    offset = 0

    try:
        while True:
            params: dict[str, Any] = {"batch": batch, "offset": offset}
            if matter_id:
                params["matter_id"] = matter_id
            with engine.connect() as conn:
                rows = conn.execute(select_sql, params).fetchall()
            if not rows:
                break
            payload = [{"doc_id": str(r.id), "document_date": r.document_date.isoformat()} for r in rows]
            if not dry_run:
                async with driver.session() as session:
                    await session.run(cypher, rows=payload)
            total += len(payload)
            offset += batch
            if tracker:
                tracker.update(processed=total)
            print(f"  Neo4j batch offset={offset - batch}: updated={total}")
    finally:
        await driver.close()

    return total


# ---------------------------------------------------------------------------
# Phase 3 — Qdrant
# ---------------------------------------------------------------------------


def backfill_qdrant(
    engine,
    *,
    matter_id: str | None,
    batch: int,
    dry_run: bool,
    tracker: TaskTracker | None,
) -> tuple[int, int]:
    """Set ``document_date`` on all chunk payloads for each document.

    Returns ``(updated, failed)``.
    """
    from qdrant_client import QdrantClient
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    from app.common.vector_store import TEXT_COLLECTION
    from app.config import Settings

    settings = Settings()
    client = QdrantClient(url=settings.qdrant_url, timeout=120)

    where_extra = _where_matter(matter_id)
    select_sql = text(
        f"""
        SELECT id, document_date
        FROM documents
        WHERE document_date IS NOT NULL
          {where_extra}
        ORDER BY id
        LIMIT :batch OFFSET :offset
        """
    )

    updated = 0
    failed = 0
    offset = 0

    while True:
        params: dict[str, Any] = {"batch": batch, "offset": offset}
        if matter_id:
            params["matter_id"] = matter_id
        with engine.connect() as conn:
            rows = conn.execute(select_sql, params).fetchall()
        if not rows:
            break
        for row in rows:
            doc_id = str(row.id)
            iso = row.document_date.isoformat()
            if dry_run:
                updated += 1
                continue
            try:
                client.set_payload(
                    collection_name=TEXT_COLLECTION,
                    payload={"document_date": iso},
                    points=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]),
                )
                updated += 1
            except Exception as exc:
                failed += 1
                logger.warning(
                    "backfill.document_date.qdrant_failed",
                    doc_id=doc_id,
                    error=str(exc),
                )
        offset += batch
        if tracker:
            tracker.update(processed=updated, failed=failed)
        print(f"  Qdrant batch offset={offset - batch}: updated={updated} failed={failed}")

    return updated, failed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill document_date column.")
    parser.add_argument("--dry-run", action="store_true", help="Count rows but don't write.")
    parser.add_argument("--matter-id", default=None, help="Restrict to a single matter UUID.")
    parser.add_argument("--batch", type=int, default=500, help="Batch size for each phase.")
    parser.add_argument("--skip-postgres", action="store_true")
    parser.add_argument("--skip-neo4j", action="store_true")
    parser.add_argument("--skip-qdrant", action="store_true")
    args = parser.parse_args()

    engine = _get_engine()

    tracker: TaskTracker | None = None
    try:
        tracker = TaskTracker(
            name="document_date backfill",
            script_name="backfill_document_dates.py",
            total=0,
        )
    except Exception as exc:
        # Task tracker is best-effort — script still runs without the UI.
        print(f"warning: TaskTracker unavailable ({exc}); progress shown on stdout only")
        tracker = None

    try:
        if not args.skip_postgres:
            print("\n=== Phase 1: PostgreSQL ===")
            parsed, unparsable = backfill_postgres(
                engine,
                matter_id=args.matter_id,
                batch=args.batch,
                dry_run=args.dry_run,
                tracker=tracker,
            )
            print(f"Phase 1 total: parsed={parsed} unparsable={unparsable}")

        if not args.skip_neo4j:
            print("\n=== Phase 2: Neo4j ===")
            neo_total = asyncio.run(
                backfill_neo4j(
                    engine,
                    matter_id=args.matter_id,
                    batch=args.batch,
                    dry_run=args.dry_run,
                    tracker=tracker,
                )
            )
            print(f"Phase 2 total: updated={neo_total}")

        if not args.skip_qdrant:
            print("\n=== Phase 3: Qdrant ===")
            qd_updated, qd_failed = backfill_qdrant(
                engine,
                matter_id=args.matter_id,
                batch=args.batch,
                dry_run=args.dry_run,
                tracker=tracker,
            )
            print(f"Phase 3 total: updated={qd_updated} failed={qd_failed}")
    except Exception as exc:
        if tracker:
            tracker.fail(str(exc))
        raise
    else:
        if tracker:
            tracker.complete()

    return 0


if __name__ == "__main__":
    sys.exit(main())
