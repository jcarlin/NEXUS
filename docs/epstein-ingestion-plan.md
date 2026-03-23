# Epstein Files Ingestion Roadmap

## Context

NEXUS is a multimodal RAG investigation platform. The GCP environment currently has only test seed data (14 docs, 143 entities) from development -- this will be wiped. We're now transitioning to real data: the Epstein document corpus spanning FBI files, House Oversight releases, email collections, court documents, and DOJ EFTA releases.

This roadmap covers **all available datasources** in priority order, from quick wins (pre-processed HuggingFace datasets with pre-computed embeddings) to the long tail (3.5M-page DOJ corpus requiring bulk OCR).

**GCP embedding setup**: Ollama with nomic-embed-text (768d). Switched from OpenAI text-embedding-3-large (1024d) on 2026-03-20. Several HuggingFace datasets include pre-computed 768d nomic vectors -- these load directly at $0 cost. Dockerfile pins `torch==2.6.0+cpu` + `torchvision==0.21.0+cpu` for GLiNER compatibility.

**Full pipeline always**: Every datasource goes through: embedding (pre-computed or Ollama) -> Qdrant vector indexing -> PostgreSQL document records -> MinIO raw storage -> Neo4j document/chunk nodes. NER entity extraction can be deferred to a separate pass for faster initial import (see NER Strategy below). The only shortcut is using pre-computed vectors where available (skips the Ollama embedding call). Citations work immediately after import (sourced from Qdrant chunk payloads, not from NER).

---

## Datasource Inventory

| # | Source | Size | Chunks/Docs | Pre-embedded? | Page Numbers? | Citation Grade | Effort |
|---|--------|------|-------------|---------------|---------------|----------------|--------|
| 1 | `svetfm/epstein-fbi-files` | 3.31 GB | 236K chunks / 8,150 docs | 768d nomic | Yes | Full | Low |
| 2 | `svetfm/epstein-files-nov11-25-house-post-ocr-embeddings` | 357 MB | 69K chunks | 768d nomic | No | Degraded | Low |
| 3 | `tensonaut/EPSTEIN_FILES_20K` | 106 MB | 25K docs | No | No | Degraded | Medium |
| 4 | `to-be/epstein-emails` | ~50 MB | 3,997 emails | No | N/A (email) | Email-grade | Medium |
| 5 | `notesbymuneeb/epstein-emails` | ~100 MB | 5,082 threads / 16,447 msgs | No | N/A (email) | Email-grade | Medium |
| 6 | SDNY Giuffre v. Maxwell (CourtListener) | ~200 MB | ~2-3K pages | No | Yes (PDF) | Full | Medium |
| 7 | FBI FOIA Vault (`vault.fbi.gov`) | ~50-100 MB | ~2-3K pages | No | Yes (PDF) | Full (after OCR) | High |
| 8 | DOJ EFTA Datasets 1-12 (torrents) | ~305-400 GB | ~3.5M pages | No | Varies | Full (after OCR) | Very High |

---

## Phase 0: Foundation (wipe + infrastructure) -- COMPLETE

**Goal**: Clean slate on GCP. Standardize embedding setup. Build reusable import tooling.

**Status**: All items complete. Local pipeline validated end-to-end on 2026-03-19.

### 0.1 Wipe GCP demo data
- [x] Follow `memory/wipe-reingest.md` procedure
- [x] Delete all Qdrant collections, truncate PostgreSQL tables, clear Neo4j, clear MinIO *(done 2026-03-20)*
- [x] Recreate `nexus_text` collection at 768d (Ollama nomic-embed-text) *(done 2026-03-20)*

### 0.2 Verify GCP embedding config -- COMPLETE (2026-03-20)
- [x] Confirm `.env` on GCP has `EMBEDDING_PROVIDER=ollama`, `EMBEDDING_DIMENSIONS=768`, `OLLAMA_EMBEDDING_MODEL=nomic-embed-text`
- [x] Confirm Ollama container is healthy and has nomic-embed-text model pulled
- [x] Confirm Qdrant collection is 768d after recreation

### 0.3 Create shared tooling -- COMPLETE
All scripts built, tested, and validated locally:

**`scripts/download_hf_dataset.py`** -- COMPLETE
- [x] Downloads from HuggingFace with `--sample N` for local testing
- [x] Prints schema inspection (columns, types, sample values, null counts)
- [x] Generic enough to download any HF dataset with `--dataset` flag
- [x] Added `--data-files` flag for JSONL-based datasets (FBI uses `embeddings/all_embeddings.jsonl`)

**`scripts/seed_epstein_matter.py`** -- COMPLETE
- [x] Updated as the single matter for all Epstein sources
- [x] Matter ID: `00000000-0000-0000-0000-000000000002`
- [x] Added FBI-specific defined terms (FOIA, FD-302, SAC, ASAC, CI, Palm Beach PD, PBSO, MC2, EFTA, etc.)
- [x] All datasets (FBI, House Oversight, emails, court docs) seeded as dataset records
- [x] Idempotent -- can be re-run as new datasources are added
- [x] Fixed: `::json` cast syntax incompatible with SQLAlchemy (now uses `CAST(... AS json)`)
- [x] Fixed: missing `anchor_document_id` column (NOT NULL constraint)

