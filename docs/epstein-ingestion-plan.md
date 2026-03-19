# Epstein Files Ingestion Roadmap

## Context

NEXUS is a multimodal RAG investigation platform. The GCP environment currently has only test seed data (14 docs, 143 entities) from development -- this will be wiped. We're now transitioning to real data: the Epstein document corpus spanning FBI files, House Oversight releases, email collections, court documents, and DOJ EFTA releases.

This roadmap covers **all available datasources** in priority order, from quick wins (pre-processed HuggingFace datasets with pre-computed embeddings) to the long tail (3.5M-page DOJ corpus requiring bulk OCR).

**GCP embedding setup**: Ollama with nomic-embed-text (768d). Several HuggingFace datasets include pre-computed 768d nomic vectors -- these load directly at $0 cost.

**Full pipeline always**: Every datasource goes through: embedding (pre-computed or Ollama) -> GLiNER NER entity extraction -> Neo4j knowledge graph indexing -> Qdrant vector indexing -> PostgreSQL document records -> MinIO raw storage. The only shortcut is using pre-computed vectors where available (skips the Ollama embedding call). Entities, graph, and citations are never skipped.

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

## Phase 0: Foundation (wipe + infrastructure)

**Goal**: Clean slate on GCP. Standardize embedding setup. Build reusable import tooling.

### 0.1 Wipe GCP demo data
- Follow `memory/wipe-reingest.md` procedure
- Delete all Qdrant collections, truncate PostgreSQL tables, clear Neo4j, clear MinIO
- Recreate `nexus_text` collection at 768d (Ollama nomic-embed-text)

### 0.2 Verify GCP embedding config
- Confirm `.env` on GCP has `EMBEDDING_PROVIDER=ollama`, `EMBEDDING_DIMENSIONS=768`, `OLLAMA_EMBEDDING_MODEL=nomic-embed-text`
- Confirm Ollama container is healthy and has nomic-embed-text model pulled
- Confirm Qdrant collection is 768d after recreation

### 0.3 Create shared tooling
These scripts are reused across all phases:

**`scripts/download_hf_dataset.py`** (new)
- Downloads from HuggingFace with `--sample N` for local testing
- Prints schema inspection (columns, types, sample values, null counts)
- Generic enough to download any HF dataset with `--dataset` flag

**`scripts/seed_epstein_matter.py`** (already exists)
- Update to be the single matter for all Epstein sources
- Matter ID: `00000000-0000-0000-0000-000000000002`
- Add FBI-specific defined terms (FOIA, FD-302, SAC, etc.) alongside existing House Oversight terms
- All datasets (FBI, House Oversight, emails, court docs) belong to this one matter
- Idempotent -- can be re-run as new datasources are added

**`scripts/import_fbi_dataset.py`** (new -- becomes template for pre-embedded imports)
- Custom import for pre-chunked + pre-embedded HuggingFace datasets
- Handles: Parquet reading -> document grouping -> PostgreSQL records -> Qdrant upsert (pre-computed vectors) -> GLiNER NER -> Neo4j graph
- CLI: `--file`, `--matter-id`, `--limit`, `--dry-run`, `--resume`, `--disable-hnsw`, `--skip-ner`, `--skip-neo4j`, `--re-embed`
- Pattern is reusable for any pre-embedded HF dataset

### 0.4 Files for Phase 0
| File | Action |
|------|--------|
| `scripts/download_hf_dataset.py` | New |
| `scripts/seed_epstein_matter.py` | Edit (add FBI terms, consolidate) |
| `scripts/import_fbi_dataset.py` | New |
| `tests/test_ingestion/test_fbi_import.py` | New |

---

## Phase 1: FBI Files -- `svetfm/epstein-fbi-files` (MVP)

**Why first**: Best metadata (page numbers, Bates, OCR confidence), pre-computed 768d nomic vectors (direct Qdrant load), full citation support. This is the proof-of-concept that validates the entire pipeline.

**Dataset**: 236K chunks from 8,150 FBI documents. Textract OCR (higher quality than Tesseract). Includes Bates numbers, page numbers, OCR confidence scores, source volumes, document types.

