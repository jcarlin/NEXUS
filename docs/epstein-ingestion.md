# Epstein Files Ingestion Guide

Strategy and runbook for ingesting the House Oversight Committee's Epstein Files release (~25,000 OCR'd documents) into NEXUS using local Ollama embeddings.

## Dataset

- **Source**: [teyler/epstein-files-20k](https://huggingface.co/datasets/teyler/epstein-files-20k) (open access, no auth)
- **Size**: ~60 MB Parquet, 25,800 rows
- **Content**: OCR'd text from 20,000+ pages of depositions, flight logs, correspondence, law enforcement records
- **Format**: Two columns: `filename` (Bates-numbered path) and `text` (OCR'd content)
- **Distribution**: 2,897 TEXT entries + 22,903 IMAGES entries (both contain full OCR text)

### Filename Format

The teyler dataset uses dash-separated filenames with a batch number:

```
TEXT-001-HOUSE_OVERSIGHT_031683.txt
IMAGES-005-HOUSE_OVERSIGHT_020367.txt
```

Format: `{TYPE}-{BATCH}-{BATES_PREFIX}_{BATES_NUMBER}.txt`

The `HuggingFaceCSVAdapter` handles both this format and slash-separated (`TEXT/HOUSE_OVERSIGHT_031683.txt`).

### Data Quality Note

The HuggingFace dataset loads as a single `text` column (each physical CSV line becomes a row). The download script (`scripts/download_epstein_dataset.py`) reconstructs the proper `filename,text` CSV structure and saves as Parquet.

---

## Prerequisites

### Infrastructure (Docker)
```bash
docker compose up -d    # Redis, Postgres, Qdrant, Neo4j, MinIO
docker compose ps       # Verify all 5 healthy
alembic upgrade head    # Ensure migrations current
```

### Ollama (Local Embeddings)
```bash
ollama pull nomic-embed-text    # ~274 MB, one-time download
curl http://localhost:11434/api/tags   # Verify serving
```

### .env Configuration
```ini
EMBEDDING_PROVIDER=ollama
EMBEDDING_DIMENSIONS=768
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
CELERY_CONCURRENCY=2       # 2 workers for MacBook, adjust as needed
```

**Important**: Both the FastAPI app and Celery workers use `EMBEDDING_PROVIDER` to select the embedding backend. Ollama runs locally with no API costs.

---

## Step-by-Step Ingestion

### 1. Download Dataset (~2 min)

```bash
python scripts/download_epstein_dataset.py --output-dir ./data/epstein
```

Output: `./data/epstein/epstein_files_20k.parquet` (25,800 docs, ~57 MB)

### 2. Verify Qdrant Collection

```bash
curl -s http://localhost:6333/collections/nexus_text | python3 -m json.tool
```

- If the collection exists with **768d vectors** — good, proceed
- If it exists with different dimensions (e.g., 1024d from OpenAI) — delete and restart the API:
  ```bash
  curl -X DELETE http://localhost:6333/collections/nexus_text
  # Restart API to recreate at 768d
  ```
- If it doesn't exist — start the API, it creates the collection during startup

### 3. Start FastAPI

```bash
uvicorn app.main:app --port 8000
```

### 4. Seed Matter + Parties + Claims

```bash
python scripts/seed_epstein_matter.py
```

Creates:
- Matter: `00000000-0000-0000-0000-000000000002` ("Epstein Files Investigation")
- 8 parties (Jeffrey Epstein, Ghislaine Maxwell, etc.)
- 3 claims (sex trafficking, obstruction, conspiracy)
- 6 defined terms (NPA, Bates number, etc.)
- Dataset record: "House Oversight Nov 2025"

Idempotent — safe to run multiple times.

### 5. Dry Run

```bash
python scripts/import_dataset.py huggingface_csv \
    --file ./data/epstein/epstein_files_20k.parquet \
    --matter-id 00000000-0000-0000-0000-000000000002 \
    --dry-run
```

Expected: ~25,320 documents, ~114k chunks, $0 embedding cost with Ollama.

### 6. Start Celery Worker (Background)

Use `tmux` or `screen` so the worker persists after closing the terminal:

```bash
tmux new -s celery
source .venv/bin/activate
celery -A workers.celery_app worker --loglevel=info --concurrency=2
# Detach: Ctrl+B, D
```

Optional — start Flower for web monitoring:
```bash
tmux new -s flower
source .venv/bin/activate
celery -A workers.celery_app flower --port=5555
# Monitor at http://localhost:5555
```

### 7. Run Full Import

```bash
python scripts/import_dataset.py huggingface_csv \
    --file ./data/epstein/epstein_files_20k.parquet \
    --matter-id 00000000-0000-0000-0000-000000000002 \
    --disable-hnsw
```

- `--disable-hnsw`: Faster bulk inserts (index rebuilds after import)
- `--resume`: Skip already-imported docs (use if restarting after partial import)

The script dispatches all 25k tasks to Celery in ~10 seconds, then exits. **Celery processes them independently** — you can close the import terminal.

### 8. Monitor Progress

```bash
# Celery logs
tmux attach -t celery

# Flower web UI
open http://localhost:5555

# Database counts
python3 -c "
from app.config import Settings
from sqlalchemy import create_engine, text
s = Settings()
engine = create_engine(s.postgres_url_sync)
with engine.connect() as conn:
    docs = conn.execute(text(\"SELECT COUNT(*) FROM documents WHERE matter_id = '00000000-0000-0000-0000-000000000002'\")).scalar()
    jobs = dict(conn.execute(text(\"SELECT status, COUNT(*) FROM jobs WHERE matter_id = '00000000-0000-0000-0000-000000000002' GROUP BY status\")).fetchall())
    print(f'Documents: {docs}')
    print(f'Jobs: {jobs}')
"

# Qdrant points
curl -s http://localhost:6333/collections/nexus_text | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['points_count'])"
```

---

## Performance Estimates (MacBook, concurrency=2)

| Stage | Per-doc Time | Notes |
|-------|-------------|-------|
| Upload to MinIO | ~1s | Write raw text to object storage |
| Chunking | ~0.1s | Semantic chunking via token boundaries |
| Embedding (Ollama) | ~25-30s | nomic-embed-text, CPU inference |
| NER (GLiNER) | ~20-30s | First doc slower (model load), ~0.05s/chunk after |
| Qdrant indexing | ~0.5s | Point upsert |
| Neo4j indexing | ~1s | Document + Entity + Chunk nodes |
| **Total per doc** | **~30-60s** | **Dominated by embedding on CPU** |

**Full import estimate**: ~25,000 docs / 2 workers = ~12,500 docs per worker at ~45s each ≈ **6-7 hours**

### Optimization Options

- **Increase concurrency**: `CELERY_CONCURRENCY=4` (if CPU allows)
- **GPU acceleration**: Run Ollama on a GPU machine (10-50x faster embeddings)
- **Skip NER**: Set `ENABLE_ENTITY_EXTRACTION=false` to skip GLiNER (saves ~20s/doc)
- **TEI embeddings**: Use a Text Embedding Inference server for batched embedding

---

## Pipeline Architecture

```
download_epstein_dataset.py
  → teyler/epstein-files-20k (HuggingFace)
  → data/epstein/epstein_files_20k.parquet

seed_epstein_matter.py
  → Postgres: case_matters, case_parties, case_claims, case_defined_terms, datasets

import_dataset.py huggingface_csv
  → HuggingFaceCSVAdapter reads Parquet
  → Dispatches import_text_document Celery tasks (one per doc)
  → Dispatches post-ingestion hooks (entity resolution, email threading, etc.)

Celery worker (import_text_document task):
  1. Upload → MinIO (raw text preserved)
  2. Chunk  → Semantic chunks (512 tokens max)
  3. Embed  → Ollama nomic-embed-text (768d vectors)
  4. NER    → GLiNER entity extraction (people, orgs, dates, locations)
  5. Index  → Qdrant (vector search) + Neo4j (knowledge graph) + Postgres (metadata)
  6. Complete → Job status updated
```

---

## Troubleshooting

### Wrong embedding provider
The Celery worker must load the correct `EMBEDDING_PROVIDER` from `.env`. If you see `provider=openai` in Celery logs, ensure:
- `.env` has `EMBEDDING_PROVIDER=ollama`
- The Celery worker was restarted after changing `.env`

### Qdrant dimension mismatch
If you see `Wrong input: Vector inserting dim X, expected Y`:
```bash
curl -X DELETE http://localhost:6333/collections/nexus_text
# Restart FastAPI to recreate at correct dimensions
```

### Jobs stuck in "pending"
Check if Celery worker is running:
```bash
celery -A workers.celery_app inspect active
```

### Resume after interruption
```bash
python scripts/import_dataset.py huggingface_csv \
    --file ./data/epstein/epstein_files_20k.parquet \
    --matter-id 00000000-0000-0000-0000-000000000002 \
    --resume
```
Skips documents already present in Postgres (by content hash).

---

## Bugs Found and Fixed During Smoke Testing

These issues were discovered and fixed during the initial ingestion run. Documented here for context.

### 1. HuggingFace dataset format mismatch
**Problem**: `teyler/epstein-files-20k` loads via `datasets.load_dataset()` as 2.1M single-column rows — each physical CSV line becomes a row, not each document.
**Fix**: `download_epstein_dataset.py` now detects this and reconstructs the proper `filename,text` CSV structure by joining all rows and re-parsing with Python's `csv.DictReader`.

### 2. Dash-separated filenames not recognized
**Problem**: Adapter expected `TEXT/HOUSE_OVERSIGHT_020367.txt` but dataset uses `TEXT-001-HOUSE_OVERSIGHT_020367.txt`.
**Fix**: Updated `_BATES_RE` regex, IMAGES prefix check, and leaf name extraction in `huggingface_csv.py` to handle both formats.

### 3. Celery worker using OpenAI instead of Ollama
**Problem**: `_embed_chunks()` in `tasks.py` only checked for `local` and `tei` providers — everything else fell through to a hardcoded OpenAI fallback. The FastAPI DI layer (`dependencies.py`) had the complete provider list but Celery didn't use it.
**Fix**: Added `ollama` and `gemini` branches to `_embed_chunks()` matching the DI factory.

### 4. `text` parameter shadowing `sqlalchemy.text`
**Problem**: The `import_text_document()` task parameter `text: str` shadowed the module-level `from sqlalchemy import text`. Three SQL calls inside the function failed with `TypeError: 'str' object is not callable`.
**Fix**: Import `text as sa_text` at function scope and use `sa_text()` for all SQL calls within the function.

### 5. `::json` cast syntax in seed script
**Problem**: `:timeline::json` in SQL was parsed by SQLAlchemy as named parameter `:timeline` + invalid syntax.
**Fix**: Changed to `CAST(:timeline AS json)`.

### 6. `anchor_document_id` NOT NULL constraint
**Problem**: `case_contexts.anchor_document_id` is NOT NULL, but the seed script didn't provide it (seeding happens before documents exist).
**Fix**: Added `'seed'` as placeholder value.

---

## Key Files

| File | Purpose |
|------|---------|
| `scripts/download_epstein_dataset.py` | Download from HuggingFace, save as Parquet |
| `scripts/seed_epstein_matter.py` | Seed matter, parties, claims, terms |
| `scripts/import_dataset.py` | CLI for bulk import (adapter dispatch) |
| `app/ingestion/adapters/huggingface_csv.py` | Adapter: Parquet → ImportDocument |
| `app/ingestion/tasks.py` | Celery task: import_text_document |
| `app/ingestion/bulk_import.py` | Bulk import orchestration |
| `data/epstein/epstein_files_20k.parquet` | Downloaded dataset (not committed) |
