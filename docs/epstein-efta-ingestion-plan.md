# DOJ EFTA Full Corpus Ingestion Plan (v2 — Revised)

## Context

Ingest ~222GB of DOJ EFTA datasets (DS 1-7+12, DS 8, DS 9, DS 11) into NEXUS on the T4 GPU VM (`nexus-gpu`, n1-standard-8, 30GB RAM, 200GB SSD, us-west1-a). Excludes DS 10 (images/videos). Goal: maximize investigation accuracy, keep extra GCP spend under ~$50, complete in 3-4 days. Every phase has a validation gate.

**Current state**: 18,681 docs / 259,584 chunks already ingested (Tiers 1-2). 15K+ NER tasks still in queue (draining via on-VM ner-worker, concurrency 5).

**Storage**: All raw data lives permanently in GCS (`gs://nexus-epstein-data/`). GCS Standard class in us-west1 (~$4.50/mo for 222GB). VM reads via gcsfuse for DS 1-8+11+12. DS 9 staged locally in batches (see below).

**Download strategy**: Per-dataset torrents from [yung-megafone/Epstein-Files](https://github.com/yung-megafone/Epstein-Files) repo — NOT the monolithic `.tar.zst` archive. Individual `.torrent` files give immediate access without decompression.

---

## Dataset Reality (Format Corrections)

| Dataset | What it actually is | Format | Adapter | Size |
|---|---|---|---|---|
| DS 1-7 | FBI interviews, Palm Beach police reports | Text-native PDFs | `import_pdf_directory.py` | ~3.0GB |
| DS 8 | FBI interviews, police reports (more) | PDFs, some scanned | `import_pdf_directory.py` | ~10.7GB |
| DS 9 | Emails flattened to PDF via Concordance export | PDFs + VOL00009.OPT/.DAT load files + NATIVE media (skip) | `ConcordanceDATAdapter` | ~180GB (incomplete, ~10GB video removed by DOJ) |
| DS 11 | Financial ledgers, flight manifests, property records | Scanned PDFs | `import_pdf_directory.py` | ~25.5GB |
| DS 12 | Supplemental docs | PDFs | `import_pdf_directory.py` | ~114MB |

**Key corrections from v1:**
- **DS 9 is NOT native .eml files.** It's a Concordance litigation support export with `VOL00009.OPT` and `VOL00009.DAT` load files + 528K PDF images + 2.3K native files (many video/media — skip these). Use existing `ConcordanceDATAdapter`, NOT a new `EMLFileAdapter`.
- **DS 11 is NOT structured CSV/XLSX.** It's scanned PDFs of paper records. No `FlightManifestAdapter` needed — Docling's table-aware chunking handles it.
- **DS 9 is known incomplete.** ~10GB of video removed from DOJ site, never re-added.
- **DS 9 OCR quality is degraded.** Concordance-to-PDF export introduces encoding artifacts (e.g., `=9` instead of `19`). Use `QUALITY_SCORE_THRESHOLD=0.5`.
- **DS 9 email threading will be limited.** PDFs don't expose RFC 5322 headers. Threading depends on OPT/DAT metadata fields.
- **No new adapters needed.** Phase 1 code changes shrink from 4-6 hours to ~30 minutes.

---

## Phase 0: Download & Validate (~4-6 hours, ~$2)

### 0.1 — Infrastructure (done)

- [x] GCS bucket created: `gs://nexus-epstein-data/`
- [x] Downloader VM running: `nexus-downloader` (e2-medium, 500GB, us-west1-a, spot)
- [x] aria2 installed
- [x] Per-dataset `.torrent` files available from GitHub index repo

### 0.2 — Download DS 1-7+12 First (smallest, validates pipeline)

```bash
# On nexus-downloader VM:
cd /data

# Download DS 1-7 via individual torrent files (~3GB total, should be fast)
for ds in 1 2 3 4 5 6 7; do
    aria2c --seed-time=0 "/tmp/Epstein-Files/Torrent Files/DataSet $ds.torrent" -d /data/ds$ds/ &
done
wait

# DS 12 — download from DOJ directly (114MB, still accessible)
mkdir -p /data/ds12
curl -sfL "https://www.justice.gov/epstein/doj-disclosures/data-set-12-files" | \
  grep -oP 'href="https://www.justice.gov/epstein/files/[^"]*\.pdf"' | \
  sed 's/href="//;s/"$//' | xargs -P4 -I{} wget -q -P /data/ds12/ {}

# Upload to GCS
gsutil -m rsync -r /data/ds1/ gs://nexus-epstein-data/ds1/
gsutil -m rsync -r /data/ds2/ gs://nexus-epstein-data/ds2/
# ... repeat for ds3-7, ds12
```

### 0.3 — Pipeline Smoke Test (100 docs)

```bash
# On nexus-gpu VM (start it first):
gcsfuse --implicit-dirs nexus-epstein-data /mnt/epstein

COMPOSE='sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.gpu.yml'

$COMPOSE exec api python scripts/import_pdf_directory.py \
  --dir /mnt/epstein/ds1 \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --dataset-name "DOJ EFTA Sample DS1" \
  --limit 100 --disable-hnsw
```

### GATE 0: Validation

- [ ] 100 docs ingested successfully
- [ ] Qdrant chunks at 1024d
- [ ] NER entities in Neo4j
- [ ] No Docling crashes
- [ ] Embedding throughput >100 chunks/sec
- [ ] GCS FUSE read speed acceptable for DS 1-8 (small files OK over FUSE)

---

## Phase 1: Code Changes (~30 minutes) — DONE

- [x] `NER_BATCH_SIZE` config wired into `_stage_extract()` and `extract_entities_for_job()` (commit `9b2263e`)
- [x] `QUALITY_SCORE_THRESHOLD` config wired into contextualizer (commit `9b2263e`)
- [x] NER worker VM scripts: `create_ner_workers.sh`, `delete_ner_workers.sh`, `ner_worker_startup.sh` (commit `9b2263e`)
- [x] Tests passing

**Removed from v1 (not needed):**
- ~~EMLFileAdapter~~ — DS 9 is Concordance PDFs, not .eml files
- ~~FlightManifestAdapter~~ — DS 11 is scanned PDFs, not CSV/XLSX

---

## Phase 2: DS 1-7+12 Ingestion (~4.3GB, ~3 hours)

Highest signal density. Contextual chunks enabled (foundational docs).

```bash
ENABLE_CONTEXTUAL_CHUNKS=true
ENABLE_CHUNK_QUALITY_SCORING=true
DEFER_NER_TO_QUEUE=true

$COMPOSE exec api python scripts/import_pdf_directory.py \
  --dir /mnt/epstein/ds1 \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --dataset-name "DOJ EFTA DS 1" \
  --disable-hnsw --resume

# Repeat for ds2-7, ds12 (or write a loop)
for ds in 2 3 4 5 6 7 12; do
  $COMPOSE exec api python scripts/import_pdf_directory.py \
    --dir /mnt/epstein/ds$ds \
    --matter-id 00000000-0000-0000-0000-000000000002 \
    --dataset-name "DOJ EFTA DS $ds" \
    --disable-hnsw --resume
done
```

### GATE 2: Validation

- [ ] Doc count matches expected
- [ ] Contextual chunk prefixes populated
- [ ] Quality scores computed
- [ ] NER queue draining at expected rate
- [ ] Sample query returns DS 1-7 docs

---

## Phase 3: DS 8 Ingestion (~10.7GB, ~6 hours)

```bash
# Download DS 8 on downloader VM
aria2c --seed-time=0 "/tmp/Epstein-Files/Torrent Files/DataSet 8.torrent" -d /data/ds8/
gsutil -m rsync -r /data/ds8/ gs://nexus-epstein-data/ds8/

# Ingest (contextual chunks OFF — not worth LLM cost at this volume)
ENABLE_CONTEXTUAL_CHUNKS=false

$COMPOSE exec api python scripts/import_pdf_directory.py \
  --dir /mnt/epstein/ds8 \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --dataset-name "DOJ EFTA DS 8" \
  --disable-hnsw --resume
```

### GATE 3: Validation

- [ ] Docling parsed all formats without crashes
- [ ] OCR quality acceptable (spot-check 10 docs)
- [ ] NER backlog manageable

---

## Phase 4: Spin Up NER Workers (~$27)

**Only after Gates 2-3 pass and NER backlog is confirmed large.**

```bash
$COMPOSE exec rabbitmq rabbitmqctl list_queues name messages consumers
```

If NER backlog > 50K: spin up 6 spot VMs.

```bash
# Push Docker image to GCR first
sudo docker tag nexus-api:latest gcr.io/vault-ai-487703/nexus-api:latest
sudo docker push gcr.io/vault-ai-487703/nexus-api:latest

# Create workers
bash scripts/infra/create_ner_workers.sh 6
```

### GATE 4: NER Worker Validation

- [ ] 6+1 consumers on `ner` queue
- [ ] NER drain rate ~6x faster
- [ ] No task errors in first 30 min

**If Gate 4 fails**: `bash scripts/infra/delete_ner_workers.sh`

---

## Phase 5: DS 9 — Concordance Email Production (~180GB, ~50-55 hours)

### Critical DS 9 notes:
- **Format**: Concordance export — `VOL00009.OPT` + `VOL00009.DAT` load files + 528K PDF images + 2.3K native files
- **Skip**: Native media files (.wmv, .ts, .db) — filter by extension before ingesting
- **OCR quality**: Degraded from Concordance-to-PDF export. Use `QUALITY_SCORE_THRESHOLD=0.5`
- **Known incomplete**: ~10GB video removed by DOJ, never restored
- **Threading**: Limited — PDFs don't have RFC 5322 headers. Check OPT/DAT for thread metadata
- **GCS FUSE WARNING**: 528K small PDFs over FUSE = latency nightmare. Stage batches locally.

### 5.1 — Download DS 9

```bash
# On downloader VM — DS 9 is the big one (~181GB)
aria2c --seed-time=0 "/tmp/Epstein-Files/Torrent Files/dataset-09 (Incomplete).torrent" -d /data/ds9/

# Upload to GCS in parallel as it downloads
gsutil -m rsync -r /data/ds9/ gs://nexus-epstein-data/ds9/
```

### 5.2 — Identify DS 9 Structure

```bash
# After download, find the OPT/DAT load files
find /data/ds9 -name "*.OPT" -o -name "*.DAT" -o -name "*.opt" -o -name "*.dat" | head
find /data/ds9 -name "*.pdf" | wc -l   # Should be ~528K
find /data/ds9 -name "*.wmv" -o -name "*.ts" -o -name "*.db" | wc -l  # Media to skip
```

### 5.3 — Ingest via ConcordanceDATAdapter (batched, not FUSE)

DS 9's 528K small PDFs will kill performance over GCS FUSE. Stage locally in batches:

```bash
# Stage 20K PDFs at a time to local SSD, ingest, clean up, repeat
QUALITY_SCORE_THRESHOLD=0.5  # Higher threshold for OCR artifacts
NER_BATCH_SIZE=24
ENABLE_CONTEXTUAL_CHUNKS=false

# If OPT/DAT load files exist and are well-formed:
$COMPOSE exec api python scripts/import_dataset.py concordance_dat \
  --file /mnt/epstein/ds9/VOL00009.DAT \
  --content-dir /local-staging/ds9-batch/ \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --disable-hnsw --resume

# If OPT/DAT are missing or corrupt, fall back to PDF directory import:
$COMPOSE exec api python scripts/import_pdf_directory.py \
  --dir /local-staging/ds9-batch/ \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --dataset-name "DOJ EFTA DS 9 - Emails" \
  --disable-hnsw --resume
```

### GATE 5: DS 9 Progress Check (every 12 hours)

- [ ] Ingestion rate sustainable
- [ ] NER workers draining
- [ ] Error rate < 1%
- [ ] Expected doc count: ~530K PDFs (minus ~10GB video gap)

---

## Phase 6: DS 11 — Financial/Flight Records (~25.5GB, ~10 hours)

Can overlap with DS 9's NER tail.

```bash
# Download DS 11
aria2c --seed-time=0 "/tmp/Epstein-Files/Torrent Files/DataSet 11.zip.torrent" -d /data/ds11/
# Extract if zipped
cd /data/ds11 && unzip "DataSet 11.zip" -d extracted/
gsutil -m rsync -r /data/ds11/extracted/ gs://nexus-epstein-data/ds11/

# Ingest — relationship extraction ON (high investigation value)
ENABLE_RELATIONSHIP_EXTRACTION=true
ENABLE_CONTEXTUAL_CHUNKS=true
QUALITY_SCORE_THRESHOLD=0.2

$COMPOSE exec api python scripts/import_pdf_directory.py \
  --dir /mnt/epstein/ds11 \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --dataset-name "DOJ EFTA DS 11 - Financial/Flight" \
  --disable-hnsw --resume
```

---

## Phase 7: Post-Ingestion Passes (~6-8 hours)

1. **HNSW Rebuild** — verify active after import scripts auto-trigger
2. **Email Threading** — limited for DS 9 (PDF-only, no headers). Check OPT/DAT for thread metadata
3. **Entity Resolution Agent** — critical for merging "J. Epstein" / "Jeffrey Epstein" / "JE"
4. **GraphRAG Community Summaries** — Louvain → LLM summaries
5. **Graph Centrality** — PageRank to surface key entities
6. **Hot Doc Scoring** — overnight batch
7. **Tear Down NER Workers**: `bash scripts/infra/delete_ner_workers.sh`
8. **Delete Downloader VM**: `gcloud compute instances delete nexus-downloader --zone=us-west1-a --quiet`
   - GCS bucket is PERMANENT (~$4.50/mo, or ~$2.50/mo on Nearline after ingestion)

---

## Feature Flags Per Dataset

| Flag | DS 1-7+12 | DS 8 | DS 9 | DS 11 | Post |
|------|-----------|------|------|-------|------|
| DEFER_NER_TO_QUEUE | true | true | true | true | false |
| ENABLE_CHUNK_QUALITY_SCORING | true | true | true | true | — |
| QUALITY_SCORE_THRESHOLD | 0.2 | 0.2 | **0.5** | 0.2 | — |
| NER_BATCH_SIZE | 8 | 8 | **24** | 8 | — |
| ENABLE_CONTEXTUAL_CHUNKS | **true** | false | false | **true** | — |
| ENABLE_RELATIONSHIP_EXTRACTION | false | false | false | **true** | — |
| ENABLE_SPARSE_EMBEDDINGS | true | true | true | true | — |
| ENABLE_NEAR_DUPLICATE_DETECTION | true | true | true | true | — |

---

## Timeline

| Phase | Duration | Overlap | Cumulative |
|-------|----------|---------|------------|
| 0: Download DS 1-7+12 & validate | ~4 hours | — | 4h |
| 2: DS 1-7+12 ingestion (4.3GB) | ~3 hours | Download DS 8/9/11 in parallel | ~7h |
| 3: DS 8 ingestion (10.7GB) | ~6 hours | — | ~13h |
| 4: Spin up NER workers | ~1 hour | — | ~14h |
| 5: DS 9 ingestion (180GB) | ~50-55 hours | — | ~66h |
| 6: DS 11 ingestion (25.5GB) | ~10 hours | Overlaps DS 9 NER tail | ~69h |
| 7: Post-ingestion + teardown | ~6-8 hours | — | ~76h |
| **Total wall clock** | | | **~3.2 days** |

## Cost Estimate

| Item | Cost |
|------|------|
| nexus-gpu VM (3.2 days @ $0.26/hr spot) | ~$20 |
| Downloader VM (e2-medium, ~3 days) | ~$1 |
| 6x NER spot VMs (55 hrs x $0.048/hr x 6) | ~$16 |
| GCS permanent bucket (222GB Standard, first month) | ~$4.50 |
| Gemini API (contextual chunks DS 1-7+11, relationship extraction DS 11) | ~$3 |
| **Total ingestion run** | **~$45** |
| **Ongoing GCS storage** | **~$4.50/mo** (or ~$2.50/mo on Nearline) |

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| DS 9 format surprise | Confirmed: Concordance production with OPT/DAT + PDFs. ConcordanceDATAdapter handles it. |
| DS 9 OCR artifacts | QUALITY_SCORE_THRESHOLD=0.5 filters garbled chunks |
| DS 9 over GCS FUSE = latency | Stage 20K PDFs at a time to local SSD, ingest, delete, repeat |
| DS 9 incomplete (10GB video gap) | Documented. Validation checklist accounts for missing files. |
| DS 9 threading limited | PDFs lack RFC 5322 headers. Check OPT/DAT for threading metadata. |
| Spot VM preemption | `--resume` + content hash dedup + Celery retry |
| NER queue unbounded | Monitor every 12h; 6 NER workers scale drain 6x |
| Docling crashes on corrupt PDFs | Celery retry 3x, skip on final failure |
| Budget overrun | Validation gates; NER workers only after Phase 3 |

## Verification (Final)

1. `SELECT count(*) FROM documents WHERE matter_id = '...-0002'` — expect 100K+ additional docs
2. `SELECT count(*) FROM documents WHERE entity_count > 0 AND matter_id = '...-0002'` — NER >95%
3. Neo4j entity distribution and relationship types
4. Sample queries: "Lolita Express manifest", "DOJ plea agreement", "Deutsche Bank transactions"
5. Frontend: entity graph clusters, hot docs panel, DS 9 docs retrievable
6. GraphRAG community summaries (Palm Beach network, financiers, etc.)