### Steps
1. **Download**: `python scripts/download_hf_dataset.py --dataset svetfm/epstein-fbi-files` (3.31 GB)
2. **Inspect schema**: Verify column names, document grouping key, embedding dimensions
3. **Seed**: `python scripts/seed_epstein_matter.py` (idempotent)
4. **Local test**: `python scripts/import_fbi_dataset.py --file data/fbi/... --matter-id ...-0002 --limit 50`
5. **GCP full import**: SSH -> download -> `python scripts/import_fbi_dataset.py --file ... --matter-id ... --disable-hnsw`

### What the import script does (full pipeline, pre-embedded path)
For each document (8,150 total):
1. **PostgreSQL**: Create `jobs` + `documents` rows with Bates metadata, page count, content hash
2. **MinIO**: Upload concatenated document text to `raw/{job_id}/{filename}`
3. **Qdrant**: For each chunk -- use pre-computed 768d nomic vector (no API call), build `PointStruct` with full payload: `page_number`, `bates_number`, `doc_id`, `matter_id`, `chunk_text`, `chunk_index`, `ocr_confidence`, `source_file`, `token_count`
4. **GLiNER NER**: Run entity extraction on every chunk (~50ms/chunk) -- extracts people, organizations, dates, locations, monetary amounts
5. **Neo4j KG**: Create Document node -> Entity nodes (with dual labels per M11) -> Chunk nodes -> MENTIONS/APPEARS_IN edges
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
- **Time**: 30-90 min (NER-bound at ~50ms/chunk for 236K chunks)
- **Storage**: ~1-2 GB Qdrant, ~500 MB PostgreSQL, ~100 MB Neo4j

---

## Phase 2: House Oversight (pre-embedded) -- `svetfm/epstein-files-nov11-25-house-post-ocr-embeddings`

**Why second**: Pre-computed 768d nomic vectors (same as Phase 1 -- $0 cost), adds 69K chunks covering different source material (estate documents, correspondence). **Degraded citations** -- no page numbers, no Bates ranges.

