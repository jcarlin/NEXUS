#!/usr/bin/env python3
"""Backfill dataset_documents links for HF-imported documents.

The HF import (import_epstein_hf.py) populates documents with
metadata_->>'dataset' but never creates dataset_documents rows.
This script reads those metadata values, finds or creates matching
dataset rows, and bulk-inserts the junction records.

Idempotent — uses ON CONFLICT DO NOTHING, safe to re-run.
Resume-safe — only processes documents not yet linked.

Usage::

    # Dry run — show what would be done
    python scripts/backfill_dataset_documents.py --dry-run

    # Full backfill
    python scripts/backfill_dataset_documents.py

    # Custom batch size
    python scripts/backfill_dataset_documents.py --batch-size 5000
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import structlog

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = structlog.get_logger(__name__)

# HF dataset name -> desired NEXUS dataset name mapping.
# Unmapped names are used as-is.
DATASET_NAME_MAP: dict[str, str] = {
    "DataSet1": "DOJ EFTA DS 1",
    "DataSet2": "DOJ EFTA DS 2",
    "DataSet3": "DOJ EFTA DS 3",
    "DataSet4": "DOJ EFTA DS 4",
    "DataSet5": "DOJ EFTA DS 5",
    "DataSet6": "DOJ EFTA DS 6",
    "DataSet7": "DOJ EFTA DS 7",
    "DataSet8": "DOJ EFTA DS 8",
    "DataSet9": "DOJ EFTA DS 9",
    "DataSet10": "DOJ EFTA DS 10",
    "DataSet11": "DOJ EFTA DS 11",
    "DataSet12": "DOJ EFTA DS 12",
    "HouseOversightEstate": "House Oversight Estate",
    "IMAGES001": "DOJ-OGR Images 001",
    "IMAGES002": "DOJ-OGR Images 002",
    "IMAGES003": "DOJ-OGR Images 003",
    "IMAGES004": "DOJ-OGR Images 004",
    "IMAGES005": "DOJ-OGR Images 005",
    "IMAGES006": "DOJ-OGR Images 006",
    "IMAGES007": "DOJ-OGR Images 007",
    "IMAGES008": "DOJ-OGR Images 008",
    "IMAGES009": "DOJ-OGR Images 009",
    "IMAGES010": "DOJ-OGR Images 010",
    "IMAGES011": "DOJ-OGR Images 011",
    "IMAGES012": "DOJ-OGR Images 012",
    "USAvJE": "USA v. Jeffrey Epstein",
    "USAvJE_FOIA": "USA v. JE (FOIA)",
    "FBIVault": "FBI FOIA Vault",
    "FlightLogs": "Flight Logs",
    "EpsteinCollection": "Epstein Collection",
    "EpsteinDocsMixed": "Epstein Docs (Mixed)",
    "DocumentCloud": "DocumentCloud",
    "CourtOpinions": "Court Opinions",
    "Congressional": "Congressional",
    "PalmBeachSA": "Palm Beach SA",
    "HouseJudiciary": "House Judiciary",
    "PublicIntelligence": "Public Intelligence",
    "UnredactedFiles": "Unredacted Files",
    "maxwell_trial_transcripts": "Maxwell Trial Transcripts",
    "maxwell_interview": "Maxwell Interview",
    "CommunityResearch": "Community Research",
    "Financial": "Financial Records",
    "GovReports": "Government Reports",
    "UK_FCA": "UK FCA",
    "DOJ_Official": "DOJ Official",
    "fbi_death_investigation": "FBI Death Investigation",
    "internet_archive": "Internet Archive",
    "StateLaw": "State Law",
    "Zenodo": "Zenodo Archive",
    "Tier2": "Tier 2 Documents",
    "HouseOversightPre-embedded": "House Oversight Pre-embedded",
    "_unknown": "Unknown / Unclassified",
}

# assigned_by is nullable — use NULL for script backfills
ASSIGNED_BY = None

IMPORT_SOURCE = "kabasshouse/epstein-data"
BATCH_SIZE = 10_000


def _get_engine():
    from sqlalchemy import create_engine

    from app.config import Settings

    settings = Settings()
    db_url = str(settings.database_url).replace("+asyncpg", "")
    return create_engine(db_url)


def get_hf_dataset_names(engine) -> list[dict]:
    """Get distinct HF dataset names with their document counts."""
    from sqlalchemy import text

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT metadata_->>'dataset' AS hf_name, count(*) AS doc_count
                FROM documents
                WHERE import_source = :src
                  AND metadata_->>'dataset' IS NOT NULL
                GROUP BY metadata_->>'dataset'
                ORDER BY count(*) DESC
            """),
            {"src": IMPORT_SOURCE},
        ).fetchall()
        return [{"hf_name": r[0], "doc_count": r[1]} for r in rows]


def ensure_dataset(engine, name: str, matter_id: str) -> str:
    """Find or create a dataset by name. Returns dataset UUID."""
    from sqlalchemy import text

    with engine.connect() as conn:
        # Try to find existing
        row = conn.execute(
            text("""
                SELECT id FROM datasets
                WHERE matter_id = :mid AND name = :name AND parent_id IS NULL
            """),
            {"mid": matter_id, "name": name},
        ).first()

        if row:
            return str(row[0])

        # Create new
        row = conn.execute(
            text("""
                INSERT INTO datasets (name, description, parent_id, matter_id, created_by)
                VALUES (:name, :desc, NULL, :mid, NULL)
                ON CONFLICT (matter_id, name) WHERE parent_id IS NULL
                DO UPDATE SET updated_at = now()
                RETURNING id
            """),
            {
                "name": name,
                "desc": f"Auto-created from HF import ({name})",
                "mid": matter_id,
            },
        ).first()
        conn.commit()
        logger.info("dataset.created", name=name, id=str(row[0]))
        return str(row[0])


