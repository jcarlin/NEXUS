#!/usr/bin/env python3
"""Import kabasshouse/epstein-data HuggingFace dataset into NEXUS.

Uses DuckDB to read multi-table parquet (handles mixed schemas via
union_by_name), loads chunk+embedding+entity indexes into Python dicts,
then streams documents through async write pipeline to PG/Qdrant/Neo4j.

Pre-computed 768-dim gemini-embedding-001 vectors — no re-embedding.
Idempotent via content_hash — safe to re-run after interruption.

Usage::

    python scripts/import_epstein_hf.py --inspect
    python scripts/import_epstein_hf.py --matter-id <UUID> --dry-run --limit 100
    python scripts/import_epstein_hf.py --matter-id <UUID> --disable-hnsw --resume
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

import numpy as np
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


def create_duckdb_conn(cache_dir: str | None = None):
    """Create DuckDB connection with HF parquet files as views."""
    import duckdb
    from huggingface_hub import HfApi, hf_hub_download

    conn = duckdb.connect(":memory:")
    conn.execute("SET enable_progress_bar = false")
    conn.execute("SET temp_directory = '/tmp/duckdb_tmp'")
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
                local_paths.append(hf_hub_download(HF_DATASET, f.rfilename, repo_type="dataset", cache_dir=cache_dir))
            paths_sql = ", ".join(f"'{p}'" for p in local_paths)
            conn.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet([{paths_sql}], union_by_name=true)")
            count = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            print(f"    {table}: {count:,} rows ({len(pq_files)} shards)")
        except Exception as e:
            print(f"    {table}: FAILED — {e}")

    return conn


def inspect_dataset() -> None:
    """Print HF dataset structure."""
    from huggingface_hub import HfApi, hf_hub_download

    print(f"\n=== Inspecting {HF_DATASET} ===\n")
    api = HfApi()
    try:
        path = hf_hub_download(HF_DATASET, "data/export_stats.json", repo_type="dataset")
        with open(path) as f:
            stats = json.load(f)
        for k, v in stats.items():
            if k == "layers":
                print("Tables:")
                for t, c in v.items():
                    print(f"  {t}: {c:,}")
            else:
                print(f"{k}: {v}")
    except Exception as e:
        print(f"export_stats: {e}")

    print("\nParquet files:")
    for table in HF_TABLES:
        try:
            files = list(api.list_repo_tree(HF_DATASET, repo_type="dataset", path_in_repo=f"data/{table}"))
            pq = [f for f in files if hasattr(f, "size")]
            print(f"  {table}: {len(pq)} files, {sum(f.size for f in pq) / 1024 / 1024:.0f} MB")
        except Exception as e:
            print(f"  {table}: {e}")

    print("\nLoading via DuckDB...")
    conn = create_duckdb_conn()
    for table in ["documents", "chunks", "embeddings_chunk"]:
        try:
            cols = conn.execute(
                f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table}'"
            ).fetchall()
            print(f"\n  {table}: {', '.join(f'{n} ({t})' for n, t in cols)}")
        except Exception:
            pass
    conn.close()


# ---------------------------------------------------------------------------
# Index loading: DuckDB reads parquets → Python dicts hold in memory
# ---------------------------------------------------------------------------


def load_indexes(
    conn,
) -> tuple[
    dict[int, list[tuple[int, str, int]]],
    dict[int, np.ndarray],
    dict[int, list[dict]],
]:
    """Load chunk, embedding, entity indexes from DuckDB views into Python dicts.

    Returns:
        chunk_index: doc_id → [(chunk_index, content, token_count), ...]
        emb_index: chunk_id → numpy array (768-dim)
        entity_index: doc_id → [{"name": ..., "type": ...}, ...]
    """
    # Chunks: group by document_id
    print("\n  Loading chunk index...")
    t0 = time.time()
    chunk_index: dict[int, list[tuple[int, str, int, int]]] = {}  # doc_id → [(chunk_id, idx, content, tokens)]
    offset = 0
    batch_size = 200_000
    while True:
        rows = conn.execute(f"""
            SELECT id, document_id, chunk_index, content, token_count
            FROM chunks
            WHERE content IS NOT NULL AND length(trim(content)) > 0
            ORDER BY document_id, chunk_index
            LIMIT {batch_size} OFFSET {offset}
        """).fetchall()
        if not rows:
            break
        for cid, did, cidx, content, tokens in rows:
            if did not in chunk_index:
                chunk_index[did] = []
            chunk_index[did].append((int(cid), int(cidx or 0), str(content), int(tokens or len(str(content).split()))))
        offset += batch_size
    total_chunks = sum(len(v) for v in chunk_index.values())
    print(f"    {total_chunks:,} chunks for {len(chunk_index):,} docs ({time.time() - t0:.1f}s)")

    # Embeddings: chunk_id → vector
    print("  Loading embedding index...")
    t0 = time.time()
    emb_index: dict[int, np.ndarray] = {}
    offset = 0
    while True:
        rows = conn.execute(f"""
            SELECT chunk_id, embedding
            FROM embeddings_chunk
            WHERE embedding IS NOT NULL
            LIMIT {batch_size} OFFSET {offset}
        """).fetchall()
        if not rows:
            break
        skipped_dim = 0
        for cid, emb in rows:
            arr = np.asarray(emb, dtype=np.float32)
            if arr.shape[0] != 768:
                skipped_dim += 1
                continue
            emb_index[int(cid)] = arr
        if skipped_dim:
            logger.warning("embeddings.bad_dim", skipped=skipped_dim, batch_offset=offset)
        offset += batch_size
    print(f"    {len(emb_index):,} embeddings ({time.time() - t0:.1f}s)")

    # Entities: group by document_id
    print("  Loading entity index...")
    t0 = time.time()
    entity_index: dict[int, list[dict]] = {}
    offset = 0
    while True:
        rows = conn.execute(f"""
            SELECT document_id, entity_type, value, normalized_value
            FROM entities
            LIMIT {batch_size} OFFSET {offset}
        """).fetchall()
        if not rows:
            break
        for did, etype, val, norm in rows:
            if not val or not str(val).strip():
                continue
            if did not in entity_index:
                entity_index[did] = []
            entity_index[did].append({"name": str(norm or val).strip(), "type": str(etype or "unknown").lower()})
        offset += batch_size
    total_ents = sum(len(v) for v in entity_index.values())
    print(f"    {total_ents:,} entities for {len(entity_index):,} docs ({time.time() - t0:.1f}s)")

    return chunk_index, emb_index, entity_index


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _get_engine():
    from sqlalchemy import create_engine

    from app.config import Settings

    return create_engine(Settings().postgres_url_sync, pool_pre_ping=True, pool_size=5)


def _get_settings():
    from app.config import Settings

    return Settings()


def check_resume(engine, content_hash: str, matter_id: str) -> bool:
    from sqlalchemy import text

    with engine.connect() as conn:
        return (
            conn.execute(
                text("SELECT id FROM documents WHERE content_hash = :hash AND matter_id = :mid LIMIT 1"),
                {"hash": content_hash, "mid": matter_id},
            ).first()
            is not None
        )


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
            INSERT INTO jobs (id, filename, status, stage, progress, error, matter_id, metadata_, created_at, updated_at)
            VALUES (:id, :fn, 'complete', 'complete', :prog, NULL, :mid, :meta, now(), now())
        """),
            {
                "id": job_id,
                "fn": filename,
                "mid": matter_id,
                "meta": metadata_json,
                "prog": json.dumps({"chunks_created": chunk_count, "entities_extracted": entity_count}),
            },
        )
        conn.execute(
            text("""
            INSERT INTO documents (id, job_id, filename, document_type, page_count, chunk_count,
                 entity_count, minio_path, file_size_bytes, content_hash,
                 matter_id, import_source, metadata_, created_at, updated_at,
                 message_id, in_reply_to, references_)
            VALUES (:id, :jid, :fn, :dt, :pc, :cc, :ec, :mp, :fs, :ch,
                    :mid, :src, :meta, now(), now(), :msgid, :irp, :refs)
        """),
            {
                "id": doc_id,
                "jid": job_id,
                "fn": filename,
                "dt": doc_type,
                "pc": page_count,
                "cc": chunk_count,
                "ec": entity_count,
                "mp": f"raw/{job_id}/{filename}",
                "fs": len(full_text.encode("utf-8")),
                "ch": content_hash,
                "mid": matter_id,
                "src": IMPORT_SOURCE,
                "meta": metadata_json,
                "msgid": msg_id,
                "irp": in_reply,
                "refs": refs,
            },
        )
        conn.commit()
    return job_id, doc_id


