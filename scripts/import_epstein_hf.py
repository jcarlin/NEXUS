#!/usr/bin/env python3
"""Import kabasshouse/epstein-data HuggingFace dataset into NEXUS.

Reads multi-table parquet dataset (documents, chunks, embeddings_chunk,
entities, kg_entities, kg_relationships) and imports directly into
PG/Qdrant/Neo4j, using pre-computed 768-dim gemini-embedding-001 vectors.

Pipeline (async, batched):
  1. Load HF dataset tables → join chunks + embeddings by chunk_id
  2. Group chunks by document_id
  3. Batch insert PG (job + document rows)
  4. Batch upsert Qdrant (pre-computed dense vectors, named "dense")
  5. Batch create Neo4j Document + Chunk nodes
  6. Batch import entities → Neo4j Entity nodes + MENTIONED_IN edges
  7. Import KG relationships → Neo4j weighted edges

Idempotent via content_hash — safe to re-run after interruption.

Usage::

    # Inspect dataset structure (no writes)
    python scripts/import_epstein_hf.py \\
        --matter-id 00000000-0000-0000-0000-000000000002 \\
        --inspect

    # Dry run — counts and schema preview
    python scripts/import_epstein_hf.py \\
        --matter-id 00000000-0000-0000-0000-000000000002 \\
        --dry-run --limit 100

    # Full import
    python scripts/import_epstein_hf.py \\
        --matter-id 00000000-0000-0000-0000-000000000002 \\
        --disable-hnsw --resume --concurrency 16
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
# Constants
# ---------------------------------------------------------------------------

HF_DATASET = "kabasshouse/epstein-data"
IMPORT_SOURCE = "kabasshouse/epstein-data"

QDRANT_BATCH_SIZE = 500
NEO4J_BATCH_SIZE = 200
PG_BATCH_SIZE = 50
ENTITY_BATCH_SIZE = 500

# Dataset label → NEXUS dataset name mapping
DATASET_LABEL_MAP = {
    "DataSet1": "DS1",
    "DataSet2": "DS2",
    "DataSet3": "DS3",
    "DataSet4": "DS4",
    "DataSet5": "DS5",
    "DataSet6": "DS6",
    "DataSet7": "DS7",
    "DataSet8": "DS8",
    "DataSet9": "DS9",
    "DataSet10": "DS10",
    "DataSet11": "DS11",
    "DataSet12": "DS12",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ChunkRecord:
    """A single chunk with its pre-computed embedding."""

    chunk_id: str
    text: str
    embedding: list[float]
    chunk_index: int
    token_count: int
    char_start: int | None = None
    char_end: int | None = None


@dataclass
class DocumentGroup:
    """All chunks belonging to a single document."""

    file_key: str
    full_text: str
    document_type: str
    date: str | None
    dataset_label: str
    page_number: int | None
    document_number: str | None
    char_count: int
    is_photo: bool
    has_handwriting: bool
    has_stamps: bool
    ocr_source: str | None
    additional_notes: str | None
    email_fields: dict | None
    chunks: list[ChunkRecord] = field(default_factory=list)
    entities: list[dict[str, Any]] = field(default_factory=list)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.full_text.encode("utf-8")).hexdigest()[:16]

    @property
    def page_count(self) -> int:
        return self.page_number or 1

    @property
    def metadata(self) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "dataset": self.dataset_label,
            "original_file_key": self.file_key,
        }
        if self.date:
            meta["date"] = self.date
        if self.document_number:
            meta["document_number"] = self.document_number
        if self.is_photo:
            meta["is_photo"] = True
        if self.has_handwriting:
            meta["has_handwriting"] = True
        if self.has_stamps:
            meta["has_stamps"] = True
        if self.ocr_source:
            meta["ocr_source"] = self.ocr_source
        if self.additional_notes:
            meta["additional_notes"] = self.additional_notes
        return meta


# ---------------------------------------------------------------------------
# HuggingFace dataset loading
# ---------------------------------------------------------------------------


def inspect_dataset() -> None:
    """Print the structure of the HF dataset without loading all data."""
    from datasets import load_dataset_builder

    print(f"\n=== Inspecting {HF_DATASET} ===\n")

    try:
        builder = load_dataset_builder(HF_DATASET)
        print(f"Description: {builder.info.description[:200] if builder.info.description else 'N/A'}")
        print(f"Configs: {builder.builder_configs.keys() if hasattr(builder, 'builder_configs') else 'default'}")
        if builder.info.features:
            print(f"Features: {list(builder.info.features.keys())}")
        if builder.info.splits:
            for split_name, split_info in builder.info.splits.items():
                print(f"  Split '{split_name}': {split_info.num_examples:,} rows")
    except Exception as e:
        print(f"Builder inspection failed: {e}")

    # Try loading each known config
    from datasets import get_dataset_config_names

    try:
        configs = get_dataset_config_names(HF_DATASET)
        print(f"\nAvailable configs: {configs}")
        for config in configs:
            try:
                ds = load_dataset_builder(HF_DATASET, config)
                rows = sum(s.num_examples for s in ds.info.splits.values()) if ds.info.splits else "?"
                cols = list(ds.info.features.keys()) if ds.info.features else "?"
                print(f"  {config}: {rows} rows, columns={cols}")
            except Exception as e:
                print(f"  {config}: error — {e}")
    except Exception as e:
        print(f"\nConfig enumeration failed: {e}")
        print("Trying default config...")
        from datasets import load_dataset

        ds = load_dataset(HF_DATASET, split="train", streaming=True)
        sample = next(iter(ds))
        print(f"  Columns: {list(sample.keys())}")
        print(f"  Sample: {json.dumps({k: str(v)[:100] for k, v in sample.items()}, indent=2)}")


def load_hf_tables(
    cache_dir: str | None = None,
) -> dict[str, Any]:
    """Load all HF dataset tables into memory (or streaming iterators).

    Returns a dict of table_name → pandas DataFrame.
    """
    from datasets import get_dataset_config_names, load_dataset

    tables: dict[str, Any] = {}
    configs = get_dataset_config_names(HF_DATASET)
    print(f"\n  Loading configs: {configs}")

    for config in configs:
        print(f"    Loading {config}...", end=" ", flush=True)
        try:
            ds = load_dataset(
                HF_DATASET,
                config,
                split="train",
                cache_dir=cache_dir,
            )
            tables[config] = ds
            print(f"{len(ds):,} rows")
        except Exception as e:
            print(f"FAILED: {e}")

    return tables


def build_document_groups(
    tables: dict[str, Any],
    limit: int | None = None,
) -> list[DocumentGroup]:
    """Join documents + chunks + embeddings tables into DocumentGroup objects."""

    # Load core tables as DataFrames
    docs_df = tables["documents"].to_pandas()
    chunks_df = tables["chunks"].to_pandas()

    print(f"\n  Documents table: {len(docs_df):,} rows")
    print(f"  Chunks table: {len(chunks_df):,} rows")

    # Embeddings may be in a separate table
    embeddings_df = None
    if "embeddings_chunk" in tables:
        embeddings_df = tables["embeddings_chunk"].to_pandas()
        print(f"  Embeddings table: {len(embeddings_df):,} rows")

    # Entity table (for per-document entities)
    entities_df = None
    if "entities" in tables:
        entities_df = tables["entities"].to_pandas()
        print(f"  Entities table: {len(entities_df):,} rows")

    # Apply limit on documents first (before joining)
    if limit is not None:
        docs_df = docs_df.head(limit)
        print(f"  Limited to first {limit} documents")

    # Build a set of document IDs we care about
    # The HF dataset uses numeric IDs or string IDs — detect the key
    doc_id_col = "document_id" if "document_id" in chunks_df.columns else "file_key"
    doc_key_col = "file_key"

    # Filter chunks to only documents in our set
    doc_keys = set(docs_df[doc_key_col])
    if doc_id_col == "document_id":
        # Need to map document index → file_key
        docs_df = docs_df.reset_index()
        docs_df["_row_id"] = docs_df.index
        # chunks reference documents by document_id (row index)
        chunks_filtered = chunks_df[chunks_df["document_id"].isin(docs_df["_row_id"])]
    else:
        chunks_filtered = chunks_df[chunks_df[doc_id_col].isin(doc_keys)]

    print(f"  Chunks after filter: {len(chunks_filtered):,}")

    # Merge embeddings into chunks if separate
    if embeddings_df is not None:
        chunk_id_col = "chunk_id" if "chunk_id" in embeddings_df.columns else None
        if chunk_id_col:
            chunks_filtered = chunks_filtered.reset_index()
            chunks_filtered["_chunk_row"] = chunks_filtered.index
            emb_subset = embeddings_df[embeddings_df[chunk_id_col].isin(chunks_filtered["_chunk_row"])]
            print(f"  Embeddings after filter: {len(emb_subset):,}")
        else:
            emb_subset = embeddings_df
    else:
        emb_subset = None

    # Group chunks by document
    groups: dict[str, DocumentGroup] = {}

    for _, doc_row in docs_df.iterrows():
        file_key = str(doc_row.get("file_key", ""))
        full_text = str(doc_row.get("full_text", ""))
        if not full_text or len(full_text.strip()) < 10:
            continue

        email_fields = doc_row.get("email_fields")
        if isinstance(email_fields, str):
            try:
                email_fields = json.loads(email_fields)
            except (json.JSONDecodeError, TypeError):
                email_fields = None
        elif not isinstance(email_fields, dict):
            email_fields = None

        group = DocumentGroup(
            file_key=file_key,
            full_text=full_text,
            document_type=str(doc_row.get("document_type", "document")),
            date=str(doc_row.get("date", "")) or None,
            dataset_label=str(doc_row.get("dataset", "")),
            page_number=_safe_int(doc_row.get("page_number")),
            document_number=str(doc_row.get("document_number", "")) or None,
            char_count=int(doc_row.get("char_count", len(full_text))),
            is_photo=bool(doc_row.get("is_photo", False)),
            has_handwriting=bool(doc_row.get("has_handwriting", False)),
            has_stamps=bool(doc_row.get("has_stamps", False)),
            ocr_source=str(doc_row.get("ocr_source", "")) or None,
            additional_notes=str(doc_row.get("additional_notes", "")) or None,
            email_fields=email_fields,
        )
        groups[file_key] = group

    # Assign chunks to groups
    doc_id_to_key: dict[int, str] = {}
    if "_row_id" in docs_df.columns:
        for _, row in docs_df.iterrows():
            doc_id_to_key[int(row["_row_id"])] = str(row["file_key"])

    chunks_assigned = 0
    for _, chunk_row in chunks_filtered.iterrows():
        # Resolve which document this chunk belongs to
        if doc_id_col == "document_id":
            doc_id = int(chunk_row["document_id"])
            file_key = doc_id_to_key.get(doc_id)
        else:
            file_key = str(chunk_row[doc_id_col])

        if not file_key or file_key not in groups:
            continue

        chunk_text = str(chunk_row.get("content", ""))
        if not chunk_text.strip():
            continue

        # Get embedding (from merged column or separate table)
        embedding: list[float] = []
        if "embedding" in chunk_row.index:
            raw_emb = chunk_row["embedding"]
            if raw_emb is not None:
                embedding = list(raw_emb)

        chunk_idx = _safe_int(chunk_row.get("chunk_index", chunks_assigned))
        token_count = _safe_int(chunk_row.get("token_count", len(chunk_text.split())))

        chunk = ChunkRecord(
            chunk_id=str(chunk_row.get("_chunk_row", chunks_assigned)),
            text=chunk_text,
            embedding=embedding,
            chunk_index=chunk_idx or 0,
            token_count=token_count or len(chunk_text.split()),
            char_start=_safe_int(chunk_row.get("char_start")),
            char_end=_safe_int(chunk_row.get("char_end")),
        )
        groups[file_key].chunks.append(chunk)
        chunks_assigned += 1

    # If embeddings are in a separate table, merge them in
    if emb_subset is not None and "embedding" not in chunks_filtered.columns:
        _merge_embeddings(groups, emb_subset, chunks_filtered)

    # Assign entities to groups
    if entities_df is not None:
        _assign_entities(groups, entities_df, doc_id_to_key, doc_id_col)

    # Filter out documents with no chunks or no embeddings
    result = []
    no_chunks = 0
    no_embeddings = 0
    for group in groups.values():
        if not group.chunks:
            no_chunks += 1
            continue
        if not group.chunks[0].embedding:
            no_embeddings += 1
            continue
        result.append(group)

    total_chunks = sum(len(g.chunks) for g in result)
    total_entities = sum(len(g.entities) for g in result)
    print(f"\n  Result: {len(result):,} documents, {total_chunks:,} chunks, {total_entities:,} entities")
    if no_chunks:
        print(f"  Skipped {no_chunks} documents with no chunks")
    if no_embeddings:
        print(f"  Skipped {no_embeddings} documents with no embeddings")
    if result:
        dim = len(result[0].chunks[0].embedding)
        print(f"  Embedding dim: {dim}")

    return result


def _merge_embeddings(
    groups: dict[str, DocumentGroup],
    emb_df: Any,
    chunks_df: Any,
) -> None:
    """Merge embeddings from separate table into chunk records."""
    # Build chunk_row → embedding mapping
    emb_map: dict[int, list[float]] = {}
    for _, row in emb_df.iterrows():
        chunk_id = int(row.get("chunk_id", -1))
        embedding = row.get("embedding")
        if embedding is not None:
            emb_map[chunk_id] = list(embedding)

    assigned = 0
    for group in groups.values():
        for chunk in group.chunks:
            chunk_row = int(chunk.chunk_id) if chunk.chunk_id.isdigit() else -1
            if chunk_row in emb_map:
                chunk.embedding = emb_map[chunk_row]
                assigned += 1

    print(f"  Merged {assigned:,} embeddings from separate table")


def _assign_entities(
    groups: dict[str, DocumentGroup],
    entities_df: Any,
    doc_id_to_key: dict[int, str],
    doc_id_col: str,
) -> None:
    """Assign HF entities to their parent document groups."""
    assigned = 0
    for _, row in entities_df.iterrows():
        if doc_id_col == "document_id":
            doc_id = int(row.get("document_id", -1))
            file_key = doc_id_to_key.get(doc_id)
        else:
            file_key = str(row.get(doc_id_col, ""))

        if not file_key or file_key not in groups:
            continue

        entity_type = str(row.get("entity_type", "unknown")).lower()
        value = str(row.get("value", ""))
        normalized = str(row.get("normalized_value", value))

        if not value.strip():
            continue

        groups[file_key].entities.append(
            {
                "name": normalized.strip() or value.strip(),
                "type": entity_type,
                "raw_value": value.strip(),
            }
        )
        assigned += 1

    print(f"  Assigned {assigned:,} entities to documents")


def _safe_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        v = int(val)
        return v if v == v else None  # NaN check
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Sync DB helpers (PostgreSQL)
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
) -> tuple[str, str]:
    """Create job + document rows in PostgreSQL. Returns (job_id, doc_id)."""
    from sqlalchemy import text

    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    filename = doc_group.file_key.split("/")[-1] if "/" in doc_group.file_key else doc_group.file_key
    metadata_json = json.dumps(doc_group.metadata, default=str)
    email_meta = doc_group.email_fields or {}

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
                "progress": json.dumps(
                    {
                        "chunks_created": len(doc_group.chunks),
                        "entities_extracted": len(doc_group.entities),
                    }
                ),
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
                "doc_type": doc_group.document_type or "document",
                "page_count": doc_group.page_count,
                "chunk_count": len(doc_group.chunks),
                "entity_count": len(doc_group.entities),
                "minio_path": f"raw/{job_id}/{filename}",
                "file_size": len(doc_group.full_text.encode("utf-8")),
                "content_hash": doc_group.content_hash,
                "matter_id": matter_id,
                "import_source": IMPORT_SOURCE,
                "metadata_": metadata_json,
                "message_id": email_meta.get("message_id"),
                "in_reply_to": email_meta.get("in_reply_to"),
                "references_": email_meta.get("references"),
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
# Async pipeline
# ---------------------------------------------------------------------------


async def batch_upsert_qdrant(
    qdrant_client,
    collection_name: str,
    doc_id: str,
    chunks: list[ChunkRecord],
    source_file: str,
    matter_id: str,
    use_named_vectors: bool,
) -> list[str]:
    """Upsert chunks for a single document to Qdrant. Returns point IDs."""
    from qdrant_client.models import PointStruct

    points: list[PointStruct] = []
    point_ids: list[str] = []

    for chunk in sorted(chunks, key=lambda c: c.chunk_index):
        if not chunk.embedding:
            continue

        point_id = str(uuid.uuid4())
        point_ids.append(point_id)

        vector: Any = {"dense": chunk.embedding} if use_named_vectors else chunk.embedding
        payload: dict[str, Any] = {
            "source_file": source_file,
            "chunk_text": chunk.text,
            "chunk_index": chunk.chunk_index,
            "doc_id": doc_id,
            "matter_id": matter_id,
            "token_count": chunk.token_count,
        }
        if chunk.char_start is not None:
            payload["char_start"] = chunk.char_start
        if chunk.char_end is not None:
            payload["char_end"] = chunk.char_end

        points.append(PointStruct(id=point_id, vector=vector, payload=payload))

    # Batch upsert
    for i in range(0, len(points), QDRANT_BATCH_SIZE):
        batch = points[i : i + QDRANT_BATCH_SIZE]
        await qdrant_client.upsert(collection_name=collection_name, points=batch)

    return point_ids


async def batch_index_neo4j(
    driver,
    doc_id: str,
    doc_group: DocumentGroup,
    point_ids: list[str],
    matter_id: str,
) -> None:
    """Create Document + Chunk nodes + Entity nodes in Neo4j for one document."""
    filename = doc_group.file_key.split("/")[-1] if "/" in doc_group.file_key else doc_group.file_key

    async with driver.session() as session:
        # Create Document node
        await session.run(
            """
            MERGE (doc:Document {id: $doc_id})
            SET doc.filename = $filename,
                doc.doc_type = $doc_type,
                doc.page_count = $page_count,
                doc.minio_path = $minio_path,
                doc.matter_id = $matter_id
            """,
            doc_id=doc_id,
            filename=filename,
            doc_type=doc_group.document_type or "document",
            page_count=doc_group.page_count,
            minio_path=f"raw/{doc_id}/{filename}",
            matter_id=matter_id,
        )

        # Create Chunk nodes + PART_OF edges (batched)
        sorted_chunks = sorted(doc_group.chunks, key=lambda c: c.chunk_index)
        chunk_nodes = []
        for chunk, pid in zip(sorted_chunks, point_ids):
            chunk_nodes.append(
                {
                    "chunk_id": pid,
                    "text_preview": chunk.text[:200],
                    "page_number": 1,
                    "qdrant_point_id": pid,
                }
            )

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
                MATCH (doc:Document {id: $doc_id})
                MERGE (doc)-[:HAS_CHUNK]->(chunk)
                """,
                chunks=batch,
                doc_id=doc_id,
            )

        # Create Entity nodes + MENTIONED_IN edges (batched)
        if doc_group.entities:
            entity_nodes = [{"name": e["name"], "type": e["type"]} for e in doc_group.entities if e.get("name")]
            for i in range(0, len(entity_nodes), ENTITY_BATCH_SIZE):
                batch = entity_nodes[i : i + ENTITY_BATCH_SIZE]
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
                    entities=batch,
                    matter_id=matter_id,
                    doc_id=doc_id,
                )