def count_unlinked(engine, hf_name: str, dataset_id: str) -> int:
    """Count documents with this HF dataset name not yet linked."""
    from sqlalchemy import text

    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT count(*)
                FROM documents d
                WHERE d.import_source = :src
                  AND d.metadata_->>'dataset' = :hf_name
                  AND NOT EXISTS (
                      SELECT 1 FROM dataset_documents dd
                      WHERE dd.document_id = d.id AND dd.dataset_id = :ds_id
                  )
            """),
            {"src": IMPORT_SOURCE, "hf_name": hf_name, "ds_id": dataset_id},
        ).first()
        return row[0]


def backfill_one_dataset(
    engine,
    hf_name: str,
    dataset_id: str,
    batch_size: int,
    dry_run: bool,
) -> dict:
    """Link all documents with this HF dataset name. Returns stats."""
    from sqlalchemy import text

    stats = {"hf_name": hf_name, "dataset_id": dataset_id, "inserted": 0, "batches": 0}

    if dry_run:
        stats["unlinked"] = count_unlinked(engine, hf_name, dataset_id)
        return stats

    total_inserted = 0
    batch_num = 0

    while True:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    INSERT INTO dataset_documents (dataset_id, document_id)
                    SELECT :ds_id, sub.id
                    FROM (
                        SELECT d.id
                        FROM documents d
                        WHERE d.import_source = :src
                          AND d.metadata_->>'dataset' = :hf_name
                          AND NOT EXISTS (
                              SELECT 1 FROM dataset_documents dd
                              WHERE dd.document_id = d.id AND dd.dataset_id = :ds_id
                          )
                        LIMIT :lim
                    ) sub
                    ON CONFLICT (dataset_id, document_id) DO NOTHING
                """),
                {
                    "ds_id": dataset_id,
                    "src": IMPORT_SOURCE,
                    "hf_name": hf_name,
                    "lim": batch_size,
                },
            )
            inserted = result.rowcount
            conn.commit()

        batch_num += 1
        total_inserted += inserted
        logger.info(
            "batch.complete",
            hf_name=hf_name,
            batch=batch_num,
            inserted=inserted,
            cumulative=total_inserted,
        )

        if inserted < batch_size:
            break

    stats["inserted"] = total_inserted
    stats["batches"] = batch_num
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill dataset_documents for HF imports")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help="Rows per batch")
    parser.add_argument(
        "--matter-id",
        default="00000000-0000-0000-0000-000000000002",
        help="Matter UUID for the Epstein corpus",
    )
    args = parser.parse_args()

    engine = _get_engine()
    t0 = time.time()

    # 0. Fix inflated page_count (HF page_number = Bates position, not page count)
    if not args.dry_run:
        from sqlalchemy import text as sa_text

        with engine.connect() as conn:
            result = conn.execute(
                sa_text("""
                    UPDATE documents SET page_count = 1, updated_at = now()
                    WHERE import_source = :src AND page_count != 1
                """),
                {"src": IMPORT_SOURCE},
            )
            conn.commit()
            if result.rowcount:
                logger.info("page_count.fixed", rows=result.rowcount)
            else:
                logger.info("page_count.already_correct")

    # 1. Get all HF dataset names
    hf_datasets = get_hf_dataset_names(engine)
    logger.info("found_hf_datasets", count=len(hf_datasets))

    if not hf_datasets:
        logger.info("nothing_to_do")
        return

    # 2. Optional: register with TaskTracker
    tracker = None
    total_docs = sum(d["doc_count"] for d in hf_datasets)
    if not args.dry_run:
        try:
            from scripts.lib.task_tracker import TaskTracker

            tracker = TaskTracker(
                "Dataset Documents Backfill",
                "backfill_dataset_documents.py",
                total=total_docs,
            )
        except Exception:
            logger.warning("task_tracker.unavailable")

    # 3. Process each HF dataset
    all_stats = []
    processed = 0

    for ds_info in hf_datasets:
        hf_name = ds_info["hf_name"]
        nexus_name = DATASET_NAME_MAP.get(hf_name, hf_name)

        # Find or create the dataset
        dataset_id = ensure_dataset(engine, nexus_name, args.matter_id)

        # Backfill links
        stats = backfill_one_dataset(
            engine,
            hf_name=hf_name,
            dataset_id=dataset_id,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )
        stats["nexus_name"] = nexus_name
        all_stats.append(stats)

        processed += ds_info["doc_count"]
        if tracker:
            tracker.update(processed=processed)

    # 4. Summary
    elapsed = time.time() - t0
    total_inserted = sum(s.get("inserted", 0) for s in all_stats)

    print(f"\n{'DRY RUN — ' if args.dry_run else ''}Summary:")
    print(f"  HF datasets processed: {len(all_stats)}")
    if args.dry_run:
        total_unlinked = sum(s.get("unlinked", 0) for s in all_stats)
        print(f"  Documents needing linkage: {total_unlinked:,}")
    else:
        print(f"  Rows inserted: {total_inserted:,}")
    print(f"  Elapsed: {elapsed:.1f}s")

    for s in all_stats:
        if args.dry_run:
            print(f"    {s['hf_name']} -> {s.get('nexus_name', '?')}: {s.get('unlinked', 0):,} unlinked")
        else:
            print(f"    {s['hf_name']} -> {s.get('nexus_name', '?')}: {s['inserted']:,} inserted")

    if tracker:
        tracker.complete()


if __name__ == "__main__":
    main()