def upload_to_minio(settings, key: str, data: bytes) -> None:
    import boto3
    from botocore.config import Config as BotoConfig

    scheme = "https" if settings.minio_use_ssl else "http"
    boto3.client(
        "s3",
        endpoint_url=f"{scheme}://{settings.minio_endpoint}",
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    ).put_object(Bucket=settings.minio_bucket, Key=key, Body=data, ContentType="text/plain")


def disable_hnsw(settings) -> None:
    from app.common.vector_store import TEXT_COLLECTION, VectorStoreClient

    VectorStoreClient(settings).disable_hnsw_indexing(TEXT_COLLECTION)
    print("  HNSW disabled")


def rebuild_hnsw(settings) -> None:
    from app.common.vector_store import TEXT_COLLECTION, VectorStoreClient

    VectorStoreClient(settings).rebuild_hnsw_index(TEXT_COLLECTION)
    print("  HNSW rebuild triggered")


def detect_named_vectors(settings) -> bool:
    from qdrant_client import QdrantClient

    from app.common.vector_store import TEXT_COLLECTION

    try:
        info = QdrantClient(url=settings.qdrant_url).get_collection(TEXT_COLLECTION)
        return isinstance(info.config.params.vectors, dict)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Async pipeline: stream docs from DuckDB, join via Python dicts, write
