# NEXUS M6: Bulk Import — Pre-OCR'd Epstein Document Datasets

## Context

M0-M5 complete (159 tests). The ingestion pipeline handles file upload → parse → chunk → embed → extract → index via Celery tasks. For the 25K+ pre-OCR'd Epstein documents available as public datasets, we can skip parsing entirely and feed clean text directly into chunking → embedding → extraction → indexing — saving massive compute and cost.

**Best available sources (researched):**
1. **tensonaut/EPSTEIN_FILES_20K** (HuggingFace) — 25K+ OCR'd text files, clean CSV format, no embeddings/entities
2. **epstein-docs.github.io** (Epstein Archive) — 8,175 docs with LLM-OCR + metadata + pre-extracted entities, JSON format, torrent available
3. **ErikVeland/epstein-archive** — 86K+ entities with relationships, MongoDB export — useful for Neo4j KG seeding only
4. **epsteinbench.com** — RAG benchmark with ground-truth Q&A pairs — useful for evaluation only (defer to M7)

**Pre-computed embeddings from other sources are NOT useful** — they use different models (nomic 768d, MiniLM 384d) vs our OpenAI 1024d. Re-embedding is cheap (~$6 for 25K docs).

**Other resources evaluated but not recommended:**
- `justinlime/epstein_rag_mcp` — Qdrant + MiniLM 384d, good architectural reference but data not importable
- `nozomio-labs/nia-epstein-ai` — Proprietary Nia API, no data export
- `svetfm/epstein-files-nov11-25-house-post-ocr-embeddings` — HF dataset with nomic 768d embeddings, wrong model for us
- `Pinperepette/parrhesepstein` — Flask + ChromaDB, different architecture
- `maxandrews/Epstein-doc-explorer` — D3.js knowledge graph viz, useful UX reference only

---

## Files to Create (7)

| File | Purpose |
|------|---------|
| `migrations/versions/002_content_hash_index.py` | Alembic index on `documents.content_hash` for dedup |
| `app/ingestion/bulk_import.py` | `ImportDocument` dataclass + shared helpers |
| `app/ingestion/adapters/__init__.py` | Package init |
| `app/ingestion/adapters/huggingface.py` | tensonaut/EPSTEIN_FILES_20K adapter (generator) |
| `app/ingestion/adapters/epstein_docs.py` | epstein-docs.github.io JSON adapter (generator) |
| `scripts/import_dataset.py` | CLI orchestrator: download, dedup, dispatch |
| `tests/test_ingestion/test_bulk_import.py` | Tests for task + adapters (~10) |

## Files to Modify (2)

| File | Changes |
|------|---------|
| `app/ingestion/tasks.py` | Add `import_text_document` Celery task (skip parsing, reuse chunk→embed→extract→index) |
| `pyproject.toml` | Add `datasets>=2.0` to optional `[bulk-import]` dep group |

---

## Phase A: Data Model + Migration

**`migrations/versions/002_content_hash_index.py`** — Index for fast dedup lookups:
```python
def upgrade():
    op.create_index("idx_documents_content_hash", "documents", ["content_hash"])
```
The `content_hash` column already exists (`hashlib.sha256(file_bytes).hexdigest()[:16]` in tasks.py:550). For text imports, we hash the text content with the same truncated SHA256.

**`app/ingestion/bulk_import.py`** — Common internal representation:
```python
@dataclass
class ImportDocument:
    source_id: str          # Unique ID from source dataset
    filename: str           # Original or derived filename
    text: str               # Full OCR'd text content
    content_hash: str       # SHA256[:16] of text
    source: str             # "tensonaut_hf" | "epstein_docs"
    metadata: dict          # Source-specific metadata
    entities: list[dict]    # Pre-extracted entities ([] if none)
    page_count: int         # Known or estimated page count
    doc_type: str           # NEXUS document type
```

## Phase B: Celery Task — `import_text_document`

**`app/ingestion/tasks.py`** — New task reusing all existing helpers:

```python
@shared_task(bind=True, name="ingestion.import_text_document", max_retries=3,
             default_retry_delay=30, acks_late=True, reject_on_worker_lost=True)
def import_text_document(self, job_id, text, filename, content_hash,
                         doc_type="document", page_count=1,
                         metadata=None, pre_entities=None):
```

**Stages (skips parsing):**

1. **Upload** — `_upload_to_minio(settings, f"raw/{job_id}/{filename}", text.encode(), "text/plain")` — stores text in MinIO so `/documents/{id}/download` works
2. **Chunk** — `TextChunker.chunk(text, metadata={"source_file": filename}, document_type=doc_type)` — reuse existing chunker
3. **Embed** — `asyncio.run(_embed_chunks(settings, chunk_texts))` — reuse existing async helper
4. **Extract** — If `pre_entities` provided, use directly. Otherwise run GLiNER NER (same dedup logic as `process_document` lines 667-684)
5. **Index** — Qdrant upsert + `_index_to_neo4j()` — reuse existing helpers
6. **Complete** — `_create_document_record()` + `_update_stage(engine, job_id, "complete", "complete")`

**Key differences from `process_document`:**
- No file download from MinIO (text is passed as task argument)
- No parsing stage
- Optional entity skip when `pre_entities` is provided
- Stores `import_source` in metadata_ via follow-up UPDATE
- Skips per-document `resolve_entities.delay()` — CLI triggers once at end

**Text size concern:** Celery serializes task args as JSON. Avg document is ~10KB text, max ~100KB. Well within Celery's 4MB message limit. For outliers, the CLI could upload to MinIO and pass a path instead (out of scope for initial implementation).

