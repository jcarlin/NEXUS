#!/usr/bin/env python3
“””
Import Epstein files from HuggingFace into NEXUS.

Handles the critical 768d vs 1024d dimension mismatch:

- NEXUS nexus_text collection uses 1024d (OpenAI/BGE-M3)
- HuggingFace datasets use 768d (nomic-embed-text)

Two modes:
–use-precomputed   Load 768d vectors into a separate ‘nexus_epstein_768’ collection.
Fast (minutes). Requires ONE retriever patch (see note at bottom).
–re-embed          Re-embed chunks via NEXUS’s configured EMBEDDING_PROVIDER.
Loads into existing nexus_text collection. No code changes needed.
Slower: ~30 min CPU (FastEmbed ONNX) or ~$5 OpenAI Batch API.

Datasets:
fbi    - svetfm/epstein-fbi-files       (236K chunks, Bates+page+OCR, recommended)
house  - svetfm/epstein-files-nov11-25-house-post-ocr-embeddings (69K, minimal metadata)

Usage (run inside Docker api container on GCP VM):
python scripts/import_epstein_fbi.py \
–matter-id <uuid> \
–dataset fbi \
–use-precomputed \
[–dry-run] [–limit 1000] [–resume]
“””

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Iterator

import structlog

# —————————————————————————

# Logging

# —————————————————————————

structlog.configure(
processors=[
structlog.processors.TimeStamper(fmt=“iso”),
structlog.processors.add_log_level,
structlog.dev.ConsoleRenderer(),
]
)
log = structlog.get_logger()

# —————————————————————————

# Constants

# —————————————————————————

FBI_DATASET    = “svetfm/epstein-fbi-files”
HOUSE_DATASET  = “svetfm/epstein-files-nov11-25-house-post-ocr-embeddings”

PRECOMPUTED_COLLECTION = “nexus_epstein_768”   # separate 768d collection
NEXUS_COLLECTION       = “nexus_text”           # existing 1024d collection (re-embed mode)

PRECOMPUTED_DIM = 768
NEXUS_DIM       = 1024  # matches VectorParams in app/common/vector_store.py

DEFAULT_BATCH_SIZE = 500
DEFAULT_FILE_TYPE  = “pdf”
DEFAULT_PRIVILEGE  = “not_reviewed”

# —————————————————————————

# Argument parsing

# —————————————————————————

def parse_args() -> argparse.Namespace:
p = argparse.ArgumentParser(description=“Import Epstein files into NEXUS”)
p.add_argument(”–matter-id”, required=True, help=“Matter UUID (must exist in case_matters)”)
p.add_argument(”–dataset”, choices=[“fbi”, “house”], default=“fbi”,
help=“Which HuggingFace dataset to import (default: fbi)”)
p.add_argument(”–use-precomputed”, action=“store_true”,
help=“Use pre-computed 768d embeddings → nexus_epstein_768 collection”)
p.add_argument(”–re-embed”, action=“store_true”,
help=“Re-embed via EMBEDDING_PROVIDER → nexus_text collection (1024d)”)
p.add_argument(”–dry-run”, action=“store_true”,
help=“Print stats only, no writes”)
p.add_argument(”–limit”, type=int, default=None,
help=“Only import first N chunks (for testing)”)
p.add_argument(”–batch-size”, type=int, default=DEFAULT_BATCH_SIZE,
help=f”Qdrant upsert batch size (default: {DEFAULT_BATCH_SIZE})”)
p.add_argument(”–resume”, action=“store_true”,
help=“Skip source_files already present in Qdrant payload”)
args = p.parse_args()

```
if not args.use_precomputed and not args.re_embed:
    p.error("Must specify either --use-precomputed or --re-embed")
if args.use_precomputed and args.re_embed:
    p.error("Cannot specify both --use-precomputed and --re-embed")

try:
    uuid.UUID(args.matter_id)
except ValueError:
    p.error(f"--matter-id must be a valid UUID, got: {args.matter_id}")

return args
```