# ---------------------------------------------------------------------------


async def run_pipeline(
    conn,
    engine,
    settings,
    matter_id: str,
    chunk_index: dict,
    emb_index: dict,
    entity_index: dict,
    limit: int | None,
    resume: bool,
    skip_minio: bool,
    skip_neo4j: bool,
    use_named_vectors: bool,
    concurrency: int,
) -> tuple[int, int, int]:
    """Stream documents from DuckDB, look up chunks/embeddings/entities
    from Python dicts, write to PG/Qdrant/Neo4j.
    """
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import PointStruct

    from app.common.vector_store import TEXT_COLLECTION

    doc_count_raw = conn.execute(
        "SELECT count(*) FROM documents WHERE full_text IS NOT NULL AND length(trim(full_text)) >= 10"
    ).fetchone()[0]
    doc_count = min(doc_count_raw, limit) if limit else doc_count_raw
    print(f"\n  Streaming {doc_count:,} documents...")

    qdrant = AsyncQdrantClient(url=settings.qdrant_url, timeout=120)
    neo4j_driver = None
    if not skip_neo4j:
        from neo4j import AsyncGraphDatabase

        neo4j_driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
        )

    imported = 0
    skipped = 0
    total_chunks = 0
    start_time = time.time()

    # Stream documents in batches from DuckDB
    offset = 0
    batch_sz = 1000

    try:
        while True:
            rows = conn.execute(f"""
                SELECT id, file_key, full_text, document_type, date, dataset,
                       is_photo, has_handwriting, has_stamps, ocr_source,
                       additional_notes, page_number, document_number, email_fields
                FROM documents
                WHERE full_text IS NOT NULL AND length(trim(full_text)) >= 10
                ORDER BY id
                LIMIT {batch_sz} OFFSET {offset}
            """).fetchall()

            if not rows:
                break
            offset += batch_sz

            for row in rows:
                if limit and imported + skipped >= limit:
                    break

                (did, fk, ft, dty, dt, ds, ip, hw, st, oc, an, pn, dn, ef) = row
                did = int(did)
                fk = str(fk or "")
                ft = str(ft or "")
                fn = fk.split("/")[-1] if "/" in fk else fk
                ch = hashlib.sha256(ft.encode("utf-8")).hexdigest()[:16]

                if resume and check_resume(engine, ch, matter_id):
                    skipped += 1
                    continue

                # Look up chunks + embeddings from Python dicts
                raw_chunks = chunk_index.get(did, [])
                doc_chunks: list[tuple[str, int, int, list[float]]] = []
                for cid, cidx, content, tokens in sorted(raw_chunks, key=lambda x: x[1]):
                    emb = emb_index.get(cid)
                    if emb is None:
                        continue
                    doc_chunks.append((content, cidx, tokens, emb.tolist()))

                if not doc_chunks:
                    skipped += 1
                    continue

                ents = entity_index.get(did, [])

                # Metadata
                meta: dict[str, Any] = {"dataset": str(ds or ""), "original_file_key": fk}
                for field, val in [("date", dt), ("document_number", dn), ("ocr_source", oc), ("additional_notes", an)]:
                    if val:
                        meta[field] = str(val)
                for bf, bv in [("is_photo", ip), ("has_handwriting", hw), ("has_stamps", st)]:
                    if bv:
                        meta[bf] = True
                mj = json.dumps(meta, default=str)

                # Email headers
                mid = irp = rfs = None
                if ef and str(ef).strip():
                    try:
                        eh = json.loads(str(ef))
                        if isinstance(eh, dict):
                            mid, irp, rfs = eh.get("message_id"), eh.get("in_reply_to"), eh.get("references")
                    except (json.JSONDecodeError, TypeError, AttributeError):
                        pass

                doc_type = str(dty or "document")
                pg_count = int(pn) if pn and str(pn).isdigit() else 1

                # PG insert
                jid, docid = create_job_and_document(
                    engine,
                    fn,
                    ft,
                    doc_type,
                    pg_count,
                    ch,
                    len(doc_chunks),
                    len(ents),
                    matter_id,
                    mj,
                    mid,
                    irp,
                    rfs,
                )

                # MinIO
                if not skip_minio:
                    await asyncio.to_thread(upload_to_minio, settings, f"raw/{jid}/{fn}", ft.encode("utf-8"))

                # Qdrant
                pts: list[PointStruct] = []
                pids: list[str] = []
                for txt, ci, tc, emb in doc_chunks:
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
                                "doc_id": docid,
                                "matter_id": matter_id,
                                "token_count": tc,
                            },
                        )
                    )
                for i in range(0, len(pts), QDRANT_BATCH_SIZE):
                    for _retry in range(3):
                        try:
                            await qdrant.upsert(collection_name=TEXT_COLLECTION, points=pts[i : i + QDRANT_BATCH_SIZE])
                            break
                        except Exception as qe:
                            if _retry == 2:
                                raise
                            logger.warning("qdrant.upsert_retry", error=str(qe), retry=_retry + 1)
                            await asyncio.sleep(2**_retry)

                # Neo4j
                if neo4j_driver:
                    async with neo4j_driver.session() as sess:
                        await sess.run(
                            "MERGE (d:Document {id:$did}) SET d.filename=$fn,d.doc_type=$dt,d.page_count=$pc,d.matter_id=$mid",
                            did=docid,
                            fn=fn,
                            dt=doc_type,
                            pc=pg_count,
                            mid=matter_id,
                        )
                        cnodes = [{"cid": p, "tp": t[:200], "qp": p} for p, (t, *_) in zip(pids, doc_chunks)]
                        for i in range(0, len(cnodes), NEO4J_BATCH_SIZE):
                            await sess.run(
                                "UNWIND $cs AS c MERGE (k:Chunk {id:c.cid}) SET k.text_preview=c.tp,k.page_number=1,k.qdrant_point_id=c.qp WITH k,c MATCH (d:Document {id:$did}) MERGE (d)-[:HAS_CHUNK]->(k)",
                                cs=cnodes[i : i + NEO4J_BATCH_SIZE],
                                did=docid,
                            )
                        if ents:
                            for i in range(0, len(ents), ENTITY_BATCH_SIZE):
                                await sess.run(
                                    "UNWIND $es AS e MERGE (n:Entity {name:e.name,type:e.type,matter_id:$mid}) ON CREATE SET n.first_seen=datetime(),n.mention_count=1 ON MATCH SET n.mention_count=n.mention_count+1 WITH n MATCH (d:Document {id:$did}) MERGE (n)-[:MENTIONED_IN]->(d)",
                                    es=ents[i : i + ENTITY_BATCH_SIZE],
                                    mid=matter_id,
                                    did=docid,
                                )

                imported += 1
                total_chunks += len(doc_chunks)

                if imported % 500 == 0:
                    elapsed = time.time() - start_time
                    rate = imported / elapsed if elapsed > 0 else 0
                    eta = (doc_count - imported - skipped) / rate / 60 if rate > 0 else 0
                    print(
                        f"  [{imported:,}/{doc_count:,}] {total_chunks:,} chunks, {skipped:,} skip, {rate:.1f} docs/s, ETA {eta:.0f}m"
                    )

            if limit and imported + skipped >= limit:
                break

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
    """Import curated KG entities + relationships to Neo4j."""
    from neo4j import GraphDatabase

    kg_count = conn.execute("SELECT count(*) FROM kg_entities").fetchone()[0]
    rel_count = conn.execute("SELECT count(*) FROM kg_relationships").fetchone()[0]
    print(f"\n  KG: {kg_count} entities, {rel_count} relationships")

    driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    with driver.session() as sess:
        rows = conn.execute("SELECT id, name, entity_type, description FROM kg_entities").fetchall()
        batch = [{"name": str(n), "type": str(t or "unknown").lower(), "desc": str(d or "")} for _, n, t, d in rows]
        if batch:
            sess.run(
                "UNWIND $es AS e MERGE (n:Entity {name:e.name,type:e.type,matter_id:$mid}) SET n.description=e.desc,n.kg_curated=true",
                es=batch,
                mid=matter_id,
            )

        km = {int(i): str(n) for i, n, _, _ in rows}
        rels = conn.execute(
            "SELECT source_id, target_id, relationship_type, weight, evidence FROM kg_relationships"
        ).fetchall()
        rb = [
            {
                "s": km.get(int(si), ""),
                "t": km.get(int(ti), ""),
                "rt": str(rt or "RELATED_TO"),
                "w": float(w or 1.0),
                "ev": str(ev or ""),
            }
            for si, ti, rt, w, ev in rels
            if km.get(int(si)) and km.get(int(ti))
        ]
        for i in range(0, len(rb), 200):
            sess.run(
                "UNWIND $rs AS r MATCH (s:Entity {name:r.s,matter_id:$mid}) MATCH (t:Entity {name:r.t,matter_id:$mid}) MERGE (s)-[rel:RELATED_TO]->(t) SET rel.relationship_type=r.rt,rel.weight=r.w,rel.evidence=r.ev,rel.kg_curated=true",
                rs=rb[i : i + 200],
                mid=matter_id,
            )
    driver.close()
    print(f"  KG done: {kg_count} entities, {len(rb)} relationships")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:  # noqa: C901
    parser = argparse.ArgumentParser(description="Import kabasshouse/epstein-data into NEXUS")
    parser.add_argument("--matter-id", default=None, help="Target matter UUID")
    parser.add_argument("--limit", type=int, default=None, help="Import first N documents")
    parser.add_argument("--inspect", action="store_true", help="Inspect HF dataset and exit")
    parser.add_argument("--dry-run", action="store_true", help="Count only, no writes")
    parser.add_argument("--resume", action="store_true", help="Skip already-imported docs")
    parser.add_argument("--disable-hnsw", action="store_true", help="Disable HNSW during import")
    parser.add_argument("--skip-minio", action="store_true", help="Skip MinIO upload")
    parser.add_argument("--skip-neo4j", action="store_true", help="Skip Neo4j writes")
    parser.add_argument("--skip-kg", action="store_true", help="Skip KG import")
    parser.add_argument("--cache-dir", default=None, help="HF cache directory")
    parser.add_argument("--concurrency", type=int, default=16, help="Batch size")
    args = parser.parse_args()

    if args.inspect:
        inspect_dataset()
        return 0
    if not args.matter_id:
        print("Error: --matter-id required", file=sys.stderr)
        return 1
    try:
        uuid.UUID(args.matter_id)
    except ValueError:
        print(f"Error: invalid UUID '{args.matter_id}'", file=sys.stderr)
        return 1

    print(f"\n=== NEXUS HF Import: {HF_DATASET} ===")
    print(f"  Matter: {args.matter_id}")
    if args.limit:
        print(f"  Limit:  {args.limit}")

    print("\n  Loading DuckDB views...")
    conn = create_duckdb_conn(args.cache_dir)
    settings = _get_settings()
    engine = _get_engine()
    use_named = detect_named_vectors(settings)
    print(f"  Named vectors: {use_named}")

    if args.dry_run:
        dist = conn.execute(
            "SELECT dataset, count(*) as c FROM documents WHERE full_text IS NOT NULL AND length(trim(full_text))>=10 GROUP BY dataset ORDER BY c DESC"
        ).fetchall()
        print("\n  Dataset distribution:")
        for label, cnt in dist:
            print(f"    {label}: {cnt:,}")
        total = sum(c for _, c in dist)
        print(f"\n  [DRY RUN] Would import {min(total, args.limit) if args.limit else total:,} documents")
        conn.close()
        return 0

    # Load indexes into memory (DuckDB reads → Python dicts)
    chunk_index, emb_index, entity_index = load_indexes(conn)

    if args.disable_hnsw:
        disable_hnsw(settings)

    start_time = time.time()
    imported, skipped_count, total_chunks = asyncio.run(
        run_pipeline(
            conn=conn,
            engine=engine,
            settings=settings,
            matter_id=args.matter_id,
            chunk_index=chunk_index,
            emb_index=emb_index,
            entity_index=entity_index,
            limit=args.limit,
            resume=args.resume,
            skip_minio=args.skip_minio,
            skip_neo4j=args.skip_neo4j,
            use_named_vectors=use_named,
            concurrency=args.concurrency,
        )
    )

    if args.disable_hnsw:
        rebuild_hnsw(settings)
    if not args.skip_kg:
        import_kg(conn, settings, args.matter_id)
    conn.close()

    if imported > 0:
        print("\n  Post-ingestion hooks...")
        try:
            from app.ingestion.bulk_import import dispatch_post_ingestion_hooks

            hooks = dispatch_post_ingestion_hooks(args.matter_id)
            print(f"  Dispatched: {', '.join(hooks) or 'none'}")
        except Exception:
            logger.warning("post_ingestion.hooks_failed", exc_info=True)

    elapsed = time.time() - start_time
    print("\n=== Complete ===")
    print(f"  Imported: {imported:,} | Skipped: {skipped_count:,} | Chunks: {total_chunks:,}")
    print(f"  Time: {elapsed:.1f}s ({elapsed / 60:.1f}min)")
    if imported > 0 and elapsed > 0:
        print(f"  Rate: {imported / elapsed:.1f} docs/s ({total_chunks / elapsed:.0f} chunks/s)")

    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
