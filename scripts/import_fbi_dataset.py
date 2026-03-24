#!/usr/bin/env python3
"""Import pre-chunked + pre-embedded HuggingFace datasets into NEXUS.

Designed for datasets like ``svetfm/epstein-fbi-files`` and
``svetfm/epstein-files-nov11-25-house-post-ocr-embeddings`` that ship
with pre-computed 768d nomic-embed-text vectors.

Pipeline (async, batched):
  1. Read parquet → group chunks by source document
  2. Batch embed via configured provider (Infinity BGE-M3 GPU)
  3. Batch upsert to Qdrant (500 points per call)
  4. Batch create Neo4j Document + Chunk nodes (UNWIND)
  5. Batch insert PostgreSQL job + document rows
  6. Optional: GLiNER NER (deferred to Celery queue)

Usage::

    # Local test (50 docs)
    python scripts/import_fbi_dataset.py \\
        --file ./data/epstein_fbi_files.parquet \\
        --matter-id 00000000-0000-0000-0000-000000000002 \\
        --limit 50

    # Full GPU import (fast, skip NER + MinIO)
    python scripts/import_fbi_dataset.py \\
        --file ./data/epstein_fbi_files.parquet \\
        --matter-id 00000000-0000-0000-0000-000000000002 \\
        --re-embed --disable-hnsw --skip-ner --skip-minio --concurrency 16

    # House Oversight pre-embedded
    python scripts/import_fbi_dataset.py \\
        --file ./data/house_oversight.parquet \\
        --matter-id 00000000-0000-0000-0000-000000000002 \\
        --dataset-name "House Oversight Pre-embedded" \\
        --citation-quality degraded --re-embed --skip-minio --skip-ner
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

EMBED_BATCH_SIZE = 128  # Optimal for Infinity on T4 GPU
QDRANT_BATCH_SIZE = 500  # Points per upsert call
NEO4J_BATCH_SIZE = 100  # Nodes per UNWIND query
NER_MAX_CHARS = 4_000


# ---------------------------------------------------------------------------
# Data classes (unchanged from original)
# ---------------------------------------------------------------------------


@dataclass
class ChunkRecord:
    """A single chunk from the HF dataset, ready for import."""

    text: str
    embedding: list[float]
    chunk_index: int
    source_file: str
    page_number: int | None = None
    bates_number: str | None = None
    ocr_confidence: float | None = None
    volume: str | None = None
    doc_type_hint: str | None = None
    total_pages: int | None = None


@dataclass
class DocumentGroup:
    """All chunks belonging to a single document, grouped by source_file."""

    source_file: str
    chunks: list[ChunkRecord] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        sorted_chunks = sorted(self.chunks, key=lambda c: c.chunk_index)
        return "\n\n".join(c.text for c in sorted_chunks)

    @property
    def page_count(self) -> int:
        if self.chunks and self.chunks[0].total_pages is not None:
            return self.chunks[0].total_pages
        pages = [c.page_number for c in self.chunks if c.page_number is not None]
        return max(pages) if pages else 1

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.full_text.encode("utf-8")).hexdigest()[:16]

    @property
    def metadata(self) -> dict[str, Any]:
        meta: dict[str, Any] = {"original_path": self.source_file}
        first = self.chunks[0] if self.chunks else None
        if first:
            if first.bates_number:
                meta["bates_number"] = first.bates_number
            if first.volume:
                meta["volume"] = first.volume
            if first.ocr_confidence is not None:
                avg_conf = sum(c.ocr_confidence for c in self.chunks if c.ocr_confidence is not None) / max(
                    sum(1 for c in self.chunks if c.ocr_confidence is not None), 1
                )
                meta["ocr_confidence"] = round(avg_conf, 3)
            if first.doc_type_hint:
                meta["doc_type"] = first.doc_type_hint
        return meta


# ---------------------------------------------------------------------------
# Schema detection (unchanged)
# ---------------------------------------------------------------------------

_FBI_REQUIRED = {"text", "embedding"}
_FBI_RICH_COLS = {"page_number", "bates_number", "ocr_confidence", "volume", "doc_type"}


def _resolve_col(col_set: set[str], *candidates: str) -> str | None:
    for c in candidates:
        if c in col_set:
            return c
    return None


def detect_schema(columns: list[str]) -> dict[str, str | None]:
    col_set = set(columns)
    text_col = _resolve_col(col_set, "text", "chunk_text")
    if text_col is None:
        raise ValueError(f"Dataset must have a 'text' or 'chunk_text' column, got: {columns}")
    if "embedding" not in col_set:
        raise ValueError(f"Dataset must have an 'embedding' column, got: {columns}")

    mapping: dict[str, str | None] = {
        "text": text_col,
        "embedding": "embedding",
        "source_file": _resolve_col(col_set, "source_file", "source_path", "filename", "file_name", "source"),
        "chunk_index": "chunk_index" if "chunk_index" in col_set else None,
        "page_number": "page_number" if "page_number" in col_set else None,
        "bates_number": _resolve_col(col_set, "bates_number", "bates_range"),
        "ocr_confidence": "ocr_confidence" if "ocr_confidence" in col_set else None,
        "volume": _resolve_col(col_set, "volume", "source_volume"),
        "doc_type": "doc_type" if "doc_type" in col_set else None,
        "total_pages": "total_pages" if "total_pages" in col_set else None,
    }

    rich_count = sum(1 for k in _FBI_RICH_COLS if mapping.get(k))
    schema_type = "rich (FBI-style)" if rich_count >= 3 else "sparse (House Oversight-style)"
    print(f"  Schema type: {schema_type}")
    print(f"  Mapped columns: { {k: v for k, v in mapping.items() if v} }")
    return mapping


# ---------------------------------------------------------------------------
# Parquet reader + grouping (unchanged)
# ---------------------------------------------------------------------------


def read_and_group(
    file_path: Path,
    schema_map: dict[str, str | None],
    limit: int | None = None,
) -> list[DocumentGroup]:
    import pandas as pd

    print(f"  Reading {file_path}...")
    df = pd.read_parquet(file_path)
    print(f"  Total rows: {len(df):,}")

    groups: dict[str, DocumentGroup] = {}
    chunk_count = 0

    for row in df.itertuples(index=False):
        text = str(getattr(row, schema_map["text"]))
        if not text or not text.strip():
            continue

        embedding_raw = getattr(row, schema_map["embedding"])
        embedding = list(embedding_raw) if embedding_raw is not None else []
        if not embedding:
            continue

        source_col = schema_map.get("source_file")
        source_file = str(getattr(row, source_col)) if source_col else f"doc_{chunk_count}"

        chunk_idx_col = schema_map.get("chunk_index")
        chunk_index = int(getattr(row, chunk_idx_col)) if chunk_idx_col else 0

        page_col = schema_map.get("page_number")
        page_number = None
        if page_col:
            raw_page = getattr(row, page_col)
            if raw_page is not None and str(raw_page) != "nan":
                try:
                    page_number = int(raw_page)
                except (ValueError, TypeError):
                    pass

        bates_col = schema_map.get("bates_number")
        bates_number = str(getattr(row, bates_col)) if bates_col and getattr(row, bates_col, None) else None

        conf_col = schema_map.get("ocr_confidence")
        ocr_confidence = None
        if conf_col:
            raw_conf = getattr(row, conf_col)
            if raw_conf is not None and str(raw_conf) != "nan":
                try:
                    ocr_confidence = float(raw_conf)
                except (ValueError, TypeError):
                    pass

        vol_col = schema_map.get("volume")
        volume = str(getattr(row, vol_col)) if vol_col and getattr(row, vol_col, None) else None

        dtype_col = schema_map.get("doc_type")
        doc_type_hint = str(getattr(row, dtype_col)) if dtype_col and getattr(row, dtype_col, None) else None

        tp_col = schema_map.get("total_pages")
        total_pages = None
        if tp_col:
            raw_tp = getattr(row, tp_col)
            if raw_tp is not None and str(raw_tp) != "nan":
                try:
                    total_pages = int(raw_tp)
                except (ValueError, TypeError):
                    pass

        chunk = ChunkRecord(
            text=text.strip(),
            embedding=embedding,
            chunk_index=chunk_index,
            source_file=source_file,
            page_number=page_number,
            bates_number=bates_number,
            ocr_confidence=ocr_confidence,
            volume=volume,
            doc_type_hint=doc_type_hint,
            total_pages=total_pages,
        )

        if source_file not in groups:
            groups[source_file] = DocumentGroup(source_file=source_file)
        groups[source_file].chunks.append(chunk)
        chunk_count += 1

    doc_groups = list(groups.values())
    if limit is not None:
        doc_groups = doc_groups[:limit]

    total_chunks = sum(len(g.chunks) for g in doc_groups)
    print(f"  Documents: {len(doc_groups):,}")
    print(f"  Chunks:    {total_chunks:,}")
    print(f"  Embedding dim: {len(doc_groups[0].chunks[0].embedding) if doc_groups else 'N/A'}")
    return doc_groups


# ---------------------------------------------------------------------------
# Sync DB helpers (PostgreSQL — fast, not the bottleneck)
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
    doc_group: DocumentGroup,
    matter_id: str,
    dataset_id: str | None,
    import_source: str,
) -> tuple[str, str]:
    from sqlalchemy import text

    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    filename = doc_group.source_file.split("/")[-1] if "/" in doc_group.source_file else doc_group.source_file
    metadata_json = json.dumps(doc_group.metadata, default=str)

    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO jobs (id, filename, status, stage, progress, error,
                                  matter_id, dataset_id, metadata_, created_at, updated_at)
                VALUES (:id, :filename, 'complete', 'complete', :progress, NULL,
                        :matter_id, :dataset_id, :metadata_, now(), now())
            """),
            {
                "id": job_id,
                "filename": filename,
                "matter_id": matter_id,
                "dataset_id": dataset_id,
                "metadata_": metadata_json,
                "progress": json.dumps({"chunks_created": len(doc_group.chunks), "entities_extracted": 0}),
            },
        )

        full_text = doc_group.full_text
        conn.execute(
            text("""
                INSERT INTO documents
                    (id, job_id, filename, document_type, page_count, chunk_count,
                     entity_count, minio_path, file_size_bytes, content_hash,
                     matter_id, import_source, metadata_, created_at, updated_at)
                VALUES
                    (:id, :job_id, :filename, 'document', :page_count, :chunk_count,
                     0, :minio_path, :file_size, :content_hash,
                     :matter_id, :import_source, :metadata_, now(), now())
            """),
            {
                "id": doc_id,
                "job_id": job_id,
                "filename": filename,
                "page_count": doc_group.page_count,
                "chunk_count": len(doc_group.chunks),
                "minio_path": f"raw/{job_id}/{filename}",
                "file_size": len(full_text.encode("utf-8")),
                "content_hash": doc_group.content_hash,
                "matter_id": matter_id,
                "import_source": import_source,
                "metadata_": metadata_json,
            },
        )
        conn.commit()

    return job_id, doc_id