async def import_kg(driver, tables: dict[str, Any], matter_id: str) -> None:
    """Import curated KG entities and relationships from HF dataset."""
    if "kg_entities" not in tables or "kg_relationships" not in tables:
        print("  No KG tables found, skipping.")
        return

    kg_entities = tables["kg_entities"].to_pandas()
    kg_rels = tables["kg_relationships"].to_pandas()
    print(f"\n  Importing KG: {len(kg_entities)} entities, {len(kg_rels)} relationships")

    async with driver.session() as session:
        # Import KG entities (with descriptions)
        for i in range(0, len(kg_entities), ENTITY_BATCH_SIZE):
            batch = []
            for _, row in kg_entities.iloc[i : i + ENTITY_BATCH_SIZE].iterrows():
                batch.append(
                    {
                        "name": str(row.get("name", "")),
                        "type": str(row.get("entity_type", "unknown")).lower(),
                        "description": str(row.get("description", "")),
                    }
                )
            await session.run(
                """
                UNWIND $entities AS e
                MERGE (ent:Entity {name: e.name, type: e.type, matter_id: $matter_id})
                SET ent.description = e.description,
                    ent.kg_curated = true
                """,
                entities=batch,
                matter_id=matter_id,
            )

        # Import KG relationships
        for i in range(0, len(kg_rels), NEO4J_BATCH_SIZE):
            batch = []
            for _, row in kg_rels.iloc[i : i + NEO4J_BATCH_SIZE].iterrows():
                batch.append(
                    {
                        "source": str(row.get("source_id", "")),
                        "target": str(row.get("target_id", "")),
                        "rel_type": str(row.get("relationship_type", "RELATED_TO")),
                        "weight": float(row.get("weight", 1.0)),
                        "evidence": str(row.get("evidence", "")),
                    }
                )
            await session.run(
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
                rels=batch,
                matter_id=matter_id,
            )

    print(f"  KG import complete: {len(kg_entities)} entities, {len(kg_rels)} relationships")


