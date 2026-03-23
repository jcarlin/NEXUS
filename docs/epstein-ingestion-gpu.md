# Epstein Corpus Ingestion Plan — GPU VM (BGE-M3 1024d)

**GPU VM**: `nexus-gpu` (n1-standard-8 + T4, us-west1-a, spot ~$186/mo)
**Embedding**: Infinity BGE-M3 (1024d) — pre-computed 768d vectors must be re-embedded
**Broker**: RabbitMQ | **Workers**: 3 (scalable to 4) | **Matter ID**: `00000000-0000-0000-0000-000000000002`

---

## Datasource Inventory

### Tier 1: Celery Bulk Import (no code changes needed)

| # | Source | Size | Docs | Pipeline | Est. Time |
|---|---|---|---|---|---|
| 1 | `to-be/epstein-emails` (HF) | ~50 MB | 3,480 emails | bulk import | ~30 min |
| 2 | `notesbymuneeb/epstein-emails` (HF) | ~100 MB | 13,008 msgs | bulk import | ~2 hrs |
| 3 | `KillerShoaib/Jeffrey-Epstein-Emails` (HF) | ~8 MB | 14,835 msgs | bulk import (adapter needed) | ~3 hrs |
| 4 | `tensonaut/EPSTEIN_FILES_20K` (HF) | 106 MB | 25K docs | bulk import | ~4 hrs |

### Tier 2: Pre-Embedded (needs `--re-embed` implementation)

| # | Source | Size | Chunks | Pipeline | Est. Time |
|---|---|---|---|---|---|
| 5 | `svetfm/epstein-fbi-files` (HF) | 3.31 GB | 236K chunks | custom script + re-embed | ~3 hrs |
| 6 | `svetfm/epstein-files-nov11-25-house` (HF) | 357 MB | 69K chunks | custom script + re-embed | ~1 hr |

### Tier 3: PDF Pipeline (Docling parse + OCR)

| # | Source | Size | Pages | Pipeline | Est. Time |
|---|---|---|---|---|---|
| 7 | Giuffre v. Maxwell (CourtListener RECAP) | ~200 MB | ~3K pages | PDF download + Celery | ~2 hrs |
| 8 | US v. Maxwell (CourtListener RECAP) | ~100 MB | ~2K pages | PDF download + Celery | ~1 hr |
| 9 | FBI FOIA Vault (vault.fbi.gov, 22 parts) | ~100 MB | ~3K pages | PDF + OCR + Celery | ~4 hrs |
| 10 | FL Palm Beach State Attorney (16 parts) | ~200 MB | ~5K pages | PDF + OCR + Celery | ~6 hrs |
| 11 | DocumentCloud collections (2019/2024 unsealing) | ~300 MB | ~5K pages | API download + Celery | ~4 hrs |

### Tier 4: Reference Data (structured import)

| # | Source | Size | Items | Notes |
|---|---|---|---|---|
| 12 | `theelderemo/FULL_EPSTEIN_INDEX` (HF) | 3.3 MB | Index CSV | Cross-reference metadata |
| 13 | `rhowardstone/Epstein-research-data` (GitHub) | ~5 MB | 606 entities, 2302 connections | Direct Neo4j import |
| 14 | Additional HF datasets (`Nikity/Epstein-Files`, `theelderemo/epstein-files-nov-2025`, `DavidBrowne17/epstein-files-20k`) | Varies | Overlaps with above | Dedup via content hash |

### GATE: Massive Datasets (deferred)

| # | Source | Size | Pages | Est. Time |
|---|---|---|---|---|
| 15 | DOJ EFTA DS 1-7 + 12 | ~4.3 GB | ~50K pages | Days |
| 16 | DOJ EFTA DS 8 | ~10.7 GB | ~100K pages | Days |
| 17 | DOJ EFTA DS 9 (emails/DOJ correspondence) | ~180 GB | ~500K pages | Weeks |
| 18 | DOJ EFTA DS 10 (images + videos) | ~82 GB | 180K images + 2K videos | Weeks |
| 19 | DOJ EFTA DS 11 (financial/flight logs) | ~27.5 GB | Flight manifests, ledgers | Days |

**Tier 1-3 total: ~40K docs, ~350K chunks, ~8 hours on GPU VM**
**Tier 4 (gated): ~3.5M pages, ~400 GB, weeks of processing**

DOJ EFTA torrents: `magnet:?xt=urn:btih:f5cbe5026b1f86617c520d0a9cd610d6254cbe85` (~221 GB). Also on Internet Archive. DOJ removed bulk ZIP downloads Feb 2026 — individual PDF only now.

---

## Key Difference from CPU VM Plan

The original plan (`docs/epstein-ingestion-plan.md`) used Ollama nomic-embed-text (768d). Pre-computed 768d vectors from HuggingFace loaded directly into Qdrant at $0 cost.

The GPU VM uses Infinity BGE-M3 (1024d). **Pre-computed 768d vectors are incompatible** with the 1024d Qdrant collection. Options:
- **Tier 1 datasets**: Use full Celery pipeline (embed from scratch via Infinity GPU). Works now.
- **Tier 2 datasets**: Need `--re-embed` flag implemented in `import_fbi_dataset.py` (ignores pre-computed vectors, embeds chunk text via Infinity instead).