def link_document_to_dataset(engine, doc_id: str, dataset_id: str) -> None:
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO dataset_documents (dataset_id, document_id, assigned_at)
                VALUES (:dataset_id, :doc_id, now())
                ON CONFLICT DO NOTHING
            """),
            {"dataset_id": dataset_id, "doc_id": doc_id},
        )
        conn.commit()


def lookup_dataset_id(engine, matter_id: str, dataset_name: str) -> str | None:
    from sqlalchemy import text

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id FROM datasets WHERE matter_id = :mid AND name = :name LIMIT 1"),
            {"mid": matter_id, "name": dataset_name},
        ).first()
        return str(row.id) if row else None


# ---------------------------------------------------------------------------
# MinIO upload
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


# ---------------------------------------------------------------------------
# HNSW control
# ---------------------------------------------------------------------------


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
# NER extraction (unchanged — sync, CPU-bound)
# ---------------------------------------------------------------------------


def extract_entities(chunks: list[ChunkRecord], extractor) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    entities: list[dict] = []
    for chunk in chunks:
        extracted = extractor.extract(chunk.text[:NER_MAX_CHARS])
        for ent in extracted:
            key = (ent.text.strip().lower(), ent.type)
            if key not in seen:
                seen.add(key)
                entities.append({"name": ent.text.strip(), "type": ent.type, "page_number": chunk.page_number})
    return entities


# ---------------------------------------------------------------------------
# Async pipeline — the core rewrite
# ---------------------------------------------------------------------------


@dataclass
class PreparedChunk:
    """A chunk ready for Qdrant upsert (with fresh embedding)."""

    point_id: str
    doc_id: str
    text: str
    embedding: list[float]
    chunk_index: int
    source_file: str
    matter_id: str
    citation_quality: str
    page_number: int | None = None
    bates_number: str | None = None
    ocr_confidence: float | None = None
    token_count: int = 0


async def batch_embed(
    embedder,
    chunks_with_doc: list[tuple[str, list[ChunkRecord]]],
    use_named_vectors: bool,
    matter_id: str,
    citation_quality: str,
) -> list[PreparedChunk]:
    """Embed all chunks from multiple documents in GPU-optimal batches.

    Returns PreparedChunk objects with fresh 1024d embeddings.
    """
    # Flatten all chunks across documents
    flat: list[tuple[str, ChunkRecord]] = []
    for doc_id, chunks in chunks_with_doc:
        for chunk in sorted(chunks, key=lambda c: c.chunk_index):
            flat.append((doc_id, chunk))

    if not flat:
        return []

    # Embed in batches of EMBED_BATCH_SIZE
    all_texts = [chunk.text for _, chunk in flat]
    all_embeddings: list[list[float]] = []

    for i in range(0, len(all_texts), EMBED_BATCH_SIZE):
        batch = all_texts[i : i + EMBED_BATCH_SIZE]
        batch_embeddings = await embedder.embed_texts(batch)
        if len(batch_embeddings) != len(batch):
            raise RuntimeError(
                f"Embedding batch mismatch: sent {len(batch)} texts, got {len(batch_embeddings)} vectors"
            )
        all_embeddings.extend(batch_embeddings)

    if len(all_embeddings) != len(flat):
        raise RuntimeError(f"Total embedding mismatch: {len(flat)} chunks but {len(all_embeddings)} vectors")

    # Build PreparedChunk objects
    prepared: list[PreparedChunk] = []
    for (doc_id, chunk), embedding in zip(flat, all_embeddings):
        # Verify dimension
        if len(embedding) < 512:
            raise RuntimeError(f"Embedding dimension too small: {len(embedding)} (expected 1024)")

        prepared.append(
            PreparedChunk(
                point_id=str(uuid.uuid4()),
                doc_id=doc_id,
                text=chunk.text,
                embedding=embedding,
                chunk_index=chunk.chunk_index,
                source_file=chunk.source_file,
                matter_id=matter_id,
                citation_quality=citation_quality,
                page_number=chunk.page_number,
                bates_number=chunk.bates_number,
                ocr_confidence=chunk.ocr_confidence,
                token_count=len(chunk.text.split()),
            )
        )

    return prepared


async def batch_upsert_qdrant(
    qdrant_client,
    collection_name: str,
    prepared_chunks: list[PreparedChunk],
    use_named_vectors: bool,
) -> None:
    """Upsert prepared chunks to Qdrant in batches of QDRANT_BATCH_SIZE."""
    from qdrant_client.models import PointStruct

    points: list[PointStruct] = []

    for pc in prepared_chunks:
        vector: Any = {"dense": pc.embedding} if use_named_vectors else pc.embedding
        payload: dict[str, Any] = {
            "source_file": pc.source_file,
            "chunk_text": pc.text,
            "chunk_index": pc.chunk_index,
            "doc_id": pc.doc_id,
            "matter_id": pc.matter_id,
            "token_count": pc.token_count,
            "citation_quality": pc.citation_quality,
        }
        if pc.page_number is not None:
            payload["page_number"] = pc.page_number
        if pc.bates_number:
            payload["bates_number"] = pc.bates_number
        if pc.ocr_confidence is not None:
            payload["ocr_confidence"] = pc.ocr_confidence

        points.append(PointStruct(id=pc.point_id, vector=vector, payload=payload))

        if len(points) >= QDRANT_BATCH_SIZE:
            await qdrant_client.upsert(collection_name=collection_name, points=points)
            points = []

    if points:
        await qdrant_client.upsert(collection_name=collection_name, points=points)


async def batch_index_neo4j(
    driver,
    prepared_chunks: list[PreparedChunk],
    doc_groups_by_id: dict[str, DocumentGroup],
    matter_id: str,
) -> None:
    """Create Document and Chunk nodes in Neo4j using batched UNWIND queries."""
    # Collect unique doc_ids from this batch
    doc_ids_seen: set[str] = set()
    doc_nodes: list[dict] = []
    chunk_nodes: list[dict] = []

    for pc in prepared_chunks:
        if pc.doc_id not in doc_ids_seen:
            doc_ids_seen.add(pc.doc_id)
            dg = doc_groups_by_id.get(pc.doc_id)
            if dg:
                filename = dg.source_file.split("/")[-1] if "/" in dg.source_file else dg.source_file
                doc_nodes.append(
                    {
                        "doc_id": pc.doc_id,
                        "filename": filename,
                        "doc_type": "document",
                        "page_count": dg.page_count,
                        "minio_path": f"raw/{pc.doc_id}/{filename}",
                        "matter_id": matter_id,
                    }
                )

        chunk_nodes.append(
            {
                "chunk_id": pc.point_id,
                "text_preview": pc.text[:200],
                "page_number": pc.page_number or 1,
                "qdrant_point_id": pc.point_id,
                "doc_id": pc.doc_id,
            }
        )

    async with driver.session() as session:
        # Batch create Document nodes
        if doc_nodes:
            for i in range(0, len(doc_nodes), NEO4J_BATCH_SIZE):
                batch = doc_nodes[i : i + NEO4J_BATCH_SIZE]
                await session.run(
                    """
                    UNWIND $docs AS d
                    MERGE (doc:Document {id: d.doc_id})
                    SET doc.filename = d.filename,
                        doc.doc_type = d.doc_type,
                        doc.page_count = d.page_count,
                        doc.minio_path = d.minio_path,
                        doc.matter_id = d.matter_id
                    """,
                    docs=batch,
                )

        # Batch create Chunk nodes + link to Documents
        if chunk_nodes:
            for i in range(0, len(chunk_nodes), NEO4J_BATCH_SIZE):
                batch = chunk_nodes[i : i + NEO4J_BATCH_SIZE]
                await session.run(
                    """
                    UNWIND $chunks AS c
                    MERGE (chunk:Chunk {id: c.chunk_id})
                    SET chunk.text_preview = c.text_preview,
                        chunk.page_number = c.page_number,
                        chunk.qdrant_point_id = c.qdrant_point_id
                    WITH chunk, c
                    MATCH (doc:Document {id: c.doc_id})
                    MERGE (doc)-[:HAS_CHUNK]->(chunk)
                    """,
                    chunks=batch,
                )


async def run_async_pipeline(
    doc_groups: list[DocumentGroup],
    engine,
    settings,
    matter_id: str,
    dataset_id: str | None,
    import_source: str,
    citation_quality: str,
    use_named_vectors: bool,
    skip_minio: bool,
    skip_neo4j: bool,
    re_embed: bool,
    concurrency: int,
) -> tuple[int, int, int]:
    """Main async pipeline: embed → upsert → index in batches.

    Returns (imported_docs, total_chunks, total_entities).
    """
    from qdrant_client import AsyncQdrantClient

    from app.common.vector_store import TEXT_COLLECTION
    from app.dependencies import get_embedder

    # --- Shared async clients (created once, reused for all docs) ---
    embedder = get_embedder() if re_embed else None
    qdrant = AsyncQdrantClient(url=settings.qdrant_url)

    neo4j_driver = None
    if not skip_neo4j:
        from neo4j import AsyncGraphDatabase

        neo4j_driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

    imported = 0
    total_chunks = 0
    start_time = time.time()

    # Process documents in batches of `concurrency` for pipeline efficiency
    batch_size = concurrency
    doc_groups_by_id: dict[str, DocumentGroup] = {}

    try:
        for batch_start in range(0, len(doc_groups), batch_size):
            batch = doc_groups[batch_start : batch_start + batch_size]

            # Phase 1: PostgreSQL inserts (sync, fast)
            chunks_with_doc: list[tuple[str, list[ChunkRecord]]] = []
            for doc_group in batch:
                job_id, doc_id = create_job_and_document(
                    engine,
                    doc_group,
                    matter_id,
                    dataset_id,
                    import_source,
                )
                doc_groups_by_id[doc_id] = doc_group
                chunks_with_doc.append((doc_id, doc_group.chunks))

                if dataset_id:
                    link_document_to_dataset(engine, doc_id, dataset_id)

                if not skip_minio:
                    filename = (
                        doc_group.source_file.split("/")[-1] if "/" in doc_group.source_file else doc_group.source_file
                    )
                    await asyncio.to_thread(
                        upload_to_minio, settings, f"raw/{job_id}/{filename}", doc_group.full_text.encode("utf-8")
                    )

            # Phase 2: Batch embed (async, GPU)
            if re_embed and embedder:
                prepared = await batch_embed(
                    embedder,
                    chunks_with_doc,
                    use_named_vectors,
                    matter_id,
                    citation_quality,
                )
            else:
                # Use pre-computed vectors (no re-embedding)
                prepared = []
                for doc_id, chunks in chunks_with_doc:
                    for chunk in sorted(chunks, key=lambda c: c.chunk_index):
                        prepared.append(
                            PreparedChunk(
                                point_id=str(uuid.uuid4()),
                                doc_id=doc_id,
                                text=chunk.text,
                                embedding=chunk.embedding,
                                chunk_index=chunk.chunk_index,
                                source_file=chunk.source_file,
                                matter_id=matter_id,
                                citation_quality=citation_quality,
                                page_number=chunk.page_number,
                                bates_number=chunk.bates_number,
                                ocr_confidence=chunk.ocr_confidence,
                                token_count=len(chunk.text.split()),
                            )
                        )

            # Phase 3+4: Qdrant + Neo4j in parallel (independent targets)
            coros: list = [batch_upsert_qdrant(qdrant, TEXT_COLLECTION, prepared, use_named_vectors)]
            if neo4j_driver and not skip_neo4j:
                coros.append(batch_index_neo4j(neo4j_driver, prepared, doc_groups_by_id, matter_id))

            results = await asyncio.gather(*coros, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    target = "qdrant" if i == 0 else "neo4j"
                    logger.error(f"import.{target}_batch_failed", batch_start=batch_start, error=str(result))
                    if i == 0:
                        # Qdrant failure is critical — vectors didn't land
                        raise RuntimeError(f"Qdrant upsert failed at batch {batch_start}: {result}") from result

            # Clean up doc_groups_by_id to avoid unbounded memory growth
            for doc_id, _ in chunks_with_doc:
                doc_groups_by_id.pop(doc_id, None)

            # Track progress
            imported += len(batch)
            batch_chunks = sum(len(dg.chunks) for dg in batch)
            total_chunks += batch_chunks

            if imported % 100 < batch_size or imported == len(batch):
                elapsed = time.time() - start_time
                rate = imported / elapsed if elapsed > 0 else 0
                remaining = len(doc_groups) - imported
                eta_min = (remaining / rate / 60) if rate > 0 else 0
                chunks_per_sec = total_chunks / elapsed if elapsed > 0 else 0
                print(
                    f"  [{imported:,}/{len(doc_groups):,}] "
                    f"{total_chunks:,} chunks, "
                    f"{rate:.1f} docs/sec, "
                    f"{chunks_per_sec:.0f} chunks/sec, "
                    f"ETA {eta_min:.0f}min"
                )

    except KeyboardInterrupt:
        print(f"\n  Interrupted at {imported} docs.")
    finally:
        await qdrant.close()
        if neo4j_driver:
            await neo4j_driver.close()

    return imported, total_chunks, 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:  # noqa: C901
    parser = argparse.ArgumentParser(
        description="Import pre-embedded HuggingFace dataset into NEXUS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--file", type=Path, required=True, help="Path to Parquet file")
    parser.add_argument("--matter-id", required=True, help="Target matter UUID")
    parser.add_argument("--dataset-name", default="FBI Files", help="Dataset name to link documents to")
    parser.add_argument("--limit", type=int, default=None, help="Import first N documents only")
    parser.add_argument("--dry-run", action="store_true", help="Count + inspect, no writes")
    parser.add_argument("--resume", action="store_true", help="Skip docs whose content_hash exists")
    parser.add_argument("--disable-hnsw", action="store_true", help="Disable HNSW during import, rebuild after")
    parser.add_argument("--skip-ner", action="store_true", help="Skip GLiNER entity extraction")
    parser.add_argument("--skip-neo4j", action="store_true", help="Skip Neo4j graph indexing")
    parser.add_argument("--skip-minio", action="store_true", help="Skip MinIO upload")
    parser.add_argument(
        "--re-embed", action="store_true", help="Re-embed with configured provider instead of pre-computed"
    )
    parser.add_argument(
        "--citation-quality",
        default="full",
        choices=["full", "degraded", "email"],
        help="Citation quality tier for Qdrant payload",
    )
    parser.add_argument(
        "--import-source",
        default="huggingface_pre_embedded",
        help="Value for documents.import_source column",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=16,
        help="Documents per async batch (default: 16)",
    )

    args = parser.parse_args()

    if not args.file.exists():
        print(f"Error: file '{args.file}' does not exist", file=sys.stderr)
        return 1

    try:
        uuid.UUID(args.matter_id)
    except ValueError:
        print(f"Error: '{args.matter_id}' is not a valid UUID", file=sys.stderr)
        return 1

    print("\n=== NEXUS Pre-Embedded Import (async pipeline) ===")
    print(f"  File:        {args.file}")
    print(f"  Matter:      {args.matter_id}")
    print(f"  Dataset:     {args.dataset_name}")
    print(f"  Citation:    {args.citation_quality}")
    print(f"  Re-embed:    {args.re_embed}")
    print(f"  Concurrency: {args.concurrency} docs/batch")
    if args.limit:
        print(f"  Limit:       {args.limit} documents")

    # --- Read and group ---
    import pandas as pd

    df = pd.read_parquet(args.file)
    schema_map = detect_schema(list(df.columns))
    doc_groups = read_and_group(args.file, schema_map, limit=args.limit)

    if not doc_groups:
        print("No documents found. Exiting.")
        return 0

    # --- Dry run ---
    if args.dry_run:
        total_chunks = sum(len(g.chunks) for g in doc_groups)
        total_chars = sum(len(g.full_text) for g in doc_groups)
        dim = len(doc_groups[0].chunks[0].embedding)
        print("\n--- Dry Run Summary ---")
        print(f"Documents:      {len(doc_groups):,}")
        print(f"Total chunks:   {total_chunks:,}")
        print(f"Total chars:    {total_chars:,}")
        print(f"Embedding dim:  {dim}")
        print(f"Est. Qdrant:    ~{total_chunks * dim * 4 / 1024 / 1024:.0f} MB")
        print(f"Citation tier:  {args.citation_quality}")
        sample = doc_groups[0]
        print(f"\nSample document: {sample.source_file}")
        print(f"  Chunks: {len(sample.chunks)}")
        print(f"  Pages:  {sample.page_count}")
        print(f"  Meta:   {sample.metadata}")
        print(f"  Text preview: {sample.full_text[:200]}...")
        return 0

    # --- Setup ---
    settings = _get_settings()
    engine = _get_engine()

    dataset_id = lookup_dataset_id(engine, args.matter_id, args.dataset_name)
    if dataset_id:
        print(f"  Dataset ID: {dataset_id}")
    else:
        print(f"  Warning: dataset '{args.dataset_name}' not found. Run seed_epstein_matter.py first.")

    use_named = detect_named_vectors(settings)
    print(f"  Named vectors: {use_named}")

    if args.disable_hnsw:
        disable_hnsw(settings)

    # --- Filter for resume ---
    skipped = 0
    docs_to_process: list[DocumentGroup] = []
    for doc_group in doc_groups:
        if args.resume and check_resume(engine, doc_group.content_hash, args.matter_id):
            skipped += 1
        else:
            docs_to_process.append(doc_group)

    if skipped:
        print(f"  Skipped {skipped} already-imported documents (resume mode)")

    total_chunks_target = sum(len(g.chunks) for g in docs_to_process)
    print(f"\n  Importing {len(docs_to_process):,} documents ({total_chunks_target:,} chunks)...")
    print(f"  Batch sizes: embed={EMBED_BATCH_SIZE}, qdrant={QDRANT_BATCH_SIZE}, neo4j={NEO4J_BATCH_SIZE}")

    # --- Run async pipeline ---
    start_time = time.time()
    imported, total_chunks, total_entities = asyncio.run(
        run_async_pipeline(
            docs_to_process,
            engine,
            settings,
            args.matter_id,
            dataset_id,
            args.import_source,
            args.citation_quality,
            use_named,
            args.skip_minio,
            args.skip_neo4j,
            args.re_embed,
            args.concurrency,
        )
    )

    # --- Rebuild HNSW ---
    if args.disable_hnsw:
        rebuild_hnsw(settings)

    # --- Post-ingestion hooks ---
    if imported > 0:
        print("\n  Dispatching post-ingestion hooks...")
        try:
            from app.ingestion.bulk_import import dispatch_post_ingestion_hooks

            hooks = dispatch_post_ingestion_hooks(args.matter_id)
            print(f"  Dispatched: {', '.join(hooks) or 'none'}")
        except Exception:
            logger.warning("post_ingestion.hooks_failed", exc_info=True)
            print("  Warning: post-ingestion hooks failed (non-fatal)")

    # --- Summary ---
    elapsed = time.time() - start_time
    print("\n=== Import Complete ===")
    print(f"  Imported:      {imported:,} documents")
    print(f"  Skipped:       {skipped:,}")
    print(f"  Total chunks:  {total_chunks:,}")
    print(f"  Total entities:{total_entities:,}")
    print(f"  Elapsed:       {elapsed:.1f}s ({elapsed / 60:.1f}min)")
    if imported > 0:
        print(f"  Rate:          {imported / elapsed:.1f} docs/sec ({total_chunks / elapsed:.0f} chunks/sec)")

    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