**`scripts/import_fbi_dataset.py`** -- COMPLETE
- [x] Custom import for pre-chunked + pre-embedded HuggingFace datasets
- [x] Full pipeline: Parquet reading -> document grouping -> PostgreSQL records -> Qdrant upsert (pre-computed vectors) -> GLiNER NER (optional) -> Neo4j graph -> dataset linking -> post-ingestion hooks
- [x] CLI: `--file`, `--matter-id`, `--limit`, `--dry-run`, `--resume`, `--disable-hnsw`, `--skip-ner`, `--skip-neo4j`, `--skip-minio`, `--re-embed`, `--citation-quality`, `--import-source`, `--concurrency`
- [x] `--concurrency N`: ThreadPoolExecutor for parallel I/O-bound import (best with `--skip-ner`)
- [x] `total_pages` column support: uses authoritative value from dataset when available
- [x] Schema detection handles FBI JSONL columns (`chunk_text` -> text, `source_path` -> source_file, `source_volume` -> volume, `bates_range` -> bates_number)
- [x] Fixed: `dataset_documents` junction table uses `(dataset_id, document_id, assigned_at)` not `(id, ...)`
- [x] Named vector detection auto-adapts to collection config

**`scripts/run_ner_pass.py`** -- COMPLETE
- [x] Deferred NER for documents imported with `--skip-ner`
- [x] Finds docs with `entity_count=0`, fetches chunks from Qdrant, runs GLiNER, indexes to Neo4j
- [x] CLI: `--matter-id`, `--concurrency`, `--limit`, `--dry-run`, `--resume`
- [x] Uses `ProcessPoolExecutor` for true CPU parallelism (bypasses GIL)
- [x] Each worker loads its own GLiNER model (~600MB)

### 0.4 Local Pipeline Validation -- COMPLETE (2026-03-19)
- [x] Synthetic FBI dataset (15 docs, 69 chunks, 768d vectors) created matching real JSONL schema
- [x] Dry-run: schema detection correctly maps all FBI JSONL columns
- [x] Live import (10 docs): PostgreSQL, Qdrant, Neo4j all populated
- [x] NER import (10 docs): GLiNER extracted 120 entities, indexed in Neo4j
- [x] Post-ingestion hooks dispatched (entity resolution, email detection, hot doc scan)
- [x] 28 unit tests pass (including 5 new alias tests)
- [x] 261 ingestion tests pass (full suite, no regressions)

**Bugs found & fixed during validation:**
1. `detect_schema()` didn't handle FBI JSONL column aliases (`chunk_text`, `source_path`, `source_volume`)
2. `seed_epstein_matter.py`: SQLAlchemy `::json` cast conflict + missing `anchor_document_id`
3. `link_document_to_dataset()`: referenced non-existent `id` column in `dataset_documents`

**Qdrant dimension note**: Local collection is already 768d with named vectors -- FBI 768d vectors upserted directly with no dimension mismatch. GCP will need collection recreated at 768d during Phase 1.

### 0.5 Files for Phase 0
| File | Action | Status |
|------|--------|--------|
| `scripts/download_hf_dataset.py` | New | Done |
| `scripts/seed_epstein_matter.py` | Edit (add FBI terms, consolidate, fix SQL) | Done |
| `scripts/import_fbi_dataset.py` | New (+concurrency, +total_pages) | Done |
| `scripts/run_ner_pass.py` | New (deferred NER) | Done |
| `tests/test_ingestion/test_fbi_import.py` | New (35 tests) | Done |
| `docs/epstein-files-plan.md` | New (research doc) | Done |

---

## Phase 1: FBI Files -- `svetfm/epstein-fbi-files` (MVP) -- IMPORT COMPLETE, NER INCOMPLETE

**Why first**: Best metadata (page numbers, Bates, OCR confidence), pre-computed 768d nomic vectors (direct Qdrant load), full citation support. This is the proof-of-concept that validates the entire pipeline.

**Prerequisites**: Phase 0 complete. Import script validated locally. GCP wipe + 768d collection recreation needed before running.

**Dataset**: 236K chunks from 4,178 unique documents (grouped by `source_path`). Textract OCR (higher quality than Tesseract). Includes Bates numbers, page numbers, OCR confidence scores, source volumes, document types.

### Steps
1. **Download**: `python scripts/download_hf_dataset.py --dataset svetfm/epstein-fbi-files` (3.31 GB)
2. **Inspect schema**: Verify column names, document grouping key, embedding dimensions
3. **Seed**: `python scripts/seed_epstein_matter.py` (idempotent)
4. **Local test**: `python scripts/import_fbi_dataset.py --file data/fbi/... --matter-id ...-0002 --limit 50`
5. **GCP full import**: SSH -> download -> `python scripts/import_fbi_dataset.py --file ... --matter-id ... --disable-hnsw`

### 1.1 Local Validation Results (2026-03-19)

**Status**: 50 real FBI documents imported end-to-end locally. All stores verified. No script changes needed.

