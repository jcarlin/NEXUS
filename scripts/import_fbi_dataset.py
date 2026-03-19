#!/usr/bin/env python3
"""Import pre-chunked + pre-embedded HuggingFace datasets into NEXUS.

Designed for datasets like ``svetfm/epstein-fbi-files`` and
``svetfm/epstein-files-nov11-25-house-post-ocr-embeddings`` that ship
with pre-computed 768d nomic-embed-text vectors.

Pipeline per document:
  1. PostgreSQL: jobs + documents rows
  2. MinIO: upload concatenated text
  3. Qdrant: upsert pre-computed vectors (no embedding API call)
  4. GLiNER NER: entity extraction on each chunk
  5. Neo4j: Document, Entity, Chunk nodes + edges

Usage::

    # Local test (50 docs)
    python scripts/import_fbi_dataset.py \\
        --file ./data/epstein_fbi_files/epstein_fbi_files.parquet \\
        --matter-id 00000000-0000-0000-0000-000000000002 \\
        --limit 50

    # Full GCP import
    python scripts/import_fbi_dataset.py \\
        --file ./data/epstein_fbi_files/epstein_fbi_files.parquet \\
        --matter-id 00000000-0000-0000-0000-000000000002 \\
        --disable-hnsw

    # House Oversight pre-embedded (auto-detects simpler schema)
    python scripts/import_fbi_dataset.py \\
        --file ./data/house_oversight/house_oversight.parquet \\
        --matter-id 00000000-0000-0000-0000-000000000002 \\
        --dataset-name "House Oversight Pre-embedded"

    # Re-embed with local Ollama instead of using pre-computed vectors
    python scripts/import_fbi_dataset.py \\
        --file ./data/fbi.parquet --matter-id ... --re-embed
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

QDRANT_BATCH_SIZE = 100
NER_MAX_CHARS = 4_000


# ---------------------------------------------------------------------------
# Data classes
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
# Schema detection
# ---------------------------------------------------------------------------

_FBI_REQUIRED = {"text", "embedding"}
_FBI_RICH_COLS = {"page_number", "bates_number", "ocr_confidence", "volume", "doc_type"}


def _resolve_col(col_set: set[str], *candidates: str) -> str | None:
    """Return the first column name from candidates found in the dataset."""
    for c in candidates:
        if c in col_set:
            return c
    return None


def detect_schema(columns: list[str]) -> dict[str, str | None]:
    """Map dataset columns to our internal field names.

    Returns a dict of internal_name -> actual_column_name (or None if absent).
    Supports the rich FBI JSONL schema (chunk_text, source_path, source_volume),
    the FBI Parquet schema (text, source_file, volume), and the sparse House
    Oversight schema.
    """
    col_set = set(columns)

    # Text column: "text" or "chunk_text" (FBI JSONL uses chunk_text)
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
    }

    rich_count = sum(1 for k in _FBI_RICH_COLS if mapping.get(k))
    schema_type = "rich (FBI-style)" if rich_count >= 3 else "sparse (House Oversight-style)"
    print(f"  Schema type: {schema_type}")
    print(f"  Mapped columns: { {k: v for k, v in mapping.items() if v} }")

    return mapping


# ---------------------------------------------------------------------------
# Parquet reader + grouping
# ---------------------------------------------------------------------------


def read_and_group(
    file_path: Path,
    schema_map: dict[str, str | None],
    limit: int | None = None,
) -> list[DocumentGroup]:
    """Read Parquet file and group chunks by source document."""
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
# DB helpers (sync, direct — no Celery)
# ---------------------------------------------------------------------------


def _get_engine():
    from sqlalchemy import create_engine

    from app.config import Settings

    settings = Settings()
    return create_engine(settings.postgres_url_sync, pool_pre_ping=True)


def _get_settings():
    from app.config import Settings

    return Settings()


def check_resume(engine, content_hash: str, matter_id: str) -> bool:
    """Return True if a document with this content hash already exists."""
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
    """Create a job row and a document row. Returns (job_id, doc_id)."""
    from sqlalchemy import text

    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    filename = doc_group.source_file.split("/")[-1] if "/" in doc_group.source_file else doc_group.source_file
    metadata_json = json.dumps(doc_group.metadata, default=str)

    with engine.connect() as conn:
        # Job row
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
                        "entities_extracted": 0,
                    }
                ),
            },
        )

        # Document row
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


def update_entity_count(engine, doc_id: str, count: int) -> None:
    """Update the entity_count on a document row."""
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(
            text("UPDATE documents SET entity_count = :count WHERE id = :id"),
            {"count": count, "id": doc_id},
        )
        conn.commit()


def link_document_to_dataset(engine, doc_id: str, dataset_id: str) -> None:
    """Insert into dataset_documents junction table."""
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
    """Find a dataset ID by name within a matter."""
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
    """Upload bytes to MinIO."""
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
# Qdrant upsert
# ---------------------------------------------------------------------------


def upsert_chunks_to_qdrant(
    settings,
    doc_id: str,
    doc_group: DocumentGroup,
    matter_id: str,
    citation_quality: str = "full",
    use_named_vectors: bool = True,
) -> list[dict]:
    """Upsert pre-embedded chunks to Qdrant. Returns chunk_data for Neo4j."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct

    from app.common.vector_store import TEXT_COLLECTION

    qdrant = QdrantClient(url=settings.qdrant_url)
    points: list[PointStruct] = []
    chunk_data_for_neo4j: list[dict] = []

    for chunk in sorted(doc_group.chunks, key=lambda c: c.chunk_index):
        point_id = str(uuid.uuid4())

        payload: dict[str, Any] = {
            "source_file": doc_group.source_file,
            "chunk_text": chunk.text,
            "chunk_index": chunk.chunk_index,
            "doc_id": doc_id,
            "matter_id": matter_id,
            "token_count": len(chunk.text.split()),
            "citation_quality": citation_quality,
        }

        if chunk.page_number is not None:
            payload["page_number"] = chunk.page_number
        if chunk.bates_number:
            payload["bates_number"] = chunk.bates_number
        if chunk.ocr_confidence is not None:
            payload["ocr_confidence"] = chunk.ocr_confidence

        # Use named vectors (dense) for collections with sparse support,
        # or unnamed vectors for simple collections
        if use_named_vectors:
            vector: Any = {"dense": chunk.embedding}
        else:
            vector = chunk.embedding

        points.append(PointStruct(id=point_id, vector=vector, payload=payload))
        chunk_data_for_neo4j.append(
            {
                "chunk_id": point_id,
                "text_preview": chunk.text[:200],
                "page_number": chunk.page_number or 1,
                "qdrant_point_id": point_id,
            }
        )

        # Batch upsert
        if len(points) >= QDRANT_BATCH_SIZE:
            qdrant.upsert(collection_name=TEXT_COLLECTION, points=points)
            points = []

    # Flush remaining
    if points:
        qdrant.upsert(collection_name=TEXT_COLLECTION, points=points)

    return chunk_data_for_neo4j