# —————————————————————————

# Database helpers (raw SQL matching NEXUS patterns from app/ingestion/service.py)

# —————————————————————————

async def get_db_engine():
“”“Create async SQLAlchemy engine from DATABASE_URL env var.”””
from sqlalchemy.ext.asyncio import create_async_engine
db_url = os.environ[“DATABASE_URL”]
# Convert postgres:// → postgresql+asyncpg://
db_url = db_url.replace(“postgresql://”, “postgresql+asyncpg://”)
db_url = db_url.replace(“postgres://”, “postgresql+asyncpg://”)
return create_async_engine(db_url, pool_size=5, max_overflow=10)

async def verify_matter_exists(engine, matter_id: str) -> dict:
“”“Verify matter exists and return its name.”””
from sqlalchemy import text
async with engine.begin() as conn:
row = await conn.execute(
text(“SELECT id, name FROM case_matters WHERE id = :mid”),
{“mid”: matter_id}
)
result = row.fetchone()
if not result:
log.error(“matter_not_found”, matter_id=matter_id)
sys.exit(1)
return {“id”: str(result[0]), “name”: result[1]}

async def get_existing_doc_ids(engine, matter_id: str) -> dict[str, str]:
“”“Return {filename: document_id} for already-imported docs in this matter.”””
from sqlalchemy import text
async with engine.begin() as conn:
rows = await conn.execute(
text(“SELECT filename, id::text FROM documents WHERE matter_id = :mid”),
{“mid”: matter_id}
)
return {r[0]: r[1] for r in rows.fetchall()}

async def insert_document(
conn,
matter_id: str,
filename: str,
bates_begin: str | None,
bates_end: str | None,
file_type: str,
source_dataset: str,
chunk_count: int,
) -> str:
“””
Insert a document record into PostgreSQL. Returns generated document UUID.
Matches documents table schema including migration 010 (bates_begin/bates_end).
“””
from sqlalchemy import text
doc_id = str(uuid.uuid4())
now = datetime.now(timezone.utc)

```
# Build import_source metadata JSON
import_source = json.dumps({
    "type": "huggingface",
    "dataset": source_dataset,
    "imported_at": now.isoformat(),
})

await conn.execute(
    text("""
        INSERT INTO documents (
            id, matter_id, filename, file_type,
            privilege_status, status,
            bates_begin, bates_end,
            import_source, chunk_count,
            created_at, updated_at
        ) VALUES (
            :id::uuid, :matter_id::uuid, :filename, :file_type,
            :privilege_status, :status,
            :bates_begin, :bates_end,
            :import_source, :chunk_count,
            :now, :now
        )
        ON CONFLICT (id) DO NOTHING
    """),
    {
        "id": doc_id,
        "matter_id": matter_id,
        "filename": filename,
        "file_type": file_type,
        "privilege_status": DEFAULT_PRIVILEGE,
        "status": "complete",
        "bates_begin": bates_begin,
        "bates_end": bates_end,
        "import_source": import_source,
        "chunk_count": chunk_count,
        "now": now,
    }
)
return doc_id
```

# —————————————————————————

# Qdrant helpers

# —————————————————————————

def get_qdrant_client():
from qdrant_client import QdrantClient
host = os.environ.get(“QDRANT_HOST”, “localhost”)
port = int(os.environ.get(“QDRANT_PORT”, “6333”))
return QdrantClient(host=host, port=port, timeout=60)

def ensure_precomputed_collection(client, collection_name: str, dim: int) -> None:
“”“Create the 768d epstein collection if it doesn’t exist.”””
from qdrant_client.models import Distance, VectorParams
existing = [c.name for c in client.get_collections().collections]
if collection_name in existing:
log.info(“collection_exists”, collection=collection_name)
return
log.info(“creating_collection”, collection=collection_name, dim=dim)
client.create_collection(
collection_name=collection_name,
vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
)
log.info(“collection_created”, collection=collection_name)

def get_existing_qdrant_sources(client, collection_name: str, matter_id: str) -> set[str]:
“”“Return set of source_file values already indexed in this collection for this matter.”””
from qdrant_client.models import Filter, FieldCondition, MatchValue
existing = set()
offset = None
while True:
results, next_offset = client.scroll(
collection_name=collection_name,
scroll_filter=Filter(must=[
FieldCondition(key=“matter_id”, match=MatchValue(value=matter_id))
]),
with_payload=[“source_file”],
with_vectors=False,
limit=1000,
offset=offset,
)
for r in results:
src = r.payload.get(“source_file”)
if src:
existing.add(src)
if next_offset is None:
break
offset = next_offset
return existing

def build_point_precomputed(
point_id: int,
embedding: list[float],
chunk_text: str,
source_file: str,
chunk_index: int,
document_id: str,
matter_id: str,
page_number: int | None,
bates_begin: str | None,
bates_end: str | None,
ocr_confidence: float | None,
date: str | None,
doc_type: str | None,
) -> dict:
“”“Build a Qdrant PointStruct dict for the precomputed-embedding path.”””
return {
“id”: point_id,
“vector”: embedding,
“payload”: {
“chunk_text”: chunk_text,
“source_file”: source_file,
“chunk_index”: chunk_index,
“document_id”: document_id,
“matter_id”: matter_id,
“page_number”: page_number,
“bates_begin”: bates_begin,
“bates_end”: bates_end,
“ocr_confidence”: ocr_confidence,
“privilege_status”: DEFAULT_PRIVILEGE,
“file_type”: DEFAULT_FILE_TYPE,
“date”: date,
“doc_type”: doc_type,
# NEXUS fields defaulted for pre-imported docs
“hot_doc_score”: 0.0,
“anomaly_score”: 0.0,
“quality_score”: ocr_confidence or 0.5,
“context_prefix”: None,
}
}

def upsert_batch(client, collection_name: str, points: list[dict]) -> None:
from qdrant_client.models import PointStruct
client.upsert(
collection_name=collection_name,
points=[
PointStruct(id=p[“id”], vector=p[“vector”], payload=p[“payload”])
for p in points
],
wait=True,
)

# —————————————————————————

# Dataset loading

# —————————————————————————

def load_fbi_dataset(limit: int | None):
“”“Load svetfm/epstein-fbi-files. Returns HuggingFace Dataset.”””
from datasets import load_dataset
log.info(“loading_dataset”, name=FBI_DATASET)
ds = load_dataset(FBI_DATASET, split=“train”)
if limit:
ds = ds.select(range(min(limit, len(ds))))
log.info(“dataset_loaded”, rows=len(ds), columns=ds.column_names)
return ds

def load_house_dataset(limit: int | None):
“”“Load svetfm/epstein-files-nov11-25-house-post-ocr-embeddings.”””
from datasets import load_dataset
log.info(“loading_dataset”, name=HOUSE_DATASET)
ds = load_dataset(HOUSE_DATASET, split=“train”)
if limit:
ds = ds.select(range(min(limit, len(ds))))
log.info(“dataset_loaded”, rows=len(ds), columns=ds.column_names)
return ds

def group_by_source_file(dataset, dataset_type: str) -> dict[str, list[dict]]:
“”“Group chunks by source document filename.”””
groups: dict[str, list[dict]] = {}
for item in dataset:
src = item.get(“source_file”) or item.get(“filename”) or “unknown”
if src not in groups:
groups[src] = []
groups[src].append(item)
log.info(“grouped_by_source”, unique_docs=len(groups))
return groups

def extract_bates(item: dict, dataset_type: str) -> tuple[str | None, str | None]:
“”“Extract Bates begin/end from dataset item.”””
if dataset_type == “fbi”:
# FBI dataset has explicit bates fields
begin = item.get(“bates_begin”) or item.get(“bates_number”)
end = item.get(“bates_end”)
return begin, end
# House dataset has no Bates
return None, None

def extract_page_number(item: dict, dataset_type: str) -> int | None:
if dataset_type == “fbi”:
pn = item.get(“page_number”) or item.get(“page”)
if pn is not None:
try:
return int(pn)
except (ValueError, TypeError):
pass
# House dataset: derive from chunk_index as best approximation
# (chunk_index is position in doc, not actual page — clearly labeled in payload)
return None

def extract_ocr_confidence(item: dict, dataset_type: str) -> float | None:
if dataset_type == “fbi”:
conf = item.get(“ocr_confidence”) or item.get(“confidence”)
if conf is not None:
try:
return float(conf)
except (ValueError, TypeError):
pass
return None

# —————————————————————————

# Re-embed path: use NEXUS configured embedding provider

# —————————————————————————

async def get_nexus_embedder():
“”“Load NEXUS embedding provider from app/common/embedder.py.”””
sys.path.insert(0, “/app”)  # Docker container path
from app.common.embedder import get_embedder
from app.config import get_settings
settings = get_settings()
return get_embedder(settings)

async def embed_texts(embedder, texts: list[str]) -> list[list[float]]:
return await embedder.embed_texts(texts)

# —————————————————————————

# Main import logic

# —————————————————————————

async def run_import(args: argparse.Namespace) -> None:
log.info(“starting_import”,
dataset=args.dataset,
matter_id=args.matter_id,
mode=“precomputed” if args.use_precomputed else “re-embed”,
dry_run=args.dry_run)

```
# --- Load HuggingFace dataset ---
if args.dataset == "fbi":
    dataset = load_fbi_dataset(args.limit)
else:
    dataset = load_house_dataset(args.limit)

groups = group_by_source_file(dataset, args.dataset)

if args.dry_run:
    log.info("dry_run_stats",
             total_chunks=len(dataset),
             unique_docs=len(groups),
             sample_columns=list(dataset[0].keys()) if len(dataset) > 0 else [])
    print("\n=== DRY RUN COMPLETE — no writes performed ===")
    return

# --- Database setup ---
engine = await get_db_engine()
matter = await verify_matter_exists(engine, args.matter_id)
log.info("matter_verified", matter_name=matter["name"])

existing_docs = await get_existing_doc_ids(engine, args.matter_id)
log.info("existing_docs_in_matter", count=len(existing_docs))

# --- Qdrant setup ---
qdrant = get_qdrant_client()

if args.use_precomputed:
    collection_name = PRECOMPUTED_COLLECTION
    ensure_precomputed_collection(qdrant, collection_name, PRECOMPUTED_DIM)
else:
    collection_name = NEXUS_COLLECTION
    log.info("using_existing_collection", collection=collection_name)

# Resume: get already-indexed sources
if args.resume:
    indexed_sources = get_existing_qdrant_sources(qdrant, collection_name, args.matter_id)
    log.info("resume_mode", already_indexed=len(indexed_sources))
else:
    indexed_sources = set()

# --- Re-embed setup ---
embedder = None
if args.re_embed:
    log.info("loading_embedder")
    embedder = await get_nexus_embedder()
    log.info("embedder_ready")

# --- Main import loop ---
total_chunks = 0
total_docs = 0
skipped_docs = 0
point_id_counter = 0

# Seed point_id_counter from existing collection size to avoid collisions
try:
    info = qdrant.get_collection(collection_name)
    point_id_counter = info.points_count or 0
    log.info("starting_point_id", point_id=point_id_counter)
except Exception:
    pass

async with engine.begin() as conn:
    for source_file, chunks in groups.items():
        # Resume check
        if source_file in indexed_sources:
            skipped_docs += 1
            continue

        # Already in PostgreSQL?
        if source_file in existing_docs:
            document_id = existing_docs[source_file]
            log.debug("doc_already_in_pg", source_file=source_file)
        else:
            # Extract Bates from first and last chunk for this doc
            first_chunk = chunks[0]
            last_chunk = chunks[-1]
            bates_begin, _ = extract_bates(first_chunk, args.dataset)
            _, bates_end = extract_bates(last_chunk, args.dataset)
            if bates_end is None:
                bates_end = bates_begin

            date_str = first_chunk.get("date") or first_chunk.get("document_date")
            doc_type = first_chunk.get("doc_type") or first_chunk.get("document_type")

            document_id = await insert_document(
                conn=conn,
                matter_id=args.matter_id,
                filename=source_file,
                bates_begin=bates_begin,
                bates_end=bates_end,
                file_type=DEFAULT_FILE_TYPE,
                source_dataset=FBI_DATASET if args.dataset == "fbi" else HOUSE_DATASET,
                chunk_count=len(chunks),
            )
            existing_docs[source_file] = document_id
            total_docs += 1

        # Build Qdrant points for this document
        qdrant_batch: list[dict] = []

        # Re-embed path: batch all texts for this doc
        if args.re_embed:
            texts = [c.get("text", "") for c in chunks]
            try:
                embeddings = await embed_texts(embedder, texts)
            except Exception as e:
                log.error("embed_failed", source_file=source_file, error=str(e))
                continue

        for i, chunk in enumerate(chunks):
            text = chunk.get("text", "").strip()
            if not text:
                continue

            embedding = embeddings[i] if args.re_embed else chunk.get("embedding")
            if embedding is None:
                log.warning("no_embedding", source_file=source_file, chunk_index=i)
                continue

            point = build_point_precomputed(
                point_id=point_id_counter,
                embedding=embedding,
                chunk_text=text,
                source_file=source_file,
                chunk_index=chunk.get("chunk_index", i),
                document_id=document_id,
                matter_id=args.matter_id,
                page_number=extract_page_number(chunk, args.dataset),
                bates_begin=extract_bates(chunk, args.dataset)[0],
                bates_end=extract_bates(chunk, args.dataset)[1],
                ocr_confidence=extract_ocr_confidence(chunk, args.dataset),
                date=chunk.get("date") or chunk.get("document_date"),
                doc_type=chunk.get("doc_type") or chunk.get("document_type"),
            )
            qdrant_batch.append(point)
            point_id_counter += 1
            total_chunks += 1

        # Upsert this document's chunks
        if qdrant_batch:
            for batch_start in range(0, len(qdrant_batch), args.batch_size):
                batch = qdrant_batch[batch_start:batch_start + args.batch_size]
                try:
                    upsert_batch(qdrant, collection_name, batch)
                except Exception as e:
                    log.error("qdrant_upsert_failed",
                              source_file=source_file,
                              batch_start=batch_start,
                              error=str(e))
                    raise

        if total_docs % 100 == 0 and total_docs > 0:
            log.info("progress",
                     docs_imported=total_docs,
                     chunks_imported=total_chunks,
                     skipped=skipped_docs)

log.info("import_complete",
         docs_imported=total_docs,
         chunks_imported=total_chunks,
         skipped_docs=skipped_docs,
         collection=collection_name,
         matter_id=args.matter_id)

if args.use_precomputed:
    print(f"""
```

╔══════════════════════════════════════════════════════════════════════════╗
║  IMPORT COMPLETE — ACTION REQUIRED                                       ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Vectors loaded into: {collection_name:<50} ║
║                                                                          ║
║  Because this is a SEPARATE 768d collection (not nexus_text 1024d),     ║
║  add this one-liner to app/query/retriever.py in HybridRetriever:        ║
║                                                                          ║
║  In _get_collection_name(), check if matter uses epstein collection:     ║
║    if matter uses 768d: return “{PRECOMPUTED_COLLECTION}”                ║
║    else: return “nexus_text”                                             ║
║                                                                          ║
║  OR run with –re-embed next time to unify into nexus_text.              ║
╚══════════════════════════════════════════════════════════════════════════╝
“””)

# —————————————————————————

# Entry point

# —————————————————————————

def main():
args = parse_args()
asyncio.run(run_import(args))

if **name** == “**main**”:
main()