**Download**: 2,000 rows streamed via `--sample 2000 --data-files "embeddings/all_embeddings.jsonl"`. Parquet: 12.1 MB. Schema auto-detected as "rich (FBI-style)" — all 9 column aliases mapped correctly (`chunk_text`→text, `source_path`→source_file, `source_volume`→volume, `bates_range`→bates_number).

**Import results** (50 docs, full pipeline, 27.9 min):

| Store | Count | Notes |
|-------|-------|-------|
| PostgreSQL documents | 50 | All with bates metadata, OCR confidence, content hash |
| PostgreSQL chunks | 764 | Linked via jobs |
| PostgreSQL entities | 8,129 | Stored in document.entity_count |
| Qdrant points | 764 | Named vectors (dense), payloads: page_number, bates_number, ocr_confidence, citation_quality=full |
| Neo4j Documents | 50 | With matter_id filter |
| Neo4j Entities | 3,901 unique | 2,921 person, 334 flight_number, 163 org, 157 monetary, 147 date, 94 location |
| Neo4j Chunks | 764 | PART_OF→Document |
| Neo4j MENTIONED_IN | 7,340 | Entity→Document relationships |
| Dataset links | 50 | All linked to "FBI Files" dataset |
| MinIO uploads | 50 | Concatenated text at raw/{job_id}/{filename} |

**API verification**: Health endpoint shows all 5 services healthy. Documents API returns 50 docs. Entities API returns 3,940 entities. Entity search for "epstein" returns Jeffrey Epstein, Paula Epstein, J. Epstein, KAREN EPSTEIN.

**Notable documents**: Flight log (210 chunks, 1,612 entities), Contact Book (34 chunks each, 1,487 entities each), Evidence List from Maxwell trial (12 chunks).

**Performance**: ~1.8 docs/sec overall, NER-dominated (~2s/chunk on CPU for entity-dense chunks like contact book). Post-ingestion hooks dispatched: entity resolution, email detection, hot doc scan, entity resolution agent.

**Tests**: 28/28 FBI import tests pass, no regressions.

**NER throughput correction**: Measured ~2s/chunk (not 50ms/chunk as originally estimated). At 236K chunks, serial NER would take ~131 hours. This motivated the two-pass strategy below.

### 1.2 GCP Phase 1a Results (2026-03-20)

**Status**: COMPLETE. All 4,178 documents imported to GCP in 22.1 minutes.

**GCP setup changes**:
- Switched `.env`: `EMBEDDING_PROVIDER=ollama`, `EMBEDDING_DIMENSIONS=768`, `OLLAMA_EMBEDDING_MODEL=nomic-embed-text`
- Wiped all demo data (PG, Qdrant, Neo4j, MinIO, Redis)
- Deleted Qdrant `nexus_text` collection, API startup recreated at 768d with named vectors
- Pulled nomic-embed-text model into Ollama container
- Seeded Epstein matter via `seed_epstein_matter.py`
- Fixed Dockerfile: pinned `torch==2.6.0+cpu` + `torchvision==0.21.0+cpu` (unpinned torch grabbed 2.10.0 nightly which broke GLiNER)

**Import command**:
```bash
python scripts/import_fbi_dataset.py \
    --file /tmp/fbi_data/epstein_fbi_files.parquet \
    --matter-id 00000000-0000-0000-0000-000000000002 \
    --dataset-name "FBI Files" \
    --disable-hnsw --skip-ner --concurrency 4
```

**Import results** (4,178 docs, skip-ner, concurrency 4, 22.1 min):

| Store | Count | Notes |
|-------|-------|-------|
| PostgreSQL documents | 4,178 | All with bates metadata, OCR confidence, content hash |
| PostgreSQL jobs | 4,179 | One per doc + seed job |
| Qdrant points | 236,174 | 768d named vectors (dense), full payloads |
| Neo4j Documents | 4,178 | With matter_id filter |
| Neo4j Chunks | 236,174 | PART_OF relationships |
| Neo4j Entities | 0 | Deferred to Phase 1b |
| Dataset links | 4,178 | All linked to "FBI Files" dataset |
| MinIO uploads | 4,178 | Concatenated text at raw/{job_id}/{filename} |

**Performance**: Peak 10.4 docs/sec (small single-chunk docs), sustained 3.2 docs/sec overall. Bottleneck: Neo4j chunk node creation (serial per document, 200+ chunks for flight logs/contact books). HNSW disabled during import, rebuilt after.

**Doc count correction**: Dataset groups to 4,178 unique documents by `source_path` (not 8,150 as originally estimated from HuggingFace metadata). 236K chunks confirmed.

**What works now**: Vector search, document browsing, citations with page numbers and Bates numbers, full-text queries. Everything sourced from Qdrant chunk payloads.

**What's pending**: Entity graph (requires NER pass, Phase 1b running in background).

### 1.3 GCP Phase 1b Results (2026-03-20) -- INCOMPLETE

**Status**: INCOMPLETE. Plan originally claimed "all 29,973 jobs finished" but GCP audit (2026-03-22) shows only 1,147 / 27,689 pre-embedded docs (4.1%) have `entity_count > 0`. The "29,973 jobs complete" likely referred to Phase 1a import jobs, not NER jobs. The NER pass either didn't fully run, was interrupted by worker restarts, or `entity_count` wasn't updated for completed NER.

