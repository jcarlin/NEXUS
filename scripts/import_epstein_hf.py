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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HF_DATASET = "kabasshouse/epstein-data"
IMPORT_SOURCE = "kabasshouse/epstein-data"
QDRANT_BATCH_SIZE = 500
NEO4J_BATCH_SIZE = 200
ENTITY_BATCH_SIZE = 500

# Tables in the HF dataset repo under data/
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

    conn = duckdb.connect(":memory:")
    conn.execute("SET enable_progress_bar = false")

    # Download parquet files via huggingface_hub and register as views
    from huggingface_hub import HfApi, hf_hub_download

    api = HfApi()

    for table in HF_TABLES:
        try:
            files = list(api.list_repo_tree(HF_DATASET, repo_type="dataset", path_in_repo=f"data/{table}"))
            pq_files = [f for f in files if hasattr(f, "rfilename") and f.rfilename.endswith(".parquet")]
            if not pq_files:
                continue

            # Filter to canonical shards only (*-of-*.parquet) to avoid
            # duplicate rows from older export format (*.parquet without -of-)
            canonical = [f for f in pq_files if "-of-" in f.rfilename]
            if canonical:
                pq_files = canonical

            # Download all parquet files and collect local paths
            local_paths = []
            for f in sorted(pq_files, key=lambda x: x.rfilename):
                local = hf_hub_download(HF_DATASET, f.rfilename, repo_type="dataset", cache_dir=cache_dir)
                local_paths.append(local)

            # Register as a DuckDB view using read_parquet with union_by_name
            # This handles mixed schemas across shards
            paths_sql = ", ".join(f"'{p}'" for p in local_paths)
            conn.execute(f"""
                CREATE VIEW {table} AS
                SELECT * FROM read_parquet([{paths_sql}], union_by_name=true)
            """)
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

    # Export stats
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

    # Parquet sizes
    print("\nParquet files:")
    for table in HF_TABLES:
        try:
            files = list(api.list_repo_tree(HF_DATASET, repo_type="dataset", path_in_repo=f"data/{table}"))
            pq_files = [f for f in files if hasattr(f, "size")]
            total_size = sum(f.size for f in pq_files)
            print(f"  {table}: {len(pq_files)} files, {total_size / 1024 / 1024:.0f} MB")
        except Exception as e:
            print(f"  {table}: {e}")

    # DuckDB schema inspection
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
    """DuckDB → PG/Qdrant/Neo4j async pipeline.

    Uses DuckDB to join documents + chunks + embeddings in a single SQL query,
    then streams results grouped by document into the write pipeline.

    Returns (imported, skipped, total_chunks).
    """
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import PointStruct

    from app.common.vector_store import TEXT_COLLECTION

    # Build the main join query
    # COALESCE handles mixed schemas (some shards have document_id, others file_key)
    limit_clause = f"LIMIT {limit}" if limit else ""

    # First, get documents with their chunks and embeddings joined
    print("\n  Building joined query via DuckDB...")
    doc_query = f"""
        SELECT
            d.id AS doc_int_id,
            d.file_key,
            d.full_text,
            d.document_type,
            d.date,
            d.dataset,
            d.is_photo,
            d.has_handwriting,
            d.has_stamps,
            d.ocr_source,
            d.additional_notes,
            d.page_number,
            d.document_number,
            d.char_count,
            d.email_fields
        FROM documents d
        WHERE d.full_text IS NOT NULL
          AND length(trim(d.full_text)) >= 10
        ORDER BY d.id
        {limit_clause}
    """

    doc_count = conn.execute(f"SELECT count(*) FROM ({doc_query}) t").fetchone()[0]
    print(f"  Documents to process: {doc_count:,}")

    if dry_run:
        # Show dataset distribution
        dist = conn.execute("""
            SELECT dataset, count(*) as cnt
            FROM documents
            WHERE full_text IS NOT NULL AND length(trim(full_text)) >= 10
            GROUP BY dataset ORDER BY cnt DESC
        """).fetchall()
        print("\n  Dataset distribution:")
        for label, cnt in dist:
            print(f"    {label}: {cnt:,}")

        sample = conn.execute(
            f"SELECT file_key, dataset, document_type, char_count FROM ({doc_query}) t LIMIT 5"
        ).fetchall()
        print("\n  Sample documents:")
        for fk, ds, dt, cc in sample:
            print(f"    {fk}: {ds}, {dt}, {cc} chars")

        print(f"\n  [DRY RUN] Would import {doc_count:,} documents")
        return doc_count, 0, 0

    # Connect async clients
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
        # Stream documents from DuckDB
        doc_result = conn.execute(doc_query)

        while True:
            doc_rows = doc_result.fetchmany(concurrency)
            if not doc_rows:
                break

            for doc_row in doc_rows:
                (
                    doc_int_id,
                    file_key,
                    full_text,
                    document_type,
                    date_val,
                    dataset,
                    is_photo,
                    has_handwriting,
                    has_stamps,
                    ocr_source,
                    additional_notes,
                    page_number,
                    document_number,
                    char_count,
                    email_fields,
                ) = doc_row

                file_key = str(file_key or "")
                full_text = str(full_text or "")
                filename = file_key.split("/")[-1] if "/" in file_key else file_key

                content_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()[:16]

                if resume and check_resume(engine, content_hash, matter_id):
                    skipped += 1
                    continue

                # Fetch chunks + embeddings for this document via DuckDB join
                # Use COALESCE to handle shards with document_id vs file_key
                chunk_rows = conn.execute(
                    """
                    SELECT
                        c.chunk_index,
                        c.content,
                        c.token_count,
                        e.embedding
                    FROM chunks c
                    JOIN embeddings_chunk e ON (
                        e.chunk_id = c.id
                        OR (e.document_id = c.document_id AND c.id IS NULL)
                    )
                    WHERE COALESCE(c.document_id, NULL) = ?
                       OR COALESCE(c.file_key, NULL) = ?
                    ORDER BY c.chunk_index
                """,
                    [doc_int_id, file_key],
                ).fetchall()

                if not chunk_rows:
                    # Try alternate join: chunks by document_id only
                    chunk_rows = conn.execute(
                        """
                        SELECT
                            c.chunk_index,
                            c.content,
                            c.token_count,
                            e.embedding
                        FROM chunks c
                        JOIN embeddings_chunk e ON e.chunk_id = c.id
                        WHERE c.document_id = ?
                        ORDER BY c.chunk_index
                    """,
                        [doc_int_id],
                    ).fetchall()

                if not chunk_rows:
                    skipped += 1
                    continue

                # Parse chunks
                doc_chunks: list[tuple[str, int, int, list[float]]] = []
                for chunk_index, content, token_count, embedding in chunk_rows:
                    if embedding is None or content is None:
                        continue
                    emb_list = list(embedding) if hasattr(embedding, "__iter__") else []
                    if not emb_list:
                        continue
                    doc_chunks.append(
                        (
                            str(content),
                            int(chunk_index or 0),
                            int(token_count or len(str(content).split())),
                            emb_list,
                        )
                    )

                if not doc_chunks:
                    skipped += 1
                    continue

                # Fetch entities for this document
                entity_rows = conn.execute(
                    """
                    SELECT entity_type, value, normalized_value
                    FROM entities
                    WHERE document_id = ?
                """,
                    [doc_int_id],
                ).fetchall()

                entities = [
                    {
                        "name": str(norm or val).strip(),
                        "type": str(etype or "unknown").lower(),
                    }
                    for etype, val, norm in entity_rows
                    if val and str(val).strip()
                ]

                # Build metadata
                meta: dict[str, Any] = {
                    "dataset": str(dataset or ""),
                    "original_file_key": file_key,
                }
                if date_val:
                    meta["date"] = str(date_val)
                if document_number:
                    meta["document_number"] = str(document_number)
                if ocr_source:
                    meta["ocr_source"] = str(ocr_source)
                if additional_notes:
                    meta["additional_notes"] = str(additional_notes)
                if is_photo:
                    meta["is_photo"] = True
                if has_handwriting:
                    meta["has_handwriting"] = True
                if has_stamps:
                    meta["has_stamps"] = True
                metadata_json = json.dumps(meta, default=str)

                # Parse email headers
                msg_id = in_reply = refs = None
                if email_fields and str(email_fields).strip():
                    try:
                        eh = json.loads(str(email_fields))
                        msg_id = eh.get("message_id")
                        in_reply = eh.get("in_reply_to")
                        refs = eh.get("references")
                    except (json.JSONDecodeError, TypeError):
                        pass

                doc_type = str(document_type or "document")
                pg_count = int(page_number) if page_number and str(page_number).isdigit() else 1

                # PG insert
                job_id, doc_id = create_job_and_document(
                    engine,
                    filename,
                    full_text,
                    doc_type,
                    pg_count,
                    content_hash,
                    len(doc_chunks),
                    len(entities),
                    matter_id,
                    metadata_json,
                    msg_id,
                    in_reply,
                    refs,
                )

                # MinIO upload
                if not skip_minio:
                    await asyncio.to_thread(
                        upload_to_minio,
                        settings,
                        f"raw/{job_id}/{filename}",
                        full_text.encode("utf-8"),
                    )

                # Qdrant upsert
                points: list[PointStruct] = []
                point_ids: list[str] = []
                for text, chunk_index, token_count, embedding in doc_chunks:
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
                    await qdrant.upsert(
                        collection_name=TEXT_COLLECTION,
                        points=points[i : i + QDRANT_BATCH_SIZE],
                    )

                # Neo4j
                if neo4j_driver:
                    async with neo4j_driver.session() as session:
                        await session.run(
                            """
                            MERGE (doc:Document {id: $doc_id})
                            SET doc.filename = $filename, doc.doc_type = $doc_type,
                                doc.page_count = $page_count, doc.matter_id = $matter_id
                            """,
                            doc_id=doc_id,
                            filename=filename,
                            doc_type=doc_type,
                            page_count=pg_count,
                            matter_id=matter_id,
                        )

                        chunk_nodes = [
                            {"chunk_id": pid, "text_preview": text[:200], "page_number": 1, "qdrant_point_id": pid}
                            for pid, (text, *_) in zip(point_ids, doc_chunks)
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
                total_chunks += len(doc_chunks)

            # Progress
            elapsed = time.time() - start_time
            rate = imported / elapsed if elapsed > 0 else 0
            if imported % 500 < concurrency or imported < concurrency:
                eta_min = (doc_count - imported - skipped) / rate / 60 if rate > 0 else 0
                print(
                    f"  [{imported:,}/{doc_count:,}] "
                    f"{total_chunks:,} chunks, {skipped:,} skipped, "
                    f"{rate:.1f} docs/sec, ETA {eta_min:.0f}min"
                )

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
        # KG entities
        rows = conn.execute("SELECT id, name, entity_type, description FROM kg_entities").fetchall()
        batch = [
            {"name": str(name), "type": str(etype or "unknown").lower(), "description": str(desc or "")}
            for _, name, etype, desc in rows
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

        # Build id → name map
        kg_id_to_name = {int(rid): str(name) for rid, name, _, _ in rows}

        # KG relationships
        rels = conn.execute(
            "SELECT source_id, target_id, relationship_type, weight, evidence FROM kg_relationships"
        ).fetchall()
        rel_batch = []
        for src_id, tgt_id, rtype, weight, evidence in rels:
            src = kg_id_to_name.get(int(src_id), "")
            tgt = kg_id_to_name.get(int(tgt_id), "")
            if not src or not tgt:
                continue
            rel_batch.append(
                {
                    "source": src,
                    "target": tgt,
                    "rel_type": str(rtype or "RELATED_TO"),
                    "weight": float(weight or 1.0),
                    "evidence": str(evidence or ""),
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
    print(f"  KG import complete: {kg_count} entities, {rel_count} relationships")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:  # noqa: C901
    parser = argparse.ArgumentParser(
        description="Import kabasshouse/epstein-data into NEXUS (DuckDB + async pipeline)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
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

    # Create DuckDB connection with all HF tables registered
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