async def run_async_pipeline(
    doc_groups: list[DocumentGroup],
    tables: dict[str, Any],
    engine,
    settings,
    matter_id: str,
    dataset_id: str | None,
    use_named_vectors: bool,
    skip_minio: bool,
    skip_neo4j: bool,
    concurrency: int,
) -> tuple[int, int, int]:
    """Main async pipeline. Returns (imported_docs, total_chunks, total_entities)."""
    from qdrant_client import AsyncQdrantClient

    from app.common.vector_store import TEXT_COLLECTION

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
    total_entities = 0
    start_time = time.time()

    try:
        for batch_start in range(0, len(doc_groups), concurrency):
            batch = doc_groups[batch_start : batch_start + concurrency]

            for doc_group in batch:
                # Phase 1: PostgreSQL (sync, fast)
                job_id, doc_id = create_job_and_document(
                    engine,
                    doc_group,
                    matter_id,
                    dataset_id,
                )

                if dataset_id:
                    link_document_to_dataset(engine, doc_id, dataset_id)

                # Phase 2: MinIO (optional)
                if not skip_minio:
                    filename = doc_group.file_key.split("/")[-1] if "/" in doc_group.file_key else doc_group.file_key
                    await asyncio.to_thread(
                        upload_to_minio,
                        settings,
                        f"raw/{job_id}/{filename}",
                        doc_group.full_text.encode("utf-8"),
                    )

                # Phase 3: Qdrant upsert (pre-computed embeddings)
                point_ids = await batch_upsert_qdrant(
                    qdrant,
                    TEXT_COLLECTION,
                    doc_id,
                    doc_group.chunks,
                    doc_group.file_key,
                    matter_id,
                    use_named_vectors,
                )

                # Phase 4: Neo4j (Document + Chunk + Entity nodes)
                if neo4j_driver and not skip_neo4j:
                    try:
                        await batch_index_neo4j(
                            neo4j_driver,
                            doc_id,
                            doc_group,
                            point_ids,
                            matter_id,
                        )
                    except Exception as e:
                        logger.warning("import.neo4j_failed", doc=doc_group.file_key, error=str(e))

                imported += 1
                total_chunks += len(doc_group.chunks)
                total_entities += len(doc_group.entities)

            # Progress report
            if imported % 100 < concurrency or imported == len(doc_groups):
                elapsed = time.time() - start_time
                rate = imported / elapsed if elapsed > 0 else 0
                remaining = len(doc_groups) - imported
                eta_min = (remaining / rate / 60) if rate > 0 else 0
                print(
                    f"  [{imported:,}/{len(doc_groups):,}] "
                    f"{total_chunks:,} chunks, "
                    f"{total_entities:,} entities, "
                    f"{rate:.1f} docs/sec, "
                    f"ETA {eta_min:.0f}min"
                )

        # Phase 5: Import KG entities and relationships
        if neo4j_driver and not skip_neo4j:
            await import_kg(neo4j_driver, tables, matter_id)

    except KeyboardInterrupt:
        print(f"\n  Interrupted at {imported} docs.")
    finally:
        await qdrant.close()
        if neo4j_driver:
            await neo4j_driver.close()

    return imported, total_chunks, total_entities


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:  # noqa: C901
    parser = argparse.ArgumentParser(
        description="Import kabasshouse/epstein-data HuggingFace dataset into NEXUS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--matter-id", required=True, help="Target matter UUID")
    parser.add_argument("--dataset-name", default=None, help="NEXUS dataset name to link to")
    parser.add_argument("--limit", type=int, default=None, help="Import first N documents only")
    parser.add_argument("--inspect", action="store_true", help="Inspect HF dataset structure and exit")
    parser.add_argument("--dry-run", action="store_true", help="Count + inspect, no writes")
    parser.add_argument("--resume", action="store_true", help="Skip docs whose content_hash exists")
    parser.add_argument("--disable-hnsw", action="store_true", help="Disable HNSW during import, rebuild after")
    parser.add_argument("--skip-neo4j", action="store_true", help="Skip Neo4j graph indexing")
    parser.add_argument("--skip-minio", action="store_true", help="Skip MinIO upload of text files")
    parser.add_argument("--cache-dir", default=None, help="HF datasets cache directory")
    parser.add_argument("--concurrency", type=int, default=16, help="Documents per batch (default: 16)")

    args = parser.parse_args()

    # Inspect mode
    if args.inspect:
        inspect_dataset()
        return 0

    try:
        uuid.UUID(args.matter_id)
    except ValueError:
        print(f"Error: '{args.matter_id}' is not a valid UUID", file=sys.stderr)
        return 1

    print(f"\n=== NEXUS HF Import: {HF_DATASET} ===")
    print(f"  Matter:      {args.matter_id}")
    print(f"  Concurrency: {args.concurrency} docs/batch")
    if args.limit:
        print(f"  Limit:       {args.limit} documents")

    # Load HF tables
    tables = load_hf_tables(cache_dir=args.cache_dir)
    if "documents" not in tables:
        print("Error: 'documents' config not found in HF dataset", file=sys.stderr)
        return 1

    # Build document groups
    doc_groups = build_document_groups(tables, limit=args.limit)
    if not doc_groups:
        print("No documents found. Exiting.")
        return 0

    # Dry run
    if args.dry_run:
        total_chunks = sum(len(g.chunks) for g in doc_groups)
        total_chars = sum(g.char_count for g in doc_groups)
        total_entities = sum(len(g.entities) for g in doc_groups)
        dim = len(doc_groups[0].chunks[0].embedding) if doc_groups[0].chunks else 0

        print("\n--- Dry Run Summary ---")
        print(f"Documents:      {len(doc_groups):,}")
        print(f"Total chunks:   {total_chunks:,}")
        print(f"Total chars:    {total_chars:,}")
        print(f"Total entities: {total_entities:,}")
        print(f"Embedding dim:  {dim}")
        print(f"Est. Qdrant:    ~{total_chunks * dim * 4 / 1024 / 1024:.0f} MB")

        # Dataset distribution
        datasets: dict[str, int] = {}
        for g in doc_groups:
            label = g.dataset_label or "unknown"
            datasets[label] = datasets.get(label, 0) + 1
        print("\nDataset distribution:")
        for label, count in sorted(datasets.items(), key=lambda x: -x[1]):
            print(f"  {label}: {count:,}")

        # Sample
        sample = doc_groups[0]
        print(f"\nSample: {sample.file_key}")
        print(f"  Type:     {sample.document_type}")
        print(f"  Dataset:  {sample.dataset_label}")
        print(f"  Chunks:   {len(sample.chunks)}")
        print(f"  Entities: {len(sample.entities)}")
        print(f"  Meta:     {sample.metadata}")
        print(f"  Text:     {sample.full_text[:200]}...")
        return 0

    # Setup
    settings = _get_settings()
    engine = _get_engine()

    dataset_id = None
    if args.dataset_name:
        dataset_id = lookup_dataset_id(engine, args.matter_id, args.dataset_name)
        if dataset_id:
            print(f"  Dataset ID: {dataset_id}")
        else:
            print(f"  Warning: dataset '{args.dataset_name}' not found")

    use_named = detect_named_vectors(settings)
    print(f"  Named vectors: {use_named}")

    if args.disable_hnsw:
        disable_hnsw(settings)

    # Filter for resume
    skipped = 0
    docs_to_process: list[DocumentGroup] = []
    if args.resume:
        print("  Checking for already-imported documents...")
        for doc_group in doc_groups:
            if check_resume(engine, doc_group.content_hash, args.matter_id):
                skipped += 1
            else:
                docs_to_process.append(doc_group)
        print(f"  Skipped {skipped:,} already-imported documents (resume mode)")
    else:
        docs_to_process = doc_groups

    total_chunks_target = sum(len(g.chunks) for g in docs_to_process)
    print(f"\n  Importing {len(docs_to_process):,} documents ({total_chunks_target:,} chunks)...")

    # Run
    start_time = time.time()
    imported, total_chunks, total_entities = asyncio.run(
        run_async_pipeline(
            docs_to_process,
            tables,
            engine,
            settings,
            args.matter_id,
            dataset_id,
            use_named,
            args.skip_minio,
            args.skip_neo4j,
            args.concurrency,
        )
    )

    # Rebuild HNSW
    if args.disable_hnsw:
        rebuild_hnsw(settings)

    # Post-ingestion hooks
    if imported > 0:
        print("\n  Dispatching post-ingestion hooks...")
        try:
            from app.ingestion.bulk_import import dispatch_post_ingestion_hooks

            hooks = dispatch_post_ingestion_hooks(args.matter_id)
            print(f"  Dispatched: {', '.join(hooks) or 'none'}")
        except Exception:
            logger.warning("post_ingestion.hooks_failed", exc_info=True)
            print("  Warning: post-ingestion hooks failed (non-fatal)")

    # Summary
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