**Impact**: Entity graph, person connections, KG visualization, and communication analytics are unavailable for ~96% of pre-embedded docs (FBI + House Oversight). Vector search and citations still work (sourced from Qdrant payloads, independent of NER).

**To complete**: Re-run `python scripts/run_ner_pass.py --matter-id ...-0002 --concurrency 2` after email queue drains. Estimated ~131 hours at concurrency 2 for 26,542 docs.

**Command used**: `python scripts/run_ner_pass.py --matter-id ...-0002 --concurrency 2`

Used 2 workers (not 4) to leave headroom for API on GCP VM (16GB RAM). Each GLiNER model ~600MB = 1.2GB total.

**Known issue fixed**: Dockerfile torch version pin. Unpinned `torch` from PyTorch CPU index grabbed 2.10.0+cpu (nightly/dev build) which had no matching torchvision, breaking `transformers` -> `image_utils` -> `torchvision` import chain required by GLiNER. Fixed by pinning `torch==2.6.0+cpu` and `torchvision==0.21.0+cpu`.

### 1.4 Two-Pass Import Strategy (2026-03-19)

**Phase 1a — Fast import** (I/O-bound, ~30-60 min):
```bash
python scripts/import_fbi_dataset.py \
    --file ./data/epstein_fbi_files/epstein_fbi_files.parquet \
    --matter-id 00000000-0000-0000-0000-000000000002 \
    --disable-hnsw --skip-ner --concurrency 4
```
Imports all 4,178 docs to PG, MinIO, Qdrant, and Neo4j (doc + chunk nodes only). Citations work immediately. Vector search works immediately. Entity graph is empty.

**Phase 1b — Deferred NER** (CPU-bound, ~24-48 hours background):
```bash
python scripts/run_ner_pass.py \
    --matter-id 00000000-0000-0000-0000-000000000002 \
    --concurrency 4
```
Finds docs with `entity_count=0`, fetches chunks from Qdrant, runs GLiNER, indexes entities to Neo4j. Uses `ProcessPoolExecutor` for true CPU parallelism (bypasses GIL). Each worker loads its own GLiNER model (~600MB). With 4 workers on GCP (16GB RAM): ~2.4GB memory, ~33 hours estimated.

### What the import script does (full pipeline, pre-embedded path)
For each document (4,178 total), optionally parallelized via `--concurrency N`:
1. **PostgreSQL**: Create `jobs` + `documents` rows with Bates metadata, page count (prefers `total_pages` from dataset), content hash
2. **MinIO**: Upload concatenated document text to `raw/{job_id}/{filename}`
3. **Qdrant**: For each chunk -- use pre-computed 768d nomic vector (no API call), build `PointStruct` with full payload: `page_number`, `bates_number`, `doc_id`, `matter_id`, `chunk_text`, `chunk_index`, `ocr_confidence`, `source_file`, `token_count`
4. **GLiNER NER** (optional, `--skip-ner` to defer): Run entity extraction on every chunk (~2s/chunk on CPU) -- extracts people, organizations, dates, locations, monetary amounts
5. **Neo4j KG**: Create Document node -> Chunk nodes. If NER ran: Entity nodes (with dual labels per M11) -> MENTIONS/APPEARS_IN edges
6. **Batch upserts**: Qdrant 100 points/batch, Neo4j batched per document
7. **Post-ingestion hooks**: Entity resolution agent, email threading detection, hot document scan

### Citation verification
- `CitedClaim.page_number` <- from FBI chunk metadata
- `CitedClaim.bates_range` <- from FBI Bates numbers
- `CitedClaim.filename` <- from FBI source file
- `CitedClaim.excerpt` <- from Qdrant `chunk_text`
- CoVe `verify_citations` node works because chunks are retrievable with proper metadata

### Estimates
- **Cost**: $0 (pre-computed vectors)
- **Phase 1a (import, --skip-ner --concurrency 4)**: ~30-60 min (I/O-bound)
- **Phase 1b (NER pass, --concurrency 4)**: ~24-48 hours (CPU-bound, ~2s/chunk for 236K chunks)
- **Storage**: ~1-2 GB Qdrant, ~500 MB PostgreSQL, ~100 MB Neo4j

---

## Phase 2: House Oversight (pre-embedded) -- `svetfm/epstein-files-nov11-25-house-post-ocr-embeddings` -- MOSTLY COMPLETE (23,511/25,791)

**Why second**: Pre-computed 768d nomic vectors (same as Phase 1 -- $0 cost), adds 69K chunks covering different source material (estate documents, correspondence). **Degraded citations** -- no page numbers, no Bates ranges.