## Phase C: Source Adapters

**`app/ingestion/adapters/huggingface.py`** — Generator yielding `ImportDocument`:
```python
def iter_tensonaut_dataset(data_dir: Path, *, limit: int | None = None) -> Iterator[ImportDocument]:
    """Yield from local TEXT/*.txt files or HuggingFace datasets download."""
```
- Reads text files one at a time (never loads full dataset)
- Computes `content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]`
- Sets `doc_type = "document"`, `entities = []`
- Also supports `datasets.load_dataset("tensonaut/EPSTEIN_FILES_20K")` streaming mode

**`app/ingestion/adapters/epstein_docs.py`** — Generator yielding `ImportDocument`:
```python
def iter_epstein_docs(results_dir: Path, *, limit: int | None = None) -> Iterator[ImportDocument]:
    """Yield from epstein-docs.github.io results/ JSON files."""
```
- Globs `results_dir/**/*.json`, processes one file at a time
- Extracts `full_text` field as document text
- Maps `document_metadata.document_type` → NEXUS doc_type
- Maps pre-extracted entities to `[{"name": str, "type": str, "page_number": int}]`
- Preserves all source metadata (date, has_handwriting, etc.)

## Phase D: CLI Orchestrator

**`scripts/import_dataset.py`** — Main entry point:
```
Usage:
    python scripts/import_dataset.py tensonaut --data-dir /path/to/TEXT/
    python scripts/import_dataset.py epstein-docs --data-dir /path/to/results/
    python scripts/import_dataset.py tensonaut --data-dir /path/ --dry-run
    python scripts/import_dataset.py tensonaut --data-dir /path/ --resume --limit 1000

Options:
    --limit N          Import first N documents only
    --batch-size N     Tasks per dispatch batch (default: 100)
    --delay SECONDS    Pause between batches (default: 2.0)
    --dry-run          Count documents and estimate cost only
    --resume           Skip docs whose content_hash exists in DB
```

**Flow:**
1. Select adapter based on subcommand
2. Optionally create a parent job for tracking
3. Iterate adapter generator:
   - Skip empty text
   - If `--resume`: query `SELECT id FROM documents WHERE content_hash = :hash LIMIT 1`
   - Create job record in PostgreSQL
   - `import_text_document.delay(job_id, text, filename, ...)`
   - Batch + delay for rate limiting
4. Print progress stats
5. Dispatch single `resolve_entities.delay()` at end

**Dry-run output:** document count, estimated chunks, estimated embedding cost ($0.13/1M tokens), estimated time.

## Phase E: Dependencies + Tests

**`pyproject.toml`** — Add optional dep group:
```toml
[project.optional-dependencies]
bulk-import = ["datasets>=2.0"]
```

**`tests/test_ingestion/test_bulk_import.py`** (~10 tests):
- `test_import_task_chunks_and_embeds` — mock chunker + embedder, verify Qdrant upsert
- `test_import_task_skips_gliner_with_pre_entities` — pre_entities provided, GLiNER not called
- `test_import_task_uses_gliner_without_pre_entities` — no pre_entities, GLiNER called
- `test_import_task_creates_document_record` — verify documents table INSERT
- `test_import_task_uploads_to_minio` — verify text stored in MinIO
- `test_tensonaut_adapter_yields_documents` — mock text files, verify ImportDocument fields
- `test_epstein_docs_adapter_maps_metadata` — mock JSON, verify metadata mapping
- `test_epstein_docs_adapter_maps_entities` — verify entity format conversion
- `test_content_hash_deterministic` — same text → same hash
- `test_dedup_skips_existing_hash` — mock DB with existing hash, verify skip

---

## Cost & Time Estimates

| Metric | tensonaut (25K docs) | epstein-docs (8K docs) |
|--------|---------------------|----------------------|
| Avg text size | ~10KB | ~15KB |
| Chunks per doc | ~4.5 | ~6 |
| Total chunks | ~112K | ~49K |
| Embedding cost | ~$6 | ~$3 |
| Import time (concurrency=1) | ~4-5 hours | ~2 hours |
| Import time (concurrency=2) | ~2.5 hours | ~1 hour |

---

## Verification

```bash
# 1. Run migration
alembic upgrade head

# 2. Install optional deps (if using HF datasets library)
pip install -e ".[bulk-import]"

# 3. Dry run
python scripts/import_dataset.py tensonaut --data-dir /path/to/TEXT/ --dry-run

# 4. Import first 100 docs as smoke test
python scripts/import_dataset.py tensonaut --data-dir /path/to/TEXT/ --limit 100

# 5. Monitor progress
curl http://localhost:8000/api/v1/jobs | python -m json.tool

# 6. Resume full import
python scripts/import_dataset.py tensonaut --data-dir /path/to/TEXT/ --resume

# 7. Run tests
pytest tests/test_ingestion/test_bulk_import.py -v

# 8. Verify data in Qdrant
python -c "from qdrant_client import QdrantClient; c=QdrantClient('localhost:6333'); print(c.count('nexus_text'))"

# 9. Verify entities in Neo4j
# MATCH (e:Entity) RETURN count(e) as total
```

---

## Not In Scope

- ErikVeland entity import (Neo4j seeding) — separate follow-up task
- epsteinbench.com evaluation — defer to M7
- Re-embedding with different models — not needed, OpenAI 1024d is our standard
- Visual embeddings (ColQwen2.5) — deferred, feature-flagged
- Cross-encoder reranker — deferred to M5b
