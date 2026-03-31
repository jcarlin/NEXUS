#!/usr/bin/env python3
"""Import kabasshouse/epstein-data HuggingFace dataset into NEXUS.

Downloads multi-table parquet dataset (documents, chunks, embeddings_chunk,
entities, kg_entities, kg_relationships), joins by integer ID, and writes
directly to PG/Qdrant/Neo4j using pre-computed 768-dim gemini-embedding-001
vectors. No re-chunking, no re-embedding, no NER.

Direct async pipeline (not Celery) — single process with async I/O to all
three data stores in parallel. Typically ~200-400 docs/sec.

Idempotent via content_hash — safe to re-run after interruption.

Usage::

    # Inspect dataset structure
    python scripts/import_epstein_hf.py --inspect

    # Dry run — count + schema preview
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HF_DATASET = "kabasshouse/epstein-data"
IMPORT_SOURCE = "kabasshouse/epstein-data"

QDRANT_BATCH_SIZE = 500
NEO4J_BATCH_SIZE = 200
ENTITY_BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# HF dataset inspection
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
                    print(f"    {table}: {count:,} rows")
            else:
                print(f"  {k}: {v}")
    except Exception as e:
        print(f"  export_stats.json: {e}")

    print("\nParquet files:")
    for table in [
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
    ]:
        try:
            files = list(api.list_repo_tree(HF_DATASET, repo_type="dataset", path_in_repo=f"data/{table}"))
            pq_files = [f for f in files if hasattr(f, "size")]
            total_size = sum(f.size for f in pq_files)
            print(f"  {table}: {len(pq_files)} files, {total_size / 1024 / 1024:.0f} MB")
        except Exception as e:
            print(f"  {table}: {e}")

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
# Parquet loading
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
        return v if v == v else None
    except (ValueError, TypeError):
        return None


def load_indexes(cache_dir: str | None = None, doc_id_set: set[int] | None = None):
    """Load chunk, embedding, and entity indexes into memory.

    Returns (chunk_map, emb_map, entity_map, doc_chunks).
    """
    import numpy as np
    import pandas as pd

    # Chunks: chunk_key → (document_id, chunk_index, content, token_count)
    # Some shards use integer document_id, others use file_key string.
    # We normalize to integer document_id using doc_file_key_to_id map.
    print("\n  Loading chunks index...")
    chunk_map: dict[int, tuple[int, int, str, int]] = {}
    # For file_key-based shards, we need a reverse map from file_key → doc int id
    # This will be populated lazily if needed
    file_key_to_doc_id: dict[str, int] | None = None
    chunk_auto_id = 0  # auto-increment for shards without chunk id column

    for cp in download_parquet_table("chunks", cache_dir):
        cdf = pd.read_parquet(cp)
        has_doc_id_col = "document_id" in cdf.columns
        has_file_key_col = "file_key" in cdf.columns
        has_id_col = "id" in cdf.columns

        # If this shard uses file_key, build reverse map from doc parquets
        if has_file_key_col and not has_doc_id_col and file_key_to_doc_id is None:
            print("    Building file_key → doc_id reverse map...")
            file_key_to_doc_id = {}
            for dp in download_parquet_table("documents", cache_dir):
                ddf = pd.read_parquet(dp, columns=["id", "file_key"])
                for _, drow in ddf.iterrows():
                    file_key_to_doc_id[str(drow["file_key"])] = int(drow["id"])
                del ddf
            print(f"    Mapped {len(file_key_to_doc_id):,} file_keys")

        for _, row in cdf.iterrows():
            # Resolve document_id
            if has_doc_id_col:
                doc_id = int(row["document_id"])
            elif has_file_key_col and file_key_to_doc_id is not None:
                fk = str(row["file_key"])
                doc_id = file_key_to_doc_id.get(fk, -1)
                if doc_id == -1:
                    continue
            else:
                continue

            if doc_id_set and doc_id not in doc_id_set:
                continue
            content = str(row.get("content", ""))
            if not content.strip():
                continue

            chunk_id = int(row["id"]) if has_id_col else chunk_auto_id
            chunk_auto_id += 1

            chunk_map[chunk_id] = (
                doc_id,
                int(row.get("chunk_index", 0)),
                content,
                int(row.get("token_count", 0)) or len(content.split()),
            )
        del cdf
    print(f"    {len(chunk_map):,} chunks indexed")

    # Embeddings: chunk_id → numpy array (768-dim float32)
    print("  Loading embeddings index...")
    emb_map: dict[int, np.ndarray] = {}
    for ep in download_parquet_table("embeddings_chunk", cache_dir):
        edf = pd.read_parquet(ep)
        for _, row in edf.iterrows():
            chunk_id = int(row["chunk_id"])
            if chunk_id in chunk_map:
                embedding = row.get("embedding")
                if embedding is not None:
                    emb_map[chunk_id] = np.asarray(embedding, dtype=np.float32)
        del edf
    print(f"    {len(emb_map):,} embeddings indexed")

    # Entities: document_id → list of entity dicts
    print("  Loading entities index...")
    entity_map: dict[int, list[dict]] = {}
    for ep in download_parquet_table("entities", cache_dir):
        edf = pd.read_parquet(ep)
        has_doc_id = "document_id" in edf.columns
        has_fk = "file_key" in edf.columns
        for _, row in edf.iterrows():
            if has_doc_id:
                doc_id = int(row["document_id"])
            elif has_fk and file_key_to_doc_id is not None:
                doc_id = file_key_to_doc_id.get(str(row["file_key"]), -1)
                if doc_id == -1:
                    continue
            else:
                continue
            if doc_id_set and doc_id not in doc_id_set:
                continue
            value = str(row.get("value", ""))
            if not value.strip():
                continue
            normalized = str(row.get("normalized_value", "")) or value
            if doc_id not in entity_map:
                entity_map[doc_id] = []
            entity_map[doc_id].append(
                {
                    "name": normalized.strip() or value.strip(),
                    "type": str(row.get("entity_type", "unknown")).lower(),
                }
            )
        del edf
    total_ents = sum(len(v) for v in entity_map.values())
    print(f"    {total_ents:,} entities for {len(entity_map):,} documents")

    # Group chunks by document_id
    doc_chunks: dict[int, list[int]] = {}
    for chunk_id, (doc_id, *_) in chunk_map.items():
        if doc_id not in doc_chunks:
            doc_chunks[doc_id] = []
        doc_chunks[doc_id].append(chunk_id)

    return chunk_map, emb_map, entity_map, doc_chunks


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
    engine, doc_row, matter_id: str, metadata_json: str, content_hash: str, chunk_count: int, entity_count: int
) -> tuple[str, str]:
    from sqlalchemy import text

    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())

    import pandas as pd

    file_key = str(doc_row.get("file_key", ""))
    filename = file_key.split("/")[-1] if "/" in file_key else file_key
    full_text = str(doc_row.get("full_text", ""))
    doc_type = str(doc_row.get("document_type", "document")) if pd.notna(doc_row.get("document_type")) else "document"
    page_count = _safe_int(doc_row.get("page_number")) or 1

    # Parse email headers
    email_fields = doc_row.get("email_fields")
    msg_id = in_reply = refs = None
    if pd.notna(email_fields) and isinstance(email_fields, str) and email_fields.strip():
        try:
            eh = json.loads(email_fields)
            msg_id = eh.get("message_id")
            in_reply = eh.get("in_reply_to")
            refs = eh.get("references")
        except (json.JSONDecodeError, TypeError):
            pass

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
    endpoint_url = f"{scheme}://{settings.minio_endpoint}"
    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )
    client.put_object(Bucket=settings.minio_bucket, Key=key, Body=data, ContentType="text/plain")


def disable_hnsw(settings) -> None:
    from app.common.vector_store import TEXT_COLLECTION, VectorStoreClient

    client = VectorStoreClient(settings)
    print("  Disabling HNSW indexing for bulk insert...")
    client.disable_hnsw_indexing(TEXT_COLLECTION)


def rebuild_hnsw(settings) -> None:
    from app.common.vector_store import TEXT_COLLECTION, VectorStoreClient

    client = VectorStoreClient(settings)
    print("  Rebuilding HNSW index (background)...")
    client.rebuild_hnsw_index(TEXT_COLLECTION)


def detect_named_vectors(settings) -> bool:
    from qdrant_client import QdrantClient

    from app.common.vector_store import TEXT_COLLECTION

    client = QdrantClient(url=settings.qdrant_url)
    try:
        info = client.get_collection(TEXT_COLLECTION)
        return isinstance(info.config.params.vectors, dict)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Async pipeline
# ---------------------------------------------------------------------------


async def run_pipeline(
    engine,
    settings,
    matter_id: str,
    cache_dir: str | None,
    limit: int | None,
    resume: bool,
    skip_minio: bool,
    skip_neo4j: bool,
    use_named_vectors: bool,
    concurrency: int,
) -> tuple[int, int, int]:
    """Direct async pipeline: read parquet → write PG/Qdrant/Neo4j.

    Returns (imported, skipped, total_chunks).
    """
    import pandas as pd
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import PointStruct

    from app.common.vector_store import TEXT_COLLECTION

    # Download document parquet paths
    print("\n  Downloading document parquet shards...")
    doc_paths = download_parquet_table("documents", cache_dir)
    print(f"    {len(doc_paths)} document shards")

    # If limit is set, figure out which doc IDs we care about
    doc_id_set: set[int] | None = None
    if limit:
        print(f"  Pre-scanning for first {limit} documents...")
        doc_id_set = set()
        count = 0
        for dp in doc_paths:
            ddf = pd.read_parquet(dp, columns=["id"])
            for _, row in ddf.iterrows():
                doc_id_set.add(int(row["id"]))
                count += 1
                if count >= limit:
                    break
            del ddf
            if count >= limit:
                break
        print(f"    Selected {len(doc_id_set)} document IDs")

    # Load indexes (chunks, embeddings, entities)
    chunk_map, emb_map, entity_map, doc_chunks = load_indexes(cache_dir, doc_id_set)

    # Connect to async clients
    qdrant = AsyncQdrantClient(url=settings.qdrant_url)
    neo4j_driver = None
    if not skip_neo4j:
        from neo4j import AsyncGraphDatabase

        neo4j_driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

    imported = 0
    skipped = 0
    total_chunks = 0
    start_time = time.time()

    try:
        for dp in doc_paths:
            ddf = pd.read_parquet(dp)

            # Process documents in batches of `concurrency`
            rows = list(ddf.iterrows())
            del ddf

            for batch_start in range(0, len(rows), concurrency):
                batch_rows = rows[batch_start : batch_start + concurrency]

                for _, doc_row in batch_rows:
                    if limit and imported + skipped >= limit:
                        break

                    doc_int_id = int(doc_row["id"])
                    file_key = str(doc_row.get("file_key", ""))
                    full_text = str(doc_row.get("full_text", "")) if pd.notna(doc_row.get("full_text")) else ""

                    if not full_text or len(full_text.strip()) < 10:
                        skipped += 1
                        continue

                    content_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()[:16]

                    if resume and check_resume(engine, content_hash, matter_id):
                        skipped += 1
                        continue

                    # Build chunks + embeddings for this document
                    chunk_ids = doc_chunks.get(doc_int_id, [])
                    doc_chunk_data: list[tuple[str, int, int, list[float]]] = []  # (text, idx, tokens, emb)

                    for cid in sorted(chunk_ids, key=lambda c: chunk_map[c][1]):
                        if cid not in emb_map:
                            continue
                        _, chunk_index, content, token_count = chunk_map[cid]
                        doc_chunk_data.append((content, chunk_index, token_count, emb_map[cid].tolist()))

                    if not doc_chunk_data:
                        skipped += 1
                        continue

                    entities = entity_map.get(doc_int_id, [])

                    # Build metadata
                    meta: dict[str, Any] = {
                        "dataset": str(doc_row.get("dataset", "")) if pd.notna(doc_row.get("dataset")) else "",
                        "original_file_key": file_key,
                    }
                    for field in ("date", "document_number", "ocr_source", "additional_notes"):
                        val = doc_row.get(field)
                        if pd.notna(val) and str(val).strip():
                            meta[field] = str(val)
                    for bf in ("is_photo", "has_handwriting", "has_stamps"):
                        if doc_row.get(bf):
                            meta[bf] = True
                    metadata_json = json.dumps(meta, default=str)

                    # PG insert
                    job_id, doc_id = create_job_and_document(
                        engine,
                        doc_row,
                        matter_id,
                        metadata_json,
                        content_hash,
                        len(doc_chunk_data),
                        len(entities),
                    )

                    # MinIO upload (async via thread)
                    if not skip_minio:
                        filename = file_key.split("/")[-1] if "/" in file_key else file_key
                        await asyncio.to_thread(
                            upload_to_minio,
                            settings,
                            f"raw/{job_id}/{filename}",
                            full_text.encode("utf-8"),
                        )

                    # Qdrant upsert
                    points: list[PointStruct] = []
                    point_ids: list[str] = []
                    for text, chunk_index, token_count, embedding in doc_chunk_data:
                        pid = str(uuid.uuid4())
                        point_ids.append(pid)
                        vector: Any = {"dense": embedding} if use_named_vectors else embedding
                        points.append(
                            PointStruct(
                                id=pid,
                                vector=vector,
                                payload={
                                    "source_file": file_key,
                                    "chunk_text": text,
                                    "chunk_index": chunk_index,
                                    "doc_id": doc_id,
                                    "matter_id": matter_id,
                                    "token_count": token_count,
                                },
                            )
                        )

                    for i in range(0, len(points), QDRANT_BATCH_SIZE):
                        await qdrant.upsert(collection_name=TEXT_COLLECTION, points=points[i : i + QDRANT_BATCH_SIZE])

                    # Neo4j: Document + Chunk + Entity nodes
                    if neo4j_driver:
                        filename = file_key.split("/")[-1] if "/" in file_key else file_key
                        async with neo4j_driver.session() as session:
                            await session.run(
                                """
                                MERGE (doc:Document {id: $doc_id})
                                SET doc.filename = $filename, doc.doc_type = $doc_type,
                                    doc.page_count = $page_count, doc.matter_id = $matter_id
                                """,
                                doc_id=doc_id,
                                filename=filename,
                                doc_type=meta.get("doc_type", "document"),
                                page_count=_safe_int(doc_row.get("page_number")) or 1,
                                matter_id=matter_id,
                            )

                            # Chunk nodes
                            chunk_nodes = [
                                {"chunk_id": pid, "text_preview": text[:200], "page_number": 1, "qdrant_point_id": pid}
                                for pid, (text, *_) in zip(point_ids, doc_chunk_data)
                            ]
                            for i in range(0, len(chunk_nodes), NEO4J_BATCH_SIZE):
                                await session.run(
                                    """
                                    UNWIND $chunks AS c
                                    MERGE (chunk:Chunk {id: c.chunk_id})
                                    SET chunk.text_preview = c.text_preview,
                                        chunk.page_number = c.page_number,
                                        chunk.qdrant_point_id = c.qdrant_point_id
                                    WITH chunk, c
                                    MATCH (doc:Document {id: $doc_id})
                                    MERGE (doc)-[:HAS_CHUNK]->(chunk)
                                    """,
                                    chunks=chunk_nodes[i : i + NEO4J_BATCH_SIZE],
                                    doc_id=doc_id,
                                )

                            # Entity nodes
                            if entities:
                                for i in range(0, len(entities), ENTITY_BATCH_SIZE):
                                    await session.run(
                                        """
                                        UNWIND $entities AS e
                                        MERGE (ent:Entity {name: e.name, type: e.type, matter_id: $matter_id})
                                        ON CREATE SET ent.first_seen = datetime(), ent.mention_count = 1
                                        ON MATCH SET ent.mention_count = ent.mention_count + 1
                                        WITH ent
                                        MATCH (doc:Document {id: $doc_id})
                                        MERGE (ent)-[:MENTIONED_IN]->(doc)
                                        """,
                                        entities=entities[i : i + ENTITY_BATCH_SIZE],
                                        matter_id=matter_id,
                                        doc_id=doc_id,
                                    )

                    imported += 1
                    total_chunks += len(doc_chunk_data)

                # Progress
                if imported % 500 < concurrency or imported < concurrency:
                    elapsed = time.time() - start_time
                    rate = imported / elapsed if elapsed > 0 else 0
                    eta_min = ((limit or 1_400_000) - imported - skipped) / rate / 60 if rate > 0 else 0
                    print(
                        f"  [{imported:,}/{limit or '~1.4M'}] "
                        f"{total_chunks:,} chunks, {skipped:,} skipped, "
                        f"{rate:.1f} docs/sec, ETA {eta_min:.0f}min"
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
# KG import (small tables, direct sync)
# ---------------------------------------------------------------------------


def import_kg(settings, matter_id: str, cache_dir: str | None = None) -> None:
    """Import curated KG entities + relationships directly to Neo4j."""
    import pandas as pd
    from neo4j import GraphDatabase

    kg_ent_paths = download_parquet_table("kg_entities", cache_dir)
    kg_rel_paths = download_parquet_table("kg_relationships", cache_dir)
    if not kg_ent_paths:
        print("  No KG tables found, skipping.")
        return

    kg_entities = pd.concat([pd.read_parquet(p) for p in kg_ent_paths], ignore_index=True)
    kg_rels = pd.concat([pd.read_parquet(p) for p in kg_rel_paths], ignore_index=True)
    print(f"\n  Importing KG: {len(kg_entities)} entities, {len(kg_rels)} relationships")

    driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))

    with driver.session() as session:
        batch = [
            {
                "name": str(row.get("name", "")),
                "type": str(row.get("entity_type", "unknown")).lower(),
                "description": str(row.get("description", "")) if pd.notna(row.get("description")) else "",
            }
            for _, row in kg_entities.iterrows()
        ]
        if batch:
            session.run(
                """
                UNWIND $entities AS e
                MERGE (ent:Entity {name: e.name, type: e.type, matter_id: $matter_id})
                SET ent.description = e.description, ent.kg_curated = true
                """,
                entities=batch,
                matter_id=matter_id,
            )

        kg_id_to_name = {int(row["id"]): str(row.get("name", "")) for _, row in kg_entities.iterrows()}

        rel_batch = []
        for _, row in kg_rels.iterrows():
            src = kg_id_to_name.get(int(row.get("source_id", -1)), "")
            tgt = kg_id_to_name.get(int(row.get("target_id", -1)), "")
            if not src or not tgt:
                continue
            rel_batch.append(
                {
                    "source": src,
                    "target": tgt,
                    "rel_type": str(row.get("relationship_type", "RELATED_TO")),
                    "weight": float(row.get("weight", 1.0)) if pd.notna(row.get("weight")) else 1.0,
                    "evidence": str(row.get("evidence", "")) if pd.notna(row.get("evidence")) else "",
                }
            )

        for i in range(0, len(rel_batch), 200):
            session.run(
                """
                UNWIND $rels AS r
                MATCH (s:Entity {name: r.source, matter_id: $matter_id})
                MATCH (t:Entity {name: r.target, matter_id: $matter_id})
                MERGE (s)-[rel:RELATED_TO]->(t)
                SET rel.relationship_type = r.rel_type, rel.weight = r.weight,
                    rel.evidence = r.evidence, rel.kg_curated = true
                """,
                rels=rel_batch[i : i + 200],
                matter_id=matter_id,
            )

    driver.close()
    print(f"  KG import complete: {len(kg_entities)} entities, {len(kg_rels)} relationships")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:  # noqa: C901
    parser = argparse.ArgumentParser(
        description="Import kabasshouse/epstein-data into NEXUS (direct async pipeline)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--matter-id", default=None, help="Target matter UUID")
    parser.add_argument("--limit", type=int, default=None, help="Import first N documents only")
    parser.add_argument("--inspect", action="store_true", help="Inspect HF dataset structure and exit")
    parser.add_argument("--dry-run", action="store_true", help="Load + count, no writes")
    parser.add_argument("--resume", action="store_true", help="Skip docs whose content_hash exists")
    parser.add_argument("--disable-hnsw", action="store_true", help="Disable HNSW during import, rebuild after")
    parser.add_argument("--skip-minio", action="store_true", help="Skip MinIO upload of text files")
    parser.add_argument("--skip-neo4j", action="store_true", help="Skip Neo4j graph indexing")
    parser.add_argument("--skip-kg", action="store_true", help="Skip KG entity/relationship import")
    parser.add_argument("--cache-dir", default=None, help="HF datasets cache directory")
    parser.add_argument("--concurrency", type=int, default=16, help="Documents per batch (default: 16)")

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

    print(f"\n=== NEXUS HF Import: {HF_DATASET} (direct async) ===")
    print(f"  Matter:      {args.matter_id}")
    print(f"  Concurrency: {args.concurrency} docs/batch")
    if args.limit:
        print(f"  Limit:       {args.limit} documents")

    settings = _get_settings()
    engine = _get_engine()

    use_named = detect_named_vectors(settings)
    print(f"  Named vectors: {use_named}")

    if args.disable_hnsw:
        disable_hnsw(settings)

    start_time = time.time()
    imported, skipped_count, total_chunks = asyncio.run(
        run_pipeline(
            engine=engine,
            settings=settings,
            matter_id=args.matter_id,
            cache_dir=args.cache_dir,
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
        import_kg(settings, args.matter_id, args.cache_dir)

    if imported > 0:
        print("\n  Dispatching post-ingestion hooks...")
        try:
            from app.ingestion.bulk_import import dispatch_post_ingestion_hooks

            hooks = dispatch_post_ingestion_hooks(args.matter_id)
            print(f"  Dispatched: {', '.join(hooks) or 'none'}")
        except Exception:
            logger.warning("post_ingestion.hooks_failed", exc_info=True)

    elapsed = time.time() - start_time
    print("\n=== Import Complete ===")
    print(f"  Imported:     {imported:,} documents")
    print(f"  Skipped:      {skipped_count:,}")
    print(f"  Total chunks: {total_chunks:,}")
    print(f"  Elapsed:      {elapsed:.1f}s ({elapsed / 60:.1f}min)")
    if imported > 0 and elapsed > 0:
        print(f"  Rate:         {imported / elapsed:.1f} docs/sec ({total_chunks / elapsed:.0f} chunks/sec)")

    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
