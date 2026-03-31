#!/usr/bin/env python3
"""Import kabasshouse/epstein-data HuggingFace dataset into NEXUS via Celery.

Downloads multi-table parquet dataset (documents, chunks, embeddings_chunk,
entities), joins by integer ID, and dispatches import_text_document tasks
to Celery workers with pre_chunks + pre_embeddings + pre_entities.

Workers handle: MinIO upload, Qdrant upsert (pre-computed 768-dim dense),
Neo4j graph writes, PG finalization. No re-chunking, no re-embedding,
no NER — all pre-computed by the HF dataset.

Idempotent via content_hash — safe to re-run after interruption.

Usage::

    # Inspect dataset structure
    python scripts/import_epstein_hf.py --inspect

    # Dry run — count + schema preview
    python scripts/import_epstein_hf.py \\
        --matter-id 00000000-0000-0000-0000-000000000002 \\
        --dry-run --limit 100

    # Full import (dispatches 1.4M tasks to Celery bulk queue)
    python scripts/import_epstein_hf.py \\
        --matter-id 00000000-0000-0000-0000-000000000002 \\
        --disable-hnsw --resume
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import structlog

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingestion.bulk_import import (
    _get_sync_engine,
    check_resume,
    create_bulk_import_job,
    create_job_row,
    dispatch_post_ingestion_hooks,
    increment_skipped,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HF_DATASET = "kabasshouse/epstein-data"
IMPORT_SOURCE = "kabasshouse/epstein-data"
DISPATCH_BATCH_LOG = 500  # Log progress every N dispatched docs


# ---------------------------------------------------------------------------
# HF dataset inspection
# ---------------------------------------------------------------------------


def inspect_dataset() -> None:
    """Print the structure of the HF dataset repo."""
    from huggingface_hub import HfApi, hf_hub_download

    print(f"\n=== Inspecting {HF_DATASET} ===\n")

    api = HfApi()

    # Read export stats
    try:
        path = hf_hub_download(HF_DATASET, "data/export_stats.json", repo_type="dataset")
        with open(path) as f:
            stats = json.load(f)
        print("Export stats:")
        for k, v in stats.items():
            if k == "layers":
                print("  Tables:")
                for table, count in v.items():
                    print(f"    {table}: {count:,} rows")
            else:
                print(f"  {k}: {v}")
    except Exception as e:
        print(f"  export_stats.json: {e}")

    # List data dirs and sizes
    print("\nParquet files:")
    tables = [
        "documents",
        "chunks",
        "embeddings_chunk",
        "entities",
        "kg_entities",
        "kg_relationships",
        "persons",
        "financial_transactions",
        "recovered_redactions",
        "curated_docs",
    ]
    for table in tables:
        try:
            files = list(api.list_repo_tree(HF_DATASET, repo_type="dataset", path_in_repo=f"data/{table}"))
            pq_files = [f for f in files if hasattr(f, "size")]
            total_size = sum(f.size for f in pq_files)
            print(f"  {table}: {len(pq_files)} files, {total_size / 1024 / 1024:.0f} MB")
        except Exception as e:
            print(f"  {table}: {e}")

    # Sample columns from key tables
    import pandas as pd

    for table in ["documents", "chunks", "embeddings_chunk"]:
        try:
            files = list(api.list_repo_tree(HF_DATASET, repo_type="dataset", path_in_repo=f"data/{table}"))
            first = [f for f in files if hasattr(f, "rfilename")][0]
            path = hf_hub_download(HF_DATASET, first.rfilename, repo_type="dataset")
            df = pd.read_parquet(path)
            print(f"\n  {table} columns: {list(df.columns)}")
            if table == "embeddings_chunk" and "embedding" in df.columns:
                emb = df.iloc[0]["embedding"]
                print(f"  embedding type={type(emb).__name__}, shape={getattr(emb, 'shape', len(emb))}")
        except Exception as e:
            print(f"  {table}: {e}")


# ---------------------------------------------------------------------------
# Parquet loading helpers
# ---------------------------------------------------------------------------


def download_parquet_table(table_name: str, cache_dir: str | None = None) -> list[Path]:
    """Download all parquet files for a table. Returns list of local paths."""
    from huggingface_hub import HfApi, hf_hub_download

    api = HfApi()
    files = list(api.list_repo_tree(HF_DATASET, repo_type="dataset", path_in_repo=f"data/{table_name}"))
    pq_files = sorted(
        [f for f in files if hasattr(f, "rfilename") and f.rfilename.endswith(".parquet")],
        key=lambda x: x.rfilename,
    )

    paths = []
    for f in pq_files:
        local = hf_hub_download(HF_DATASET, f.rfilename, repo_type="dataset", cache_dir=cache_dir)
        paths.append(Path(local))

    return paths


def _safe_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        v = int(val)
        return v if v == v else None  # NaN check
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Core: streaming dispatch
# ---------------------------------------------------------------------------


def stream_and_dispatch(
    engine,
    matter_id: str,
    bulk_job_id: str,
    cache_dir: str | None = None,
    limit: int | None = None,
    resume: bool = False,
    dry_run: bool = False,
    queue: str = "bulk",
) -> tuple[int, int, int]:
    """Stream through HF parquet shards, join data, dispatch Celery tasks.

    Processes one documents shard at a time to limit memory usage.
    For each document: joins its chunks + embeddings + entities, then
    dispatches import_text_document with pre_chunks + pre_embeddings.

    Returns (dispatched, skipped, failed).
    """
    import numpy as np
    import pandas as pd

    from app.ingestion.tasks import import_text_document

    # Download parquet file paths (HF hub caches locally)
    print("\n  Downloading parquet file lists...")
    doc_paths = download_parquet_table("documents", cache_dir)
    chunk_paths = download_parquet_table("chunks", cache_dir)
    emb_paths = download_parquet_table("embeddings_chunk", cache_dir)
    print(f"    documents: {len(doc_paths)} shards")
    print(f"    chunks: {len(chunk_paths)} shards")
    print(f"    embeddings: {len(emb_paths)} shards")

    # Load ALL chunks into a map: chunks.id → (document_id, chunk_index, content, token_count)
    # 2.2M rows × ~50 bytes metadata = ~110MB. Manageable.
    print("\n  Loading chunks index...")
    chunk_map: dict[int, tuple[int, int, str, int]] = {}
    for cp in chunk_paths:
        cdf = pd.read_parquet(cp)
        for _, row in cdf.iterrows():
            content = str(row.get("content", ""))
            if not content.strip():
                continue
            chunk_map[int(row["id"])] = (
                int(row["document_id"]),
                int(row.get("chunk_index", 0)),
                content,
                int(row.get("token_count", 0)) or len(content.split()),
            )
        del cdf
    print(f"    {len(chunk_map):,} chunks indexed")

    # Load ALL embeddings into a map: chunk_id → embedding (numpy array)
    # 2.1M × 768 × 4 bytes = ~6.4GB. This is the big memory consumer.
    # We keep as numpy arrays until dispatch (no list conversion until needed).
    print("\n  Loading embeddings index...")
    emb_map: dict[int, np.ndarray] = {}
    for ep in emb_paths:
        edf = pd.read_parquet(ep)
        for _, row in edf.iterrows():
            chunk_id = int(row["chunk_id"])
            if chunk_id in chunk_map:
                embedding = row.get("embedding")
                if embedding is not None:
                    emb_map[chunk_id] = np.asarray(embedding, dtype=np.float32)
        del edf
    print(f"    {len(emb_map):,} embeddings indexed")

    # Load entities into a map: document_id → list of entity dicts
    print("\n  Loading entities index...")
    entity_paths = download_parquet_table("entities", cache_dir)
    entity_map: dict[int, list[dict]] = {}
    for ep in entity_paths:
        edf = pd.read_parquet(ep)
        for _, row in edf.iterrows():
            doc_id = int(row["document_id"])
            entity_type = str(row.get("entity_type", "unknown")).lower()
            value = str(row.get("value", ""))
            normalized = str(row.get("normalized_value", "")) or value
            if not value.strip():
                continue
            if doc_id not in entity_map:
                entity_map[doc_id] = []
            entity_map[doc_id].append(
                {
                    "name": normalized.strip() or value.strip(),
                    "type": entity_type,
                }
            )
        del edf
    total_entities = sum(len(v) for v in entity_map.values())
    print(f"    {total_entities:,} entities for {len(entity_map):,} documents")

    # Group chunk_map by document_id for fast lookup
    doc_chunks: dict[int, list[int]] = {}  # document_id → [chunk_id, ...]
    for chunk_id, (doc_id, *_) in chunk_map.items():
        if doc_id not in doc_chunks:
            doc_chunks[doc_id] = []
        doc_chunks[doc_id].append(chunk_id)

    # Stream through document shards and dispatch
    print("\n  Dispatching tasks...")
    dispatched = 0
    skipped = 0
    failed = 0
    total_docs_seen = 0
    start_time = time.time()

    for dp in doc_paths:
        ddf = pd.read_parquet(dp)

        for _, doc_row in ddf.iterrows():
            if limit and total_docs_seen >= limit:
                break

            total_docs_seen += 1

            doc_int_id = int(doc_row["id"])
            file_key = str(doc_row.get("file_key", ""))
            full_text = str(doc_row.get("full_text", "")) if pd.notna(doc_row.get("full_text")) else ""

            if not full_text or len(full_text.strip()) < 10:
                skipped += 1
                increment_skipped(engine, bulk_job_id)
                continue

            # Content hash for dedup
            content_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()[:16]

            if resume and check_resume(engine, content_hash, matter_id):
                skipped += 1
                increment_skipped(engine, bulk_job_id)
                continue

            # Build pre_chunks + pre_embeddings from joined data
            chunk_ids = doc_chunks.get(doc_int_id, [])
            pre_chunks: list[dict] = []
            pre_embeddings: list[list[float]] = []

            for cid in sorted(chunk_ids, key=lambda c: chunk_map[c][1]):  # sort by chunk_index
                if cid not in emb_map:
                    continue
                doc_id, chunk_index, content, token_count = chunk_map[cid]
                pre_chunks.append(
                    {
                        "text": content,
                        "chunk_index": chunk_index,
                        "token_count": token_count,
                    }
                )
                pre_embeddings.append(emb_map[cid].tolist())

            if not pre_chunks:
                skipped += 1
                increment_skipped(engine, bulk_job_id)
                continue

            # Build pre_entities
            pre_entities = entity_map.get(doc_int_id)

            # Build metadata
            metadata: dict[str, Any] = {
                "dataset": str(doc_row.get("dataset", "")) if pd.notna(doc_row.get("dataset")) else "",
                "original_file_key": file_key,
            }
            for field in ("date", "document_number", "ocr_source", "additional_notes"):
                val = doc_row.get(field)
                if pd.notna(val) and str(val).strip():
                    metadata[field] = str(val)
            for bool_field in ("is_photo", "has_handwriting", "has_stamps"):
                if doc_row.get(bool_field):
                    metadata[bool_field] = True

            # Parse email headers
            email_headers = None
            raw_email = doc_row.get("email_fields")
            if pd.notna(raw_email) and isinstance(raw_email, str) and raw_email.strip():
                try:
                    email_headers = json.loads(raw_email)
                except (json.JSONDecodeError, TypeError):
                    pass

            filename = file_key.split("/")[-1] if "/" in file_key else file_key
            doc_type = (
                str(doc_row.get("document_type", "document")) if pd.notna(doc_row.get("document_type")) else "document"
            )
            page_count = _safe_int(doc_row.get("page_number")) or 1

            if dry_run:
                dispatched += 1
                if dispatched % DISPATCH_BATCH_LOG == 0:
                    print(f"  [dry-run] {dispatched:,} would be dispatched, {skipped:,} skipped")
                continue

            # Create job row
            job_id = str(uuid.uuid4())
            create_job_row(engine, job_id, filename, matter_id, bulk_import_job_id=bulk_job_id)

            # Dispatch Celery task
            try:
                import_text_document.apply_async(
                    kwargs={
                        "job_id": job_id,
                        "text": full_text,
                        "filename": filename,
                        "content_hash": content_hash,
                        "matter_id": matter_id,
                        "doc_type": doc_type,
                        "page_count": page_count,
                        "metadata": metadata,
                        "pre_entities": pre_entities,
                        "import_source": IMPORT_SOURCE,
                        "bulk_import_job_id": bulk_job_id,
                        "email_headers": email_headers,
                        "pre_chunks": pre_chunks,
                        "pre_embeddings": pre_embeddings,
                    },
                    queue=queue,
                )
                dispatched += 1
            except Exception as e:
                logger.error("dispatch.failed", filename=filename, error=str(e))
                failed += 1

            if dispatched % DISPATCH_BATCH_LOG == 0:
                elapsed = time.time() - start_time
                rate = dispatched / elapsed if elapsed > 0 else 0
                remaining = (limit or 1_500_000) - total_docs_seen
                eta_min = (remaining / rate / 60) if rate > 0 else 0
                print(f"  [{dispatched:,} dispatched, {skipped:,} skipped] {rate:.0f} docs/sec, ETA {eta_min:.0f}min")

        del ddf

        if limit and total_docs_seen >= limit:
            break

    return dispatched, skipped, failed


# ---------------------------------------------------------------------------
# KG import (direct, not via Celery — small tables)
# ---------------------------------------------------------------------------


def import_kg_direct(engine, matter_id: str, cache_dir: str | None = None) -> None:
    """Import KG entities + relationships directly to Neo4j (small tables)."""
    import pandas as pd

    from app.config import Settings

    settings = Settings()

    kg_ent_paths = download_parquet_table("kg_entities", cache_dir)
    kg_rel_paths = download_parquet_table("kg_relationships", cache_dir)

    if not kg_ent_paths:
        print("  No KG tables found, skipping.")
        return

    kg_entities = pd.concat([pd.read_parquet(p) for p in kg_ent_paths], ignore_index=True)
    kg_rels = pd.concat([pd.read_parquet(p) for p in kg_rel_paths], ignore_index=True)
    print(f"\n  Importing KG: {len(kg_entities)} entities, {len(kg_rels)} relationships")

    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

    with driver.session() as session:
        # Import KG entities with descriptions
        batch = []
        for _, row in kg_entities.iterrows():
            batch.append(
                {
                    "name": str(row.get("name", "")),
                    "type": str(row.get("entity_type", "unknown")).lower(),
                    "description": str(row.get("description", "")) if pd.notna(row.get("description")) else "",
                }
            )

        if batch:
            session.run(
                """
                UNWIND $entities AS e
                MERGE (ent:Entity {name: e.name, type: e.type, matter_id: $matter_id})
                SET ent.description = e.description,
                    ent.kg_curated = true
                """,
                entities=batch,
                matter_id=matter_id,
            )

        # Build kg_entity id → name map for relationship import
        kg_id_to_name: dict[int, str] = {}
        for _, row in kg_entities.iterrows():
            kg_id_to_name[int(row["id"])] = str(row.get("name", ""))

        # Import KG relationships
        rel_batch = []
        for _, row in kg_rels.iterrows():
            source_name = kg_id_to_name.get(int(row.get("source_id", -1)), "")
            target_name = kg_id_to_name.get(int(row.get("target_id", -1)), "")
            if not source_name or not target_name:
                continue
            rel_batch.append(
                {
                    "source": source_name,
                    "target": target_name,
                    "rel_type": str(row.get("relationship_type", "RELATED_TO")),
                    "weight": float(row.get("weight", 1.0)) if pd.notna(row.get("weight")) else 1.0,
                    "evidence": str(row.get("evidence", "")) if pd.notna(row.get("evidence")) else "",
                }
            )

        if rel_batch:
            for i in range(0, len(rel_batch), 200):
                chunk = rel_batch[i : i + 200]
                session.run(
                    """
                    UNWIND $rels AS r
                    MATCH (s:Entity {name: r.source, matter_id: $matter_id})
                    MATCH (t:Entity {name: r.target, matter_id: $matter_id})
                    MERGE (s)-[rel:RELATED_TO]->(t)
                    SET rel.relationship_type = r.rel_type,
                        rel.weight = r.weight,
                        rel.evidence = r.evidence,
                        rel.kg_curated = true
                    """,
                    rels=chunk,
                    matter_id=matter_id,
                )

    driver.close()
    print(f"  KG import complete: {len(kg_entities)} entities, {len(kg_rels)} relationships")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:  # noqa: C901
    parser = argparse.ArgumentParser(
        description="Import kabasshouse/epstein-data via Celery workers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--matter-id", default=None, help="Target matter UUID")
    parser.add_argument("--limit", type=int, default=None, help="Import first N documents only")
    parser.add_argument("--inspect", action="store_true", help="Inspect HF dataset structure and exit")
    parser.add_argument("--dry-run", action="store_true", help="Count + preview, no Celery dispatch")
    parser.add_argument("--resume", action="store_true", help="Skip docs whose content_hash exists")
    parser.add_argument("--disable-hnsw", action="store_true", help="Disable HNSW during import, rebuild after")
    parser.add_argument("--cache-dir", default=None, help="HF datasets cache directory")
    parser.add_argument("--queue", default="bulk", help="Celery queue for task dispatch (default: bulk)")
    parser.add_argument("--skip-kg", action="store_true", help="Skip KG entity/relationship import")

    args = parser.parse_args()

    # Inspect mode (no matter-id required)
    if args.inspect:
        inspect_dataset()
        return 0

    if not args.matter_id:
        print("Error: --matter-id is required", file=sys.stderr)
        return 1

    try:
        uuid.UUID(args.matter_id)
    except ValueError:
        print(f"Error: '{args.matter_id}' is not a valid UUID", file=sys.stderr)
        return 1

    print(f"\n=== NEXUS HF Import: {HF_DATASET} ===")
    print(f"  Matter:  {args.matter_id}")
    print(f"  Queue:   {args.queue}")
    if args.limit:
        print(f"  Limit:   {args.limit} documents")
    if args.dry_run:
        print("  Mode:    DRY RUN")

    # Setup
    engine = _get_sync_engine()

    # Disable HNSW if requested
    qdrant_client = None
    if args.disable_hnsw and not args.dry_run:
        from app.common.vector_store import TEXT_COLLECTION, VectorStoreClient
        from app.config import Settings

        settings = Settings()
        qdrant_client = VectorStoreClient(settings)
        print("  Disabling HNSW indexing for bulk insert...")
        qdrant_client.disable_hnsw_indexing(TEXT_COLLECTION)

    # Create bulk import job (even for dry run, for counting)
    bulk_job_id = create_bulk_import_job(
        engine,
        args.matter_id,
        "epstein_hf",
        HF_DATASET,
        1_424_673,
    )
    print(f"  Bulk import job: {bulk_job_id}")

    # Stream + dispatch
    start_time = time.time()
    dispatched, skipped, failed = stream_and_dispatch(
        engine=engine,
        matter_id=args.matter_id,
        bulk_job_id=bulk_job_id,
        cache_dir=args.cache_dir,
        limit=args.limit,
        resume=args.resume,
        dry_run=args.dry_run,
        queue=args.queue,
    )

    # Import KG (small, direct to Neo4j)
    if not args.skip_kg and not args.dry_run:
        import_kg_direct(engine, args.matter_id, args.cache_dir)

    # Rebuild HNSW if disabled
    if args.disable_hnsw and qdrant_client and not args.dry_run:
        from app.common.vector_store import TEXT_COLLECTION

        print("\n  Rebuilding HNSW index (background)...")
        qdrant_client.rebuild_hnsw_index(TEXT_COLLECTION)

    # Post-ingestion hooks
    if dispatched > 0 and not args.dry_run:
        print("\n  Dispatching post-ingestion hooks...")
        try:
            hooks = dispatch_post_ingestion_hooks(args.matter_id)
            print(f"  Dispatched: {', '.join(hooks) or 'none'}")
        except Exception:
            logger.warning("post_ingestion.hooks_failed", exc_info=True)

    # Summary
    elapsed = time.time() - start_time
    prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"\n=== {prefix}Import Summary ===")
    print(f"  Bulk job:    {bulk_job_id}")
    print(f"  Dispatched:  {dispatched:,}")
    print(f"  Skipped:     {skipped:,}")
    print(f"  Failed:      {failed:,}")
    print(f"  Elapsed:     {elapsed:.1f}s ({elapsed / 60:.1f}min)")
    if dispatched > 0 and elapsed > 0:
        print(f"  Rate:        {dispatched / elapsed:.0f} docs/sec")

    if not args.dry_run:
        print("\n  Tasks are now processing in Celery workers.")
        print("  Monitor progress: Pipeline Monitor > Bulk Jobs or")
        print("    SELECT processed_documents, failed_documents, total_documents")
        print(f"    FROM bulk_import_jobs WHERE id = '{bulk_job_id}';")

    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