# ---------------------------------------------------------------------------
# NER extraction
# ---------------------------------------------------------------------------


def extract_entities(chunks: list[ChunkRecord], extractor) -> list[dict]:
    """Run GLiNER NER on all chunks, deduplicating entities."""
    seen: set[tuple[str, str]] = set()
    entities: list[dict] = []

    for chunk in chunks:
        extracted = extractor.extract(chunk.text[:NER_MAX_CHARS])
        for ent in extracted:
            key = (ent.text.strip().lower(), ent.type)
            if key not in seen:
                seen.add(key)
                entities.append(
                    {
                        "name": ent.text.strip(),
                        "type": ent.type,
                        "page_number": chunk.page_number,
                    }
                )

    return entities


# ---------------------------------------------------------------------------
# Neo4j indexing
# ---------------------------------------------------------------------------


async def index_to_neo4j(
    settings,
    doc_id: str,
    doc_group: DocumentGroup,
    entities: list[dict],
    chunk_data: list[dict],
    matter_id: str,
) -> None:
    """Create Document, Entity, and Chunk nodes in Neo4j."""
    from neo4j import AsyncGraphDatabase

    from app.entities.graph_service import GraphService

    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        gs = GraphService(driver)
        filename = doc_group.source_file.split("/")[-1] if "/" in doc_group.source_file else doc_group.source_file

        await gs.create_document_node(
            doc_id=doc_id,
            filename=filename,
            doc_type="document",
            page_count=doc_group.page_count,
            minio_path=f"raw/{doc_id}/{filename}",
            matter_id=matter_id,
        )

        if entities:
            await gs.index_entities_for_document(
                doc_id=doc_id,
                entities=entities,
                matter_id=matter_id,
            )

        for cd in chunk_data:
            await gs.create_chunk_node(
                chunk_id=cd["chunk_id"],
                text_preview=cd["text_preview"],
                page_number=cd.get("page_number", 1),
                qdrant_point_id=cd["qdrant_point_id"],
                doc_id=doc_id,
            )
    finally:
        await driver.close()


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


# ---------------------------------------------------------------------------
# Qdrant collection introspection
# ---------------------------------------------------------------------------