**Dataset**: 69K chunks from House Oversight Nov 2025 release. Sparse schema: `source_file`, `chunk_index`, `text`, `embedding`. Tesseract OCR (noisier than FBI's Textract).

### Steps
1. **Download**: Same download script with `--dataset svetfm/epstein-files-nov11-25-house-post-ocr-embeddings` (357 MB)
2. **Import**: Adapt `import_fbi_dataset.py` or create `import_house_oversight.py` (simpler schema, no page numbers)
3. **GCP import**: SSH -> download -> import

### Citation impact
- `page_number` defaults to `None` (not available in dataset)
- `bates_range` defaults to `None`
- `filename` available from `source_file` column
- Frontend PDF viewer click-through won't work (no page to jump to)
- CoVe verification still works on text-level (excerpt matching)
- Consider: add a `citation_quality: "degraded" | "full"` flag to Qdrant payload so the frontend can show a warning badge

### Estimates
- **Cost**: $0
- **Time**: 15-30 min
- **Storage**: ~500 MB additional

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

## Phase 4: Epstein Emails

**Two complementary email datasets** -- different extraction methods, different structure.

### 4a: `to-be/epstein-emails` (3,997 emails)
- Extracted via Qwen 2.5 VL 72B vision model from document images
- Likely has structured fields: from, to, date, subject, body
- Smaller but potentially higher extraction quality

### 4b: `notesbymuneeb/epstein-emails` (5,082 threads, 16,447 messages)
- Parsed via xAI Grok
- Thread-level structure (multiple messages per thread)
- Larger coverage

### Why these matter for NEXUS
- Feed directly into EDRM email threading (M6b)
- Communication analytics (M10c): communication matrix, temporal patterns
- Email-as-node modeling (M11): Email nodes -> Person nodes via SENT/TO/CC/BCC edges
- Investigation agent tools: `search_communications`, `find_person_connections`

### Steps
1. **Download & inspect**: Download both datasets, inspect schemas (need: from, to, cc, date, subject, body)
2. **Write email adapter**: New adapter `app/ingestion/adapters/epstein_emails.py` that:
   - Reads email dataset (CSV/Parquet/JSON)
   - Maps fields to `ImportDocument` with `email_headers` dict
   - Sets `doc_type="email"` for email-as-node pipeline
3. **Import via standard pipeline**: The existing Celery task handles email_headers -> creates Email nodes in Neo4j, SENT/TO edges, etc.
4. **Dedup across datasets**: Both cover overlapping emails. Use content hash or (from + date + subject) for dedup.

### Estimates
- **Cost**: $0 (Ollama embedding)
- **Time**: 2-4 hours (16K messages through Celery pipeline)
- **Storage**: ~500 MB

---

## Phase 5: Giuffre v. Maxwell Court Documents

**Source**: CourtListener RECAP archive (`courtlistener.com/docket/4355835/giuffre-v-maxwell/`)

~2-3K pages of motions, depositions, exhibits released in 8+ batches. Native PDFs with text layers -- ideal for Docling parsing.

### Steps
1. **Download**: Script to bulk-download from CourtListener RECAP API or Public Intelligence mirrors
2. **Organize**: Save PDFs to a directory, one per filing
3. **Import via standard pipeline**: Use `directory` adapter with PDF support, or upload PDFs through the NEXUS UI/API
4. **Full citation support**: Docling extracts page numbers from PDF structure -> full page-level citations

### What's special
- These are properly formatted court documents (not scanned images)
- Docling parsing produces excellent structured output
- Depositions have Q&A structure that the query agent can exploit
- Named entities are densely packed (names, dates, locations referenced repeatedly)

### Estimates
- **Cost**: $0 (Ollama embedding)
- **Time**: 1-2 hours (2-3K pages is small)
- **Storage**: ~200 MB

---

## Phase 6: FBI FOIA Vault

**Source**: `vault.fbi.gov/jeffrey-epstein` -- 22 parts, ~2-3K pages of older FOIA releases.

**Challenge**: Scanned image PDFs without text layers. Requires OCR.

### Steps
1. **Download**: Script to crawl FBI vault and download all 22 PDF parts
2. **OCR pipeline**: Docling handles image PDFs with built-in OCR (EasyOCR). Alternatively, use Textract for higher quality (paid).
3. **Import via standard pipeline**: Upload PDFs -> Docling parse (with OCR) -> chunk -> embed -> NER -> index
4. **Quality check**: OCR quality on scanned FBI documents may be poor. Spot-check and potentially enable `ENABLE_OCR_CORRECTION` (LLM post-processing)

### Estimates
- **Cost**: $0 (local OCR + Ollama embedding) or ~$5-10 if using Textract
- **Time**: 2-4 hours (OCR is slow, ~5-10s/page)
- **Storage**: ~200 MB

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
Phase 0 (Foundation)     <- Must do first, ~2 hours
  |
  +-- Phase 1 (FBI Files)    <- MVP, ~2 hours, $0
  |     |
  |     +-- Phase 2 (House Oversight pre-embedded)  <- Quick add, ~1 hour, $0
  |     |     OR
  |     +-- Phase 3 (House Oversight full pipeline)  <- Better quality, ~6 hours, $0
  |
  +-- Phase 4 (Emails)  <- Parallel with 2/3, ~4 hours, $0
  |
  +-- Phase 5 (Court Docs)  <- Anytime after Phase 0, ~2 hours, $0
  |
  +-- Phase 6 (FBI FOIA)  <- After pipeline proven, ~4 hours, $0-10
  |
  +-- Phase 7 (DOJ EFTA)  <- Long-term, days/weeks, $0-50
```

**Recommended first session**: Phase 0 + Phase 1 (foundation + FBI files). This gets 8,150 real documents with full citation support running on GCP in one session.

**Next sessions**: Phase 4 (emails) for communication analytics, then Phase 5 (court docs) for high-value depositions.

---

## Shared Infrastructure Decisions

### Single matter vs. multiple matters
**Recommendation**: Single Epstein matter (`...-0002`) with all datasources as separate `datasets` rows. This allows:
- Cross-source queries ("find all references to X across FBI files AND court documents")
- Unified entity graph (entities from different sources linked)
- Matter-level analytics (communication patterns across all sources)
- Per-dataset filtering via `dataset_id` query parameter

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