**Dataset**: 69,290 chunks from 25,791 unique documents (grouped by `source_file`). Sparse schema: `source_file`, `chunk_index`, `text`, `embedding`. Tesseract OCR (noisier than FBI's Textract).

### Steps
1. **Download**: Same download script with `--dataset svetfm/epstein-files-nov11-25-house-post-ocr-embeddings` (415 MB parquet)
2. **Import**: Reused `import_fbi_dataset.py` with `--citation-quality degraded` (auto-detects sparse schema)
3. **GCP import**: SSH -> download -> dry-run -> full import

### 2.1 GCP Import Results (2026-03-20)

**Status**: MOSTLY COMPLETE. 23,511 of 25,791 documents imported (~63 min). 2,280 docs were likely skipped by content hash dedup or empty text. GCP audit (2026-03-22) confirmed 23,511 linked to "House Oversight Pre-embedded" dataset. Ran concurrently with FBI NER pass (Phase 1b) with no issues.

**Import command**:
```bash
python scripts/import_fbi_dataset.py \
    --file /tmp/house_oversight/epstein_files_nov11_25_house_post_ocr_embeddings.parquet \
    --matter-id 00000000-0000-0000-0000-000000000002 \
    --dataset-name "House Oversight Pre-embedded" \
    --citation-quality degraded \
    --disable-hnsw --skip-ner --concurrency 4
```

**Import results** (25,791 docs, skip-ner, concurrency 4, ~63 min):

| Store | Count | Notes |
|-------|-------|-------|
| PostgreSQL documents | 25,791 | Linked to "House Oversight Pre-embedded" dataset |
| PostgreSQL jobs | 25,792 | One per doc + seed job |
| Qdrant points | 69,290 | 768d named vectors (dense), citation_quality=degraded |
| Neo4j Documents | 25,791 | With matter_id filter |
| Neo4j Chunks | 69,290 | PART_OF relationships |
| Neo4j Entities | 0 | Deferred (NER pass needed) |
| Dataset links | 25,791 | All linked to "House Oversight Pre-embedded" dataset |
| MinIO uploads | 25,791 | Concatenated text at raw/{job_id}/{filename} |

**Combined totals (FBI + House Oversight)**:

| Store | FBI | House Oversight | Total |
|-------|-----|-----------------|-------|
| PostgreSQL documents | 4,178 | 25,791 | 29,969 |
| Qdrant points | 236,174 | 69,290 | 305,464 |
| Neo4j Documents | 4,178 | 25,791 | 29,969 |
| Neo4j Chunks | 236,174 | 69,290 | 305,464 |

**Doc count note**: Dataset groups to 25,791 unique documents by `source_file` (not the 69K row count). Most are single-chunk documents with avg ~2.7 chunks/doc.

**What works now**: Vector search across both FBI + House Oversight, document browsing, citations (degraded for House Oversight -- filename only, no page numbers). House Oversight chunks have `citation_quality: "degraded"` in Qdrant payload.

**What's pending**: Entity graph for House Oversight docs (NER pass needed after Phase 1b completes).

### Citation impact
- `page_number` = `None` (not available in dataset)
- `bates_range` = `None`
- `filename` from `source_file` column
- `citation_quality` = `"degraded"` in Qdrant payload
- CoVe verification works on text-level (excerpt matching)

### Estimates (actual vs. planned)
- **Cost**: $0 (pre-computed vectors)
- **Import (--skip-ner --concurrency 4)**: ~63 min (planned 15-30 min; slower due to 25K docs, not 69K chunks -- higher per-doc overhead)
- **NER pass**: ~38 hours (69K chunks x ~2s/chunk, parallelizable) -- pending
- **Storage**: ~415 MB parquet + Qdrant/PG/Neo4j

---

## Phase 3: House Oversight (full pipeline) -- `tensonaut/EPSTEIN_FILES_20K`

**Why third**: This is the **same House Oversight source material** as Phase 2 but as raw text files. Running these through the full NEXUS ingestion pipeline (Docling parse -> semantic chunking -> Ollama embedding -> NER -> graph) produces proper NEXUS chunks. The existing `huggingface_csv` adapter already handles this format.

**Decision point**: Phase 2 vs Phase 3 are alternatives covering the same documents. Phase 2 is faster (pre-embedded) but degraded. Phase 3 is slower but produces native NEXUS chunks. Could skip Phase 2 and go straight to Phase 3 if we want cleaner data. Or do Phase 2 first as a quick win, then replace with Phase 3 later.

### Steps
1. **Download**: `python scripts/download_epstein_dataset.py --source teyler` (already exists, 106 MB)
2. **Import**: Use existing pipeline -- `python scripts/import_dataset.py huggingface_csv --file ./data/epstein/epstein_files_20k.parquet --matter-id ...-0002 --disable-hnsw`
3. **Celery workers**: Need running workers for the standard pipeline (`celery -A workers.celery_app worker --concurrency=2`)

### What's different from Phase 1-2
- Goes through full Celery pipeline (7 stages: parse -> chunk -> embed -> NER -> index)
- Ollama embeds each chunk (~25-30s/doc on CPU -- dominated by embedding)
- Semantic chunking produces NEXUS-native boundaries (not FBI's chunk boundaries)
- Page numbers still absent (text-only source material)

### Estimates
- **Cost**: $0 (Ollama local embedding)
- **Time**: 6-7 hours on GCP (25K docs x ~45s each / 2 Celery workers) -- or ~2 hours with `CELERY_CONCURRENCY=4`
- **Storage**: ~1 GB additional

---

## Phase 4: Epstein Emails -- PROCESSING (2026-03-20, ~23% complete as of 2026-03-22)

**Two complementary email datasets** -- different extraction methods, different structure.

### 4a: `to-be/epstein-emails` (4,272 rows, flat schema)
- Extracted via Qwen 2.5 VL 72B vision model from document images
- **Flat**: one row per message. Columns: `from_address`, `to_address`, `other_recipients`, `subject`, `timestamp_iso`, `message_html`, `document_id`, `source_filename`, `message_order`
- Body is HTML -- adapter strips tags to plain text
- 4,272 rows -> 3,480 emails (792 skipped: empty/short body after HTML stripping)

### 4b: `notesbymuneeb/epstein-emails` (5,082 threads, threaded JSON schema)
- Parsed via xAI Grok
- **Threaded**: one row per thread. Columns: `thread_id`, `source_file`, `subject`, `messages` (JSON array), `message_count`
- Each message in JSON has: `sender`, `recipients`, `timestamp`, `subject`, `body`
- 5,082 threads -> 16,447 messages -> 13,008 after filtering short bodies (3,439 skipped)
- Sender names cleaned (strips email addresses in `[]` and `<>` brackets)

### Why these matter for NEXUS
- Feed directly into EDRM email threading (M6b)
- Communication analytics (M10c): communication matrix, temporal patterns
- Email-as-node modeling (M11): Email nodes -> Person nodes via SENT/TO/CC/BCC edges
- Investigation agent tools: `search_communications`, `find_person_connections`

### Adapter: `app/ingestion/adapters/epstein_emails.py`
- Implements `DatasetAdapter` protocol (like `HuggingFaceCSVAdapter`)
- Auto-detects schema variant by column names (`from_address` = flat, `messages` = threaded)
- Maps to `ImportDocument(doc_type="email", email_headers={from, to, subject, date})`
- Content hash dedup across datasets via `--resume` flag
- Registered in `ADAPTER_REGISTRY` as `"epstein_emails"`
- CLI: `python scripts/import_dataset.py epstein_emails --file <path> --matter-id <uuid>`
- 19 unit tests covering both schemas, HTML stripping, recipient parsing, thread flattening, malformed JSON, limit enforcement

### GCP Import Results (2026-03-20)

**Dataset A** (to-be/epstein-emails):
- **Command**: `import_dataset.py epstein_emails --file /tmp/emails_tobe/epstein_emails.parquet --matter-id ...-0002 --disable-hnsw`
- **Dispatched**: 3,480 tasks, 0 skipped, 632.8s (5.5 docs/sec)
- **Bulk job ID**: `d4476aa2-f5a5-45a4-8529-36a014e9b50e`

**Dataset B** (notesbymuneeb/epstein-emails):
- **Command**: `import_dataset.py epstein_emails --file /tmp/emails_muneeb/epstein_emails.parquet --matter-id ...-0002 --resume --disable-hnsw`
- **Dispatched**: 12,858 tasks, 150 skipped (content hash dedup), 2256.4s (5.7 docs/sec)
- **Bulk job ID**: `648e1902-16ad-4c4a-95dc-708596e6752d`

**Combined**: 16,338 email tasks dispatched. Processing via single Celery worker (~20s/email = ~90 hours ETA). Each email goes through: chunking -> Ollama embedding -> GLiNER NER -> Qdrant indexing -> Neo4j email-as-node graph -> email threading.

**Dedup**: Only 150/13,008 messages in Dataset B matched content hashes from Dataset A -- very little overlap (expected since the two datasets use different extraction methods on the same source material).

### Post-ingestion hooks dispatched
- `entities.resolve_entities` -- merge duplicate entities across email + document sources
- `ingestion.detect_inclusive_emails` -- flag emails that contain/forward other emails
- `agents.hot_document_scan` -- LLM scan for high-value investigative content
- `agents.entity_resolution_agent` -- autonomous entity dedup agent

### Estimates (actual vs. planned)
- **Cost**: $0 (Ollama embedding)
- **Dispatch time**: ~48 min total (11 min Dataset A + 37 min Dataset B)
- **Processing time**: ~90 hours (single Celery worker, embedding-dominated)
- **Storage**: ~5 MB parquet source, Qdrant/PG/Neo4j TBD after processing completes

### Files created/modified
| File | Action |
|------|--------|
| `app/ingestion/adapters/epstein_emails.py` | **New**: Email adapter for HF datasets |
| `app/ingestion/adapters/__init__.py` | Edit: register adapter |
| `scripts/import_dataset.py` | Edit: add `epstein_emails` choice |
| `tests/test_ingestion/test_epstein_email_adapter.py` | **New**: 19 tests |

### Pending verification (after processing completes)
- PG: `SELECT count(*) FROM documents WHERE document_type = 'email'` -- expect ~16,338
- Neo4j: `MATCH (e:Email) RETURN count(e)` -- email nodes exist
- Neo4j: `MATCH (p:Person)-[:SENT]->(e:Email) RETURN count(*)` -- SENT edges exist
- Qdrant: point count increased by ~16K+
- Email threading: `SELECT count(DISTINCT thread_id) FROM documents WHERE document_type = 'email'`
- Communication pairs: `SELECT count(*) FROM communication_pairs`

---

## Phase 5: Giuffre v. Maxwell Court Documents

**Source**: CourtListener RECAP archive (`courtlistener.com/docket/4355835/giuffre-v-maxwell/`)

~2-3K pages of motions, depositions, exhibits released in 8+ batches. Native PDFs with text layers -- ideal for Docling parsing.

### Scripts
- **Download**: `scripts/download_courtlistener.py` — queries CourtListener REST API (`/api/rest/v3/recap-documents/`), downloads available PDFs with rate limiting (1 req/sec). Optional `--api-token` for authenticated access. Falls back to Public Intelligence mirrors if API is unavailable.
- **Import**: `scripts/import_pdf_directory.py` — uploads PDFs to MinIO and dispatches `process_document` Celery tasks (Docling parsing pipeline).

### Commands
```bash
# Download
python scripts/download_courtlistener.py \
    --docket-id 4355835 \
    --output-dir /tmp/maxwell_docs

# Import
python scripts/import_pdf_directory.py \
    --dir /tmp/maxwell_docs \
    --matter-id 00000000-0000-0000-0000-000000000002 \
    --dataset-name "Giuffre v. Maxwell Court Docs" \
    --disable-hnsw
```

### What's special
- Properly formatted court documents (not scanned images) -- Docling produces excellent structured output
- Depositions have Q&A structure that the query agent can exploit
- Named entities are densely packed (names, dates, locations referenced repeatedly)
- **Full citation support**: Page numbers extracted from PDF structure automatically

### Estimates
- **Cost**: $0 (Ollama embedding)
- **Time**: 1-2 hours (2-3K pages is small)
- **Storage**: ~200 MB

---

## Phase 6: FBI FOIA Vault

**Source**: `vault.fbi.gov/jeffrey-epstein` -- 22 parts, ~2-3K pages of older FOIA releases.

**Challenge**: Scanned image PDFs without text layers. Docling handles OCR automatically via built-in backend.

### Scripts
- **Download**: `scripts/download_fbi_vault.py` — scrapes the FBI vault index page, discovers PDF links for all 22 parts, downloads with rate limiting (1 req/sec). Resume-safe (skips existing files).
- **Import**: `scripts/import_pdf_directory.py` — same shared PDF import script as Phase 5.

### Commands
```bash
# Download
python scripts/download_fbi_vault.py \
    --output-dir /tmp/fbi_vault

# Import (Docling auto-detects scanned PDFs and applies OCR)
python scripts/import_pdf_directory.py \
    --dir /tmp/fbi_vault \
    --matter-id 00000000-0000-0000-0000-000000000002 \
    --dataset-name "FBI FOIA Vault" \
    --disable-hnsw
```

### OCR handling
- Docling auto-detects scanned image PDFs and applies built-in OCR -- no manual configuration needed
- **Optional quality boost**: Set `ENABLE_OCR_CORRECTION=true` on GCP before import for regex-based legal OCR fixes (`app/ingestion/ocr_corrector.py`)
- **Quality check**: After import, spot-check documents via API. If OCR quality is poor, consider re-import with `ENABLE_CONTEXTUAL_CHUNKS=true` (LLM-assisted chunk enrichment)

### Estimates
- **Cost**: $0 (local OCR + Ollama embedding) or ~$5-10 if using Textract
- **Time**: 2-4 hours (OCR adds ~5-10s/page)
- **Storage**: ~200 MB

### Parallel execution
Phases 5 and 6 can run simultaneously. Both download scripts are independent. Both import commands dispatch to the same Celery worker queue -- bump worker concurrency to `-c 2` during import:
```bash
$COMPOSE exec -T worker celery -A workers.celery_app control pool_resize 2
```

---

## Phase 7: DOJ EFTA Datasets 1-12 (Long-term)

**The big one**: ~3.5M pages across 305-400 GB. This is a weeks-long project.

**Acquisition**: DOJ removed bulk ZIP downloads Feb 2026. Torrents only via `github.com/yung-megafone/Epstein-Files` (verified magnet links + SHA hashes). Internet Archive mirrors for most datasets.

| DOJ Dataset | Size | Contents | Status |
|-------------|------|----------|--------|
| 1-7 | ~4.2 GB | FBI interviews, police reports (2005-2008) | Complete |
| 8 | ~10.7 GB | FBI interviews, police reports | Complete |
| 9 | ~180 GB | Emails, DOJ correspondence re: 2008 NPA | Incomplete (49-96 GB recovered) |
| 10 | ~82 GB | 180K images + 2K videos from properties | Complete |
| 11 | ~27.5 GB | Financial ledgers, flight manifests, property records | Complete |
| 12 | ~114 MB | Late productions, supplemental items | Complete |

### Approach
1. **Start with Datasets 1-7 + 12** (~4.3 GB) -- smallest, manageable on GCP VM disk
2. **Bulk OCR pipeline**: Need a scalable OCR approach (Docling + EasyOCR, or AWS Textract Batch API, or Google Document AI)
3. **Dataset 11** (financial/flight logs) -- highest investigation value, structured data
4. **Dataset 8** (interviews) -- high investigation value, text-heavy
5. **Dataset 9** (emails) -- largest, partially incomplete
6. **Dataset 10** (images/videos) -- requires visual pipeline, different tooling

### Infrastructure considerations
- GCP VM (e2-standard-4, 16 GB RAM) may not have enough disk for full corpus
- Consider: attached persistent SSD (100-500 GB) for staging
- Consider: batch processing with Google Document AI for OCR at scale
- Ingestion would be batched over days/weeks, not a single run

### Estimates (Datasets 1-7 + 12 only)
- **Cost**: $0-50 depending on OCR approach
- **Time**: Days (OCR + embedding + NER for ~50K+ pages)
- **Storage**: 10-50 GB

---

## Execution Priority & Dependencies

```
Phase 0 (Foundation)     <- Must do first, ~2 hours -- COMPLETE
  |
  +-- Phase 1a (FBI import, --skip-ner)  <- 22.1 min, $0 -- COMPLETE (2026-03-20)
  |     |
  |     +-- Phase 1b (FBI NER pass)      <- ~131 hrs est. -- INCOMPLETE (4.1% done, see 1.3)
  |     |
  |     +-- Phase 2 (House Oversight pre-embedded)  <- 63 min, $0 -- MOSTLY COMPLETE (23,511/25,791 docs)
  |     |     OR
  |     +-- Phase 3 (House Oversight full pipeline)  <- Better quality, ~6 hours, $0
  |
  +-- Phase 4 (Emails)  <- 16,338 dispatched, ~23% complete -- PROCESSING (2026-03-21, 3 workers)
  |
  +-- Phase 5 (Court Docs)  <- Anytime, ~2 hours, $0
  |
  +-- Phase 6 (FBI FOIA)  <- After pipeline proven, ~4 hours, $0-10 (20 test docs imported)
  |
  +-- Phase 7 (DOJ EFTA)  <- Long-term, days/weeks, $0-50
```

**GCP audit (2026-03-22)**: Phase 1b NER is ~96% incomplete despite being marked COMPLETE. 26,542 pre-embedded docs have `entity_count=0`. Phase 4 emails are actively processing (~3,810 of ~16,338 docs created, ~9,285 tasks still pending in queue, 76 failed). 3 Celery workers active.

**Next priority after email queue drains**: Re-run NER pass for pre-embedded docs, retry failed jobs, then consider Phase 5 (court docs).

---

## Shared Infrastructure Decisions

### Single matter vs. multiple matters
**Recommendation**: Single Epstein matter (`...-0002`) with all datasources as separate `datasets` rows. This allows:
- Cross-source queries ("find all references to X across FBI files AND court documents")
- Unified entity graph (entities from different sources linked)
- Matter-level analytics (communication patterns across all sources)
- Per-dataset filtering via `dataset_id` query parameter

### NER Strategy: Two-Pass Import
GLiNER NER runs at ~2s/chunk on CPU (measured, not the originally estimated 50ms/chunk). For large datasets (236K+ chunks), this dominates import time by 40x.

**Strategy**: Import all documents fast with `--skip-ner --concurrency N` (I/O-bound, parallelizes well), then run NER as a deferred background pass via `scripts/run_ner_pass.py` (CPU-bound, uses `ProcessPoolExecutor` for true parallelism past GIL).

**What works without NER**: Vector search, citations, document browsing, full-text queries, chunk retrieval. Everything sourced from Qdrant payloads.

**What requires NER**: Entity graph traversal (`search_entities`, `find_person_connections`), communication analytics, entity-based filtering, knowledge graph visualization. These come online after the NER pass completes.

**Tooling**:
- `scripts/import_fbi_dataset.py --skip-ner --concurrency 4` — fast I/O-bound import
- `scripts/run_ner_pass.py --concurrency 4` — deferred NER with CPU parallelism

### Embedding standardization
- All datasets use nomic-embed-text 768d (via Ollama on GCP)
- Pre-computed vectors used when available (FBI, House Oversight pre-embedded)
- Full pipeline embedding for raw text sources (emails, court docs, DOJ)
- Query encoding always via Ollama nomic-embed-text

### Entity deduplication
- GLiNER extracts entities from all sources independently
- Entity Resolution Agent (M11) runs post-ingestion to merge duplicates
- Critical for Epstein corpus: same names appear in wildly different forms across sources
- Post-ingestion hook dispatches automatically after each import

### Citation quality tiers
Store `citation_quality` in Qdrant payload:
- `"full"` -- page_number + bates_range + filename (FBI files, court docs)
- `"degraded"` -- filename only, no page numbers (House Oversight pre-embedded)
- `"email"` -- email thread reference instead of page (emails)

Frontend can show appropriate UI per tier (page jump vs. document link vs. thread view).

---

## Verification (end-to-end, after each phase)

1. **Counts**: PostgreSQL documents + Qdrant points + Neo4j nodes match expectations
2. **Query test**: Run 3-5 investigative queries against the matter
3. **Citation check**: Verify `cited_claims` in response have appropriate metadata per citation tier
4. **Entity graph**: Check entity page shows connected entities from ingested source
5. **Frontend**: Browse documents, click citations, verify page viewer works (for full-citation sources)
6. **Regression**: Run backend test suite (4 parallel agents per CLAUDE.md rule 43)