def detect_named_vectors(settings) -> bool:
    """Check if the nexus_text collection uses named vectors."""
    from qdrant_client import QdrantClient

    from app.common.vector_store import TEXT_COLLECTION

    client = QdrantClient(url=settings.qdrant_url)
    try:
        info = client.get_collection(TEXT_COLLECTION)
        return isinstance(info.config.params.vectors, dict)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Main import loop
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
    parser.add_argument("--re-embed", action="store_true", help="Re-embed with local provider instead of pre-computed")
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

    args = parser.parse_args()

    # Validate
    if not args.file.exists():
        print(f"Error: file '{args.file}' does not exist", file=sys.stderr)
        return 1

    try:
        uuid.UUID(args.matter_id)
    except ValueError:
        print(f"Error: '{args.matter_id}' is not a valid UUID", file=sys.stderr)
        return 1

    print("\n=== NEXUS Pre-Embedded Import ===")
    print(f"  File:       {args.file}")
    print(f"  Matter:     {args.matter_id}")
    print(f"  Dataset:    {args.dataset_name}")
    print(f"  Citation:   {args.citation_quality}")
    if args.limit:
        print(f"  Limit:      {args.limit} documents")

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

        # Schema sample
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

    # Lookup dataset ID
    dataset_id = lookup_dataset_id(engine, args.matter_id, args.dataset_name)
    if dataset_id:
        print(f"  Dataset ID: {dataset_id}")
    else:
        print(f"  Warning: dataset '{args.dataset_name}' not found. Run seed_epstein_matter.py first.")

    # Named vectors detection
    use_named = detect_named_vectors(settings)
    print(f"  Named vectors: {use_named}")

    # HNSW control
    if args.disable_hnsw:
        disable_hnsw(settings)

    # NER setup
    extractor = None
    if not args.skip_ner:
        from app.entities.extractor import EntityExtractor

        extractor = EntityExtractor(model_name=settings.gliner_model)
        print("  GLiNER NER: enabled (loading model on first use)")
    else:
        print("  GLiNER NER: skipped")

    # --- Import loop ---
    start_time = time.time()
    imported = 0
    skipped = 0
    total_chunks_imported = 0
    total_entities = 0

    print(f"\n  Importing {len(doc_groups):,} documents...")

    try:
        for i, doc_group in enumerate(doc_groups):
            # Resume check
            if args.resume and check_resume(engine, doc_group.content_hash, args.matter_id):
                skipped += 1
                continue

            # 1. PostgreSQL: job + document
            job_id, doc_id = create_job_and_document(
                engine,
                doc_group,
                args.matter_id,
                dataset_id,
                args.import_source,
            )

            # 2. MinIO: upload concatenated text
            if not args.skip_minio:
                filename = (
                    doc_group.source_file.split("/")[-1] if "/" in doc_group.source_file else doc_group.source_file
                )
                minio_key = f"raw/{job_id}/{filename}"
                upload_to_minio(settings, minio_key, doc_group.full_text.encode("utf-8"))

            # 3. Qdrant: upsert pre-computed vectors
            chunk_data = upsert_chunks_to_qdrant(
                settings,
                doc_id,
                doc_group,
                args.matter_id,
                citation_quality=args.citation_quality,
                use_named_vectors=use_named,
            )
            total_chunks_imported += len(doc_group.chunks)

            # 4. NER
            entities: list[dict] = []
            if extractor:
                entities = extract_entities(doc_group.chunks, extractor)
                total_entities += len(entities)
                if entities:
                    update_entity_count(engine, doc_id, len(entities))

            # 5. Neo4j
            if not args.skip_neo4j:
                try:
                    asyncio.run(
                        index_to_neo4j(
                            settings,
                            doc_id,
                            doc_group,
                            entities,
                            chunk_data,
                            args.matter_id,
                        )
                    )
                except Exception:
                    logger.warning("neo4j.index_failed", doc_id=doc_id, exc_info=True)

            # 6. Dataset link
            if dataset_id:
                link_document_to_dataset(engine, doc_id, dataset_id)

            imported += 1

            # Progress
            if imported % 100 == 0 or imported == 1:
                elapsed = time.time() - start_time
                rate = imported / elapsed if elapsed > 0 else 0
                eta_secs = (len(doc_groups) - imported - skipped) / rate if rate > 0 else 0
                eta_min = eta_secs / 60
                print(
                    f"  [{imported:,}/{len(doc_groups):,}] "
                    f"{skipped} skipped, {total_chunks_imported:,} chunks, "
                    f"{total_entities:,} entities — "
                    f"{rate:.1f} docs/sec, ETA {eta_min:.0f}min"
                )

    except KeyboardInterrupt:
        print(f"\n  Interrupted! Imported {imported}, skipped {skipped}.")

    # --- Rebuild HNSW ---
    if args.disable_hnsw:
        rebuild_hnsw(settings)

    # --- Post-ingestion hooks ---
    if imported > 0 and not args.dry_run:
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
    print(f"  Total chunks:  {total_chunks_imported:,}")
    print(f"  Total entities:{total_entities:,}")
    print(f"  Elapsed:       {elapsed:.1f}s ({elapsed / 60:.1f}min)")
    if imported > 0:
        print(f"  Rate:          {imported / elapsed:.1f} docs/sec")

    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