The GPU compensates: Infinity GPU embeds at ~60-2700 chunks/sec (vs ~50/sec on CPU Ollama). Re-embedding 305K chunks takes ~2-4 hours, not days.

---

## Execution Plan

### Step 0: Seed Epstein Matter

```bash
COMPOSE='sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.gpu.yml'
$COMPOSE exec api python scripts/seed_epstein_matter.py
```

Creates: matter, 8 parties, 3 claims, 17 legal terms, 11 timeline events, 6 dataset records.

### Step 1: Import to-be Emails (smallest, kick off first)

```bash
$COMPOSE exec api python scripts/download_hf_dataset.py \
  --dataset to-be/epstein-emails --output /tmp/emails_tobe

$COMPOSE exec api python scripts/import_dataset.py epstein_emails \
  --file /tmp/emails_tobe/*.parquet \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --disable-hnsw
```

Full pipeline per email: chunk -> embed (Infinity GPU) -> GLiNER NER -> Qdrant + Neo4j (entity nodes + CO_OCCURS edges) -> email threading.

### Step 2: Import muneeb Emails

```bash
$COMPOSE exec api python scripts/download_hf_dataset.py \
  --dataset notesbymuneeb/epstein-emails --output /tmp/emails_muneeb

$COMPOSE exec api python scripts/import_dataset.py epstein_emails \
  --file /tmp/emails_muneeb/*.parquet \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --resume --disable-hnsw
```

### Step 3: Import tensonaut 20K (House Oversight raw text)

```bash
$COMPOSE exec api python scripts/download_hf_dataset.py \
  --dataset tensonaut/EPSTEIN_FILES_20K --output /tmp/epstein_20k

$COMPOSE exec api python scripts/import_dataset.py huggingface_csv \
  --file /tmp/epstein_20k/*.parquet \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --disable-hnsw
```

### Step 4: Implement `--re-embed` (code change, ~20 lines)

In `scripts/import_fbi_dataset.py`, when `--re-embed` is set: skip pre-computed vectors, embed chunk text via the configured embedding provider (Infinity BGE-M3) at 1024d.

### Step 5: Import FBI Files (236K chunks, after `--re-embed`)

```bash
$COMPOSE exec api python scripts/download_hf_dataset.py \
  --dataset svetfm/epstein-fbi-files \
  --data-files "embeddings/all_embeddings.jsonl" --output /tmp/fbi_data

$COMPOSE exec api python scripts/import_fbi_dataset.py \
  --file /tmp/fbi_data/*.parquet \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --dataset-name "FBI Files" \
  --re-embed --disable-hnsw --skip-ner --concurrency 4
```

### Step 6: Import House Oversight Pre-embedded (69K chunks)

```bash
$COMPOSE exec api python scripts/download_hf_dataset.py \
  --dataset svetfm/epstein-files-nov11-25-house-post-ocr-embeddings --output /tmp/house

$COMPOSE exec api python scripts/import_fbi_dataset.py \
  --file /tmp/house/*.parquet \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --dataset-name "House Oversight Pre-embedded" \
  --citation-quality degraded \
  --re-embed --disable-hnsw --skip-ner --concurrency 4
```

### Step 7: Court Documents (Giuffre v. Maxwell, native PDFs)

```bash
$COMPOSE exec api python scripts/download_courtlistener.py \
  --docket-id 4355835 --output-dir /tmp/maxwell_docs

$COMPOSE exec api python scripts/import_pdf_directory.py \
  --dir /tmp/maxwell_docs \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --dataset-name "Giuffre v. Maxwell Court Docs" \
  --disable-hnsw
```

### Step 8: Run Case Setup Agent

```bash
TOKEN=$(curl -sf http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"password123"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

curl -X POST http://localhost:8000/api/v1/cases/setup \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Matter-ID: 00000000-0000-0000-0000-000000000002" \
  -H "Content-Type: application/json" \
  -d '{"matter_id": "00000000-0000-0000-0000-000000000002"}'
```

---

## Shared Infrastructure

- **Single matter**: All datasources share matter `...-0002` with per-dataset filtering via `dataset_id`
- **Embedding**: Infinity BGE-M3 1024d (GPU) — all sources embedded uniformly
- **Entity dedup**: Entity Resolution Agent runs post-ingestion to merge duplicates
- **CO_OCCURS edges**: Created during ingestion for entity network graph
- **Citation quality**: `full` (FBI, court docs), `degraded` (House Oversight pre-embedded), `email` (emails)

## Verification (after each datasource)

1. `SELECT count(*) FROM documents WHERE matter_id = '...-0002'`
2. `MATCH (n) RETURN labels(n)[0] AS label, count(n) ORDER BY count(n) DESC`
3. `MATCH ()-[r:CO_OCCURS]-() RETURN count(r)` — entity co-occurrence edges
4. Query: "Who did Epstein communicate with about flights?"
5. Frontend: entity network graph shows connections, email threading works
