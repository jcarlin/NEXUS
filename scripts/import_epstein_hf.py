#!/usr/bin/env python3
"""Import kabasshouse/epstein-data HuggingFace dataset into NEXUS.

Uses DuckDB to read and join multi-table parquet dataset (documents,
chunks, embeddings_chunk, entities) directly from HuggingFace hub cache.
Writes to PG/Qdrant/Neo4j via async pipeline using pre-computed 768-dim
gemini-embedding-001 vectors.

No re-chunking, no re-embedding, no NER — all pre-computed.

Idempotent via content_hash — safe to re-run after interruption.

Usage::

    # Inspect dataset structure
    python scripts/import_epstein_hf.py --inspect

    # Dry run (first 100 docs)
    python scripts/import_epstein_hf.py \\
        --matter-id 00000000-0000-0000-0000-000000000002 \\
        --dry-run --limit 100

    # Full import
    python scripts/import_epstein_hf.py \\
        --matter-id 00000000-0000-0000-0000-000000000002 \\
        --disable-hnsw --resume --concurrency 32
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import structlog

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = structlog.get_logger(__name__)

HF_DATASET = "kabasshouse/epstein-data"
IMPORT_SOURCE = "kabasshouse/epstein-data"
QDRANT_BATCH_SIZE = 500
NEO4J_BATCH_SIZE = 200
ENTITY_BATCH_SIZE = 500

HF_TABLES = [
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


# ---------------------------------------------------------------------------
# DuckDB setup
# ---------------------------------------------------------------------------


def create_duckdb_conn(cache_dir: str | None = None):
    """Create a DuckDB connection with HF parquet files registered as views."""
    import duckdb
    from huggingface_hub import HfApi, hf_hub_download

    conn = duckdb.connect(":memory:")
    conn.execute("SET enable_progress_bar = false")
    api = HfApi()

    for table in HF_TABLES:
        try:
            files = list(api.list_repo_tree(HF_DATASET, repo_type="dataset", path_in_repo=f"data/{table}"))
            pq_files = [f for f in files if hasattr(f, "rfilename") and f.rfilename.endswith(".parquet")]
            if not pq_files:
                continue
            canonical = [f for f in pq_files if "-of-" in f.rfilename]
            if canonical:
                pq_files = canonical
            local_paths = []
            for f in sorted(pq_files, key=lambda x: x.rfilename):
                local = hf_hub_download(HF_DATASET, f.rfilename, repo_type="dataset", cache_dir=cache_dir)
                local_paths.append(local)
            paths_sql = ", ".join(f"'{p}'" for p in local_paths)
            conn.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet([{paths_sql}], union_by_name=true)")
            count = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            print(f"    {table}: {count:,} rows ({len(pq_files)} shards)")
        except Exception as e:
            print(f"    {table}: FAILED — {e}")

    return conn


# ---------------------------------------------------------------------------
# Inspection
# ---------------------------------------------------------------------------


def inspect_dataset() -> None:
    """Print the structure of the HF dataset repo."""
    from huggingface_hub import HfApi, hf_hub_download

    print(f"\n=== Inspecting {HF_DATASET} ===\n")
    api = HfApi()
    try:
        path = hf_hub_download(HF_DATASET, "data/export_stats.json", repo_type="dataset")
        with open(path) as f:
            stats = json.load(f)
        print("Export stats:")
        for k, v in stats.items():
            if k == "layers":
                print("  Tables:")
                for table, count in v.items():
                    print(f"    {table}: {count:,}")
            else:
                print(f"  {k}: {v}")
    except Exception as e:
        print(f"  export_stats.json: {e}")

    print("\nParquet files:")
    for table in HF_TABLES:
        try:
            files = list(api.list_repo_tree(HF_DATASET, repo_type="dataset", path_in_repo=f"data/{table}"))
            pq_files = [f for f in files if hasattr(f, "size")]
            total_size = sum(f.size for f in pq_files)
            print(f"  {table}: {len(pq_files)} files, {total_size / 1024 / 1024:.0f} MB")
        except Exception as e:
            print(f"  {table}: {e}")

    print("\nLoading via DuckDB (union_by_name for mixed schemas)...")
    conn = create_duckdb_conn()
    for table in ["documents", "chunks", "embeddings_chunk"]:
        try:
            cols = conn.execute(
                f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table}'"
            ).fetchall()
            print(f"\n  {table} schema:")
            for name, dtype in cols:
                print(f"    {name}: {dtype}")
        except Exception:
            pass
    conn.close()


# ---------------------------------------------------------------------------
# Sync DB helpers
# ---------------------------------------------------------------------------


def _get_engine():
    from sqlalchemy import create_engine

    from app.config import Settings

    settings = Settings()
    return create_engine(settings.postgres_url_sync, pool_pre_ping=True, pool_size=5)


def _get_settings():
    from app.config import Settings

    return Settings()


def check_resume(engine, content_hash: str, matter_id: str) -> bool:
    from sqlalchemy import text

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT id FROM documents WHERE content_hash = :hash AND matter_id = :mid LIMIT 1"),
            {"hash": content_hash, "mid": matter_id},
        )
        return result.first() is not None


def create_job_and_document(
    engine,
    filename: str,
    full_text: str,
    doc_type: str,
    page_count: int,
    content_hash: str,
    chunk_count: int,
    entity_count: int,
    matter_id: str,
    metadata_json: str,
    msg_id: str | None,
    in_reply: str | None,
    refs: str | None,
) -> tuple[str, str]:
    from sqlalchemy import text

    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    with engine.connect() as conn:
        conn.execute(
            text("""
            INSERT INTO jobs (id, filename, status, stage, progress, error,
                              matter_id, metadata_, created_at, updated_at)
            VALUES (:id, :filename, 'complete', 'complete', :progress, NULL,
                    :matter_id, :metadata_, now(), now())
        """),
            {
                "id": job_id,
                "filename": filename,
                "matter_id": matter_id,
                "metadata_": metadata_json,
                "progress": json.dumps({"chunks_created": chunk_count, "entities_extracted": entity_count}),
            },
        )
        conn.execute(
            text("""
            INSERT INTO documents
                (id, job_id, filename, document_type, page_count, chunk_count,
                 entity_count, minio_path, file_size_bytes, content_hash,
                 matter_id, import_source, metadata_, created_at, updated_at,
                 message_id, in_reply_to, references_)
            VALUES
                (:id, :job_id, :filename, :doc_type, :page_count, :chunk_count,
                 :entity_count, :minio_path, :file_size, :content_hash,
                 :matter_id, :import_source, :metadata_, now(), now(),
                 :message_id, :in_reply_to, :references_)
        """),
            {
                "id": doc_id,
                "job_id": job_id,
                "filename": filename,
                "doc_type": doc_type,
                "page_count": page_count,
                "chunk_count": chunk_count,
                "entity_count": entity_count,
                "minio_path": f"raw/{job_id}/{filename}",
                "file_size": len(full_text.encode("utf-8")),
                "content_hash": content_hash,
                "matter_id": matter_id,
                "import_source": IMPORT_SOURCE,
                "metadata_": metadata_json,
                "message_id": msg_id,
                "in_reply_to": in_reply,
                "references_": refs,
            },
        )
        conn.commit()
    return job_id, doc_id


# ---------------------------------------------------------------------------
# MinIO / HNSW helpers
# ---------------------------------------------------------------------------


def upload_to_minio(settings, key: str, data: bytes) -> None:
    import boto3
    from botocore.config import Config as BotoConfig

    scheme = "https" if settings.minio_use_ssl else "http"
    client = boto3.client(
        "s3",
        endpoint_url=f"{scheme}://{settings.minio_endpoint}",
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )
    client.put_object(Bucket=settings.minio_bucket, Key=key, Body=data, ContentType="text/plain")


def disable_hnsw(settings) -> None:
    from app.common.vector_store import TEXT_COLLECTION, VectorStoreClient

    VectorStoreClient(settings).disable_hnsw_indexing(TEXT_COLLECTION)
    print("  HNSW indexing disabled")


def rebuild_hnsw(settings) -> None:
    from app.common.vector_store import TEXT_COLLECTION, VectorStoreClient

    VectorStoreClient(settings).rebuild_hnsw_index(TEXT_COLLECTION)
    print("  HNSW rebuild triggered (background)")


def detect_named_vectors(settings) -> bool:
    from qdrant_client import QdrantClient

    from app.common.vector_store import TEXT_COLLECTION

    try:
        info = QdrantClient(url=settings.qdrant_url).get_collection(TEXT_COLLECTION)
        return isinstance(info.config.params.vectors, dict)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Async pipeline — pre-joined DuckDB → PG/Qdrant/Neo4j
# ---------------------------------------------------------------------------


async def run_pipeline(
    conn,
    engine,
    settings,
    matter_id: str,
    limit: int | None,
    resume: bool,
    skip_minio: bool,
    skip_neo4j: bool,
    use_named_vectors: bool,
    concurrency: int,
    dry_run: bool,
) -> tuple[int, int, int]:
    """Pre-join in DuckDB, stream grouped rows, write to all stores.

    Returns (imported, skipped, total_chunks).
    """
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import PointStruct

    from app.common.vector_store import TEXT_COLLECTION

    doc_count_raw = conn.execute(
        "SELECT count(*) FROM documents WHERE full_text IS NOT NULL AND length(trim(full_text)) >= 10"
    ).fetchone()[0]
    doc_count = min(doc_count_raw, limit) if limit else doc_count_raw
    print(f"\n  Eligible documents: {doc_count:,}")

    if dry_run:
        dist = conn.execute("""
            SELECT dataset, count(*) as cnt FROM documents
            WHERE full_text IS NOT NULL AND length(trim(full_text)) >= 10
            GROUP BY dataset ORDER BY cnt DESC
        """).fetchall()
        print("\n  Dataset distribution:")
        for label, cnt in dist:
            print(f"    {label}: {cnt:,}")
        print(f"\n  [DRY RUN] Would import {doc_count:,} documents")
        return doc_count, 0, 0

    # Pre-join: one query, ordered by doc id for streaming group-by
    print("  Executing pre-join (documents + chunks + embeddings)...")
    t0 = time.time()
    result = conn.execute("""
        SELECT
            d.id AS doc_int_id, d.file_key, d.full_text, d.document_type,
            d.date, d.dataset, d.is_photo, d.has_handwriting, d.has_stamps,
            d.ocr_source, d.additional_notes, d.page_number,
            d.document_number, d.email_fields,
            c.chunk_index, c.content AS chunk_content,
            c.token_count AS chunk_tokens, e.embedding
        FROM documents d
        JOIN chunks c ON c.document_id = d.id
        JOIN embeddings_chunk e ON e.chunk_id = c.id
        WHERE d.full_text IS NOT NULL AND length(trim(d.full_text)) >= 10
          AND c.content IS NOT NULL AND e.embedding IS NOT NULL
        ORDER BY d.id, c.chunk_index
    """)
    print(f"  Pre-join executed in {time.time() - t0:.1f}s")

    # Entity index: streamed into memory
    print("  Loading entity index...")
    t0 = time.time()
    entity_map: dict[int, list[dict]] = {}
    ent_res = conn.execute(
        "SELECT document_id, entity_type, value, normalized_value FROM entities ORDER BY document_id"
    )
    while True:
        batch = ent_res.fetchmany(100_000)
        if not batch:
            break
        for did, etype, val, norm in batch:
            if not val or not str(val).strip():
                continue
            if did not in entity_map:
                entity_map[did] = []
            entity_map[did].append({"name": str(norm or val).strip(), "type": str(etype or "unknown").lower()})
    print(
        f"  Entities: {sum(len(v) for v in entity_map.values()):,} for {len(entity_map):,} docs ({time.time() - t0:.1f}s)"
    )

    # Async clients
    qdrant = AsyncQdrantClient(url=settings.qdrant_url)
    neo4j_driver = None
    if not skip_neo4j:
        from neo4j import AsyncGraphDatabase

        neo4j_driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
        )

    imported = 0
    skipped = 0
    total_chunks = 0
    docs_seen = 0
    start_time = time.time()

    # Group-by state
    cur_id: int | None = None
    cur_meta: dict[str, Any] = {}
    cur_chunks: list[tuple[str, int, int, list[float]]] = []

    async def _flush():
        nonlocal imported, skipped, total_chunks
        if not cur_chunks:
            skipped += 1
            return
        m = cur_meta
        fk = m["file_key"]
        ft = m["full_text"]
        fn = fk.split("/")[-1] if "/" in fk else fk
        ch = hashlib.sha256(ft.encode("utf-8")).hexdigest()[:16]
        if resume and check_resume(engine, ch, matter_id):
            skipped += 1
            return
        ents = entity_map.get(cur_id, [])
        meta: dict[str, Any] = {"dataset": str(m.get("dataset") or ""), "original_file_key": fk}
        for f in ("date", "document_number", "ocr_source", "additional_notes"):
            if m.get(f):
                meta[f] = str(m[f])
        for bf in ("is_photo", "has_handwriting", "has_stamps"):
            if m.get(bf):
                meta[bf] = True
        mj = json.dumps(meta, default=str)
        mid = irp = rfs = None
        ef = m.get("email_fields")
        if ef and str(ef).strip():
            try:
                eh = json.loads(str(ef))
                mid, irp, rfs = eh.get("message_id"), eh.get("in_reply_to"), eh.get("references")
            except (json.JSONDecodeError, TypeError):
                pass
        dt = str(m.get("document_type") or "document")
        pn = m.get("page_number")
        pc = int(pn) if pn and str(pn).isdigit() else 1

        jid, did = create_job_and_document(
            engine, fn, ft, dt, pc, ch, len(cur_chunks), len(ents), matter_id, mj, mid, irp, rfs
        )

        if not skip_minio:
            await asyncio.to_thread(upload_to_minio, settings, f"raw/{jid}/{fn}", ft.encode("utf-8"))

        pts: list[PointStruct] = []
        pids: list[str] = []
        for txt, ci, tc, emb in cur_chunks:
            pid = str(uuid.uuid4())
            pids.append(pid)
            vec: Any = {"dense": emb} if use_named_vectors else emb
            pts.append(
                PointStruct(
                    id=pid,
                    vector=vec,
                    payload={
                        "source_file": fk,
                        "chunk_text": txt,
                        "chunk_index": ci,
                        "doc_id": did,
                        "matter_id": matter_id,
                        "token_count": tc,
                    },
                )
            )
        for i in range(0, len(pts), QDRANT_BATCH_SIZE):
            await qdrant.upsert(collection_name=TEXT_COLLECTION, points=pts[i : i + QDRANT_BATCH_SIZE])

        if neo4j_driver:
            async with neo4j_driver.session() as sess:
                await sess.run(
                    "MERGE (doc:Document {id: $did}) SET doc.filename=$fn, doc.doc_type=$dt, doc.page_count=$pc, doc.matter_id=$mid",
                    did=did,
                    fn=fn,
                    dt=dt,
                    pc=pc,
                    mid=matter_id,
                )
                cnodes = [{"cid": p, "tp": t[:200], "pn": 1, "qp": p} for p, (t, *_) in zip(pids, cur_chunks)]
                for i in range(0, len(cnodes), NEO4J_BATCH_SIZE):
                    await sess.run(
                        "UNWIND $cs AS c MERGE (k:Chunk {id:c.cid}) SET k.text_preview=c.tp, k.page_number=c.pn, k.qdrant_point_id=c.qp WITH k,c MATCH (d:Document {id:$did}) MERGE (d)-[:HAS_CHUNK]->(k)",
                        cs=cnodes[i : i + NEO4J_BATCH_SIZE],
                        did=did,
                    )
                if ents:
                    for i in range(0, len(ents), ENTITY_BATCH_SIZE):
                        await sess.run(
                            "UNWIND $es AS e MERGE (n:Entity {name:e.name, type:e.type, matter_id:$mid}) ON CREATE SET n.first_seen=datetime(), n.mention_count=1 ON MATCH SET n.mention_count=n.mention_count+1 WITH n MATCH (d:Document {id:$did}) MERGE (n)-[:MENTIONED_IN]->(d)",
                            es=ents[i : i + ENTITY_BATCH_SIZE],
                            mid=matter_id,
                            did=did,
                        )
        imported += 1
        total_chunks += len(cur_chunks)

    try:
        while True:
            rows = result.fetchmany(5000)
            if not rows:
                break
            for row in rows:
                (did, fk, ft, dty, dt, ds, ip, hw, st, oc, an, pn, dn, ef, ci, cc, ct, emb) = row
                if did != cur_id:
                    if cur_id is not None:
                        await _flush()
                        docs_seen += 1
                        if limit and docs_seen >= limit:
                            break
                    cur_id = did
                    cur_meta = {
                        "file_key": str(fk or ""),
                        "full_text": str(ft or ""),
                        "document_type": dty,
                        "date": dt,
                        "dataset": ds,
                        "is_photo": ip,
                        "has_handwriting": hw,
                        "has_stamps": st,
                        "ocr_source": oc,
                        "additional_notes": an,
                        "page_number": pn,
                        "document_number": dn,
                        "email_fields": ef,
                    }
                    cur_chunks = []
                if emb is not None and cc:
                    el = list(emb) if hasattr(emb, "__iter__") else []
                    if el:
                        cur_chunks.append((str(cc), int(ci or 0), int(ct or len(str(cc).split())), el))

            if imported > 0 and imported % 500 < 100:
                elapsed = time.time() - start_time
                rate = imported / elapsed if elapsed > 0 else 0
                eta = (doc_count - imported - skipped) / rate / 60 if rate > 0 else 0
                print(
                    f"  [{imported:,}/{doc_count:,}] {total_chunks:,} chunks, {skipped:,} skip, {rate:.1f} docs/s, ETA {eta:.0f}m"
                )

            if limit and docs_seen >= limit:
                break

        if cur_id is not None:
            await _flush()

    except KeyboardInterrupt:
        print(f"\n  Interrupted at {imported:,} docs.")
    finally:
        await qdrant.close()
        if neo4j_driver:
            await neo4j_driver.close()

    return imported, skipped, total_chunks


# ---------------------------------------------------------------------------
# KG import
# ---------------------------------------------------------------------------


def import_kg(conn, settings, matter_id: str) -> None:
    """Import curated KG entities + relationships directly to Neo4j."""
    from neo4j import GraphDatabase

    kg_count = conn.execute("SELECT count(*) FROM kg_entities").fetchone()[0]
    rel_count = conn.execute("SELECT count(*) FROM kg_relationships").fetchone()[0]
    print(f"\n  Importing KG: {kg_count} entities, {rel_count} relationships")

    driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    with driver.session() as session:
        rows = conn.execute("SELECT id, name, entity_type, description FROM kg_entities").fetchall()
        batch = [
            {"name": str(n), "type": str(t or "unknown").lower(), "description": str(d or "")} for _, n, t, d in rows
        ]
        if batch:
            session.run(
                "UNWIND $entities AS e MERGE (ent:Entity {name: e.name, type: e.type, matter_id: $mid}) SET ent.description = e.description, ent.kg_curated = true",
                entities=batch,
                mid=matter_id,
            )
        kg_map = {int(i): str(n) for i, n, _, _ in rows}
        rels = conn.execute(
            "SELECT source_id, target_id, relationship_type, weight, evidence FROM kg_relationships"
        ).fetchall()
        rb = []
        for si, ti, rt, w, ev in rels:
            s, t = kg_map.get(int(si), ""), kg_map.get(int(ti), "")
            if s and t:
                rb.append(
                    {
                        "source": s,
                        "target": t,
                        "rel_type": str(rt or "RELATED_TO"),
                        "weight": float(w or 1.0),
                        "evidence": str(ev or ""),
                    }
                )
        for i in range(0, len(rb), 200):
            session.run(
                "UNWIND $rels AS r MATCH (s:Entity {name:r.source, matter_id:$mid}) MATCH (t:Entity {name:r.target, matter_id:$mid}) MERGE (s)-[rel:RELATED_TO]->(t) SET rel.relationship_type=r.rel_type, rel.weight=r.weight, rel.evidence=r.evidence, rel.kg_curated=true",
                rels=rb[i : i + 200],
                mid=matter_id,
            )
    driver.close()
    print(f"  KG complete: {kg_count} entities, {rel_count} relationships")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:  # noqa: C901
    parser = argparse.ArgumentParser(description="Import kabasshouse/epstein-data into NEXUS (DuckDB + async)")
    parser.add_argument("--matter-id", default=None, help="Target matter UUID")
    parser.add_argument("--limit", type=int, default=None, help="Import first N documents only")
    parser.add_argument("--inspect", action="store_true", help="Inspect HF dataset structure and exit")
    parser.add_argument("--dry-run", action="store_true", help="Load + count, no writes")
    parser.add_argument("--resume", action="store_true", help="Skip docs whose content_hash exists")
    parser.add_argument("--disable-hnsw", action="store_true", help="Disable HNSW during import, rebuild after")
    parser.add_argument("--skip-minio", action="store_true", help="Skip MinIO text upload")
    parser.add_argument("--skip-neo4j", action="store_true", help="Skip Neo4j graph writes")
    parser.add_argument("--skip-kg", action="store_true", help="Skip KG entity/relationship import")
    parser.add_argument("--cache-dir", default=None, help="HF datasets cache directory")
    parser.add_argument("--concurrency", type=int, default=16, help="Documents per fetch batch (default: 16)")
    args = parser.parse_args()

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

    print(f"\n=== NEXUS HF Import: {HF_DATASET} (DuckDB + async) ===")
    print(f"  Matter:      {args.matter_id}")
    print(f"  Concurrency: {args.concurrency}")
    if args.limit:
        print(f"  Limit:       {args.limit}")

    print("\n  Registering HF parquet tables in DuckDB...")
    conn = create_duckdb_conn(args.cache_dir)
    settings = _get_settings()
    engine = _get_engine()
    use_named = detect_named_vectors(settings)
    print(f"  Named vectors: {use_named}")

    if args.disable_hnsw and not args.dry_run:
        disable_hnsw(settings)

    start_time = time.time()
    imported, skipped_count, total_chunks = asyncio.run(
        run_pipeline(
            conn=conn,
            engine=engine,
            settings=settings,
            matter_id=args.matter_id,
            limit=args.limit,
            resume=args.resume,
            skip_minio=args.skip_minio,
            skip_neo4j=args.skip_neo4j,
            use_named_vectors=use_named,
            concurrency=args.concurrency,
            dry_run=args.dry_run,
        )
    )

    if args.disable_hnsw and not args.dry_run:
        rebuild_hnsw(settings)
    if not args.skip_kg and not args.dry_run:
        import_kg(conn, settings, args.matter_id)
    conn.close()

    if imported > 0 and not args.dry_run:
        print("\n  Dispatching post-ingestion hooks...")
        try:
            from app.ingestion.bulk_import import dispatch_post_ingestion_hooks

            hooks = dispatch_post_ingestion_hooks(args.matter_id)
            print(f"  Dispatched: {', '.join(hooks) or 'none'}")
        except Exception:
            logger.warning("post_ingestion.hooks_failed", exc_info=True)

    elapsed = time.time() - start_time
    print("\n=== Import Complete ===")
    print(f"  Imported:     {imported:,}")
    print(f"  Skipped:      {skipped_count:,}")
    print(f"  Total chunks: {total_chunks:,}")
    print(f"  Elapsed:      {elapsed:.1f}s ({elapsed / 60:.1f}min)")
    if imported > 0 and elapsed > 0:
        print(f"  Rate:         {imported / elapsed:.1f} docs/sec ({total_chunks / elapsed:.0f} chunks/sec)")

    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
