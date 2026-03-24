# DOJ EFTA Full Corpus Ingestion Plan

## Context

Ingest ~222GB of DOJ EFTA datasets (DS 1-7+12, DS 8, DS 9, DS 11) into NEXUS on the T4 GPU VM (`nexus-gpu`, n1-standard-8, 30GB RAM, 200GB SSD, us-west1-a). Excludes DS 10 (images/videos). Goal: maximize investigation accuracy, keep extra GCP spend under ~$50, complete in 3-4 days. Every phase has a validation gate — no money committed until the previous phase proves out.

**Current state**: 18,681 docs / 259,584 chunks already ingested (Tiers 1-2 from `docs/epstein-ingestion-gpu.md`). The DOJ EFTA datasets are the "Tier 4: GATE" items.

**Source**: DOJ EFTA torrent (`magnet:?xt=urn:btih:f5cbe5026b1f86617c520d0a9cd610d6254cbe85`, ~222GB). Also on Internet Archive. Needs fresh download.

**Storage**: All raw data lives permanently in GCS (`gs://nexus-epstein-data/`), not on the VM. The VM reads via gcsfuse mount. GCS Standard class in us-west1 (~$0.02/GB/mo = ~$4.50/mo for 222GB). Data persists for future re-ingestion, re-embedding, or new pipeline runs.

---

## Phase 0: Sample Download & Format Validation (~3-4 hours, ~$2)

**Goal**: Download a small sample from each dataset, inspect file formats, run 100-doc pipeline test. Catch format surprises before committing 222GB and $50.

### 0.1 — Staging Infrastructure

```bash
# Create permanent GCS bucket (us-west1, same region as VM — free intra-region egress)
# Standard storage class — data stays here permanently for future use
gsutil mb -l us-west1 -c standard gs://nexus-epstein-data/

# On local machine: start torrent, let it download just enough to inspect
# OR: spin up a cheap e2-medium download VM with 500GB pd-standard
gcloud compute instances create nexus-downloader \
  --machine-type=e2-medium --zone=us-west1-a \
  --boot-disk-size=500GB --boot-disk-type=pd-standard \
  --image-family=debian-12 --image-project=debian-cloud \
  --preemptible
# Cost: ~$0.01/hr + $0.02/GB/mo disk = ~$1/day
```

### 0.2 — Download & Inspect Sample

On the downloader VM (or local machine):
```bash
# Install aria2 or transmission-cli for torrent
sudo apt-get install -y aria2

# Download torrent — select only first few files from each DS
# aria2c supports file selection from torrent
aria2c --select-file=<DS1_files>,<DS8_files>,<DS9_files>,<DS11_files> \
  "magnet:?xt=urn:btih:f5cbe5026b1f86617c520d0a9cd610d6254cbe85" \
  --max-overall-download-limit=50M --seed-time=0

# Inspect file types
find ds1/ -type f | head -20           # What extensions?
file ds9/* | head -20                  # PDF? EML? MSG? TXT?
find ds11/ -type f -name "*.xlsx" -o -name "*.csv" | head  # Structured?
ls -la ds9/ | head -20                 # File sizes — many small or few large?
```

**Key questions to answer**:
- DS 9: PDF scans? .eml files? .txt? This determines adapter choice.
- DS 11: Structured data (CSV/XLSX) or scanned PDFs?
- DS 1-7: Text-native PDFs or scanned?
- File naming conventions (for dataset/source tracking)

### 0.3 — Upload Sample to GCS & Mount on VM

```bash
# Upload ~1GB sample from each DS to GCS
gsutil -m cp -r ds1-sample/ gs://nexus-epstein-data/sample/ds1/
gsutil -m cp -r ds8-sample/ gs://nexus-epstein-data/sample/ds8/
gsutil -m cp -r ds9-sample/ gs://nexus-epstein-data/sample/ds9/
gsutil -m cp -r ds11-sample/ gs://nexus-epstein-data/sample/ds11/

# On nexus-gpu VM: mount GCS
sudo apt-get install -y gcsfuse
sudo mkdir -p /mnt/epstein
gcsfuse --implicit-dirs nexus-epstein-data /mnt/epstein
```

### 0.4 — Pipeline Smoke Test (100 docs from each DS)

```bash
COMPOSE='sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.gpu.yml'

# Test DS 1-7 sample (PDF pipeline)
$COMPOSE exec api python scripts/import_pdf_directory.py \
  --dir /mnt/epstein/sample/ds1 \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --dataset-name "DOJ EFTA Sample DS1" \
  --limit 100 --disable-hnsw

# Test DS 9 sample (adapter TBD based on format inspection)
# If PDFs:
$COMPOSE exec api python scripts/import_pdf_directory.py \
  --dir /mnt/epstein/sample/ds9 \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --dataset-name "DOJ EFTA Sample DS9" \
  --limit 100 --disable-hnsw

# If .eml files: may need new adapter (see Code Changes section)
```

### GATE 0: Validation Checklist

- [ ] File formats identified for all 4 dataset groups
- [ ] 100 docs from each DS ingested successfully
- [ ] Qdrant chunks created with embeddings (spot-check vector dimensions = 1024)
- [ ] NER entities extracted and visible in Neo4j
- [ ] No Docling crashes, OOM, or disk issues
- [ ] Embedding throughput: >100 chunks/sec on Infinity GPU
- [ ] Sample query returns results from sample docs
- [ ] GCS FUSE mount stable (no hangs, acceptable read speed)

**If Gate 0 fails**: Fix issues on the 100-doc sample before downloading the full 222GB. Total cost so far: ~$2 (downloader VM + GCS).

**Decision point**: Based on DS 9/DS 11 format inspection, determine:
- Which adapter to use for each dataset
- Whether FlightManifestAdapter is needed for DS 11
- Whether a new .eml adapter is needed for DS 9

---

## Phase 1: Code Changes (~4-6 hours)

### 1.1 — NER_BATCH_SIZE config (15 min)

**Files**: `app/config.py`, `app/ingestion/tasks.py`

- Add `ner_batch_size: int = 8` to `ProcessingConfig` in `app/config.py`
- Add `NER_BATCH_SIZE=8` to `.env.example` and `.env.gpu.example`
- Wire into `_stage_extract()` (line ~981 in tasks.py): pass `batch_size=settings.ner_batch_size` to `extract_batch()`
- Wire into `extract_entities_for_job()` deferred NER task (line ~2324)
- For DS 9 short emails: set `NER_BATCH_SIZE=24` at runtime

### 1.2 — QUALITY_SCORE_THRESHOLD config (15 min)

**Files**: `app/config.py`, `app/ingestion/contextualizer.py`

- Add `quality_score_threshold: float = 0.2` to `ProcessingConfig`
- Replace hardcoded `0.2` in contextualizer with `settings.quality_score_threshold`
- Add `QUALITY_SCORE_THRESHOLD=0.2` to `.env.example`
- For DS 9: set `QUALITY_SCORE_THRESHOLD=0.4` to filter email boilerplate

### 1.3 — NER Worker VM Infrastructure (~1.5 hours)

**New files**: `scripts/ner_worker_startup.sh`, `scripts/infra/create_ner_workers.sh`, `scripts/infra/delete_ner_workers.sh`

`scripts/ner_worker_startup.sh`:
```bash
#!/bin/bash
# Startup script for NER worker spot VMs
# Pulls NEXUS Docker image, starts Celery worker on ner queue

set -euo pipefail

# Install Docker
curl -fsSL https://get.docker.com | sh

# Pull pre-built image from GCR (or build from source)
# Option A: GCR image (requires `docker push` from main VM first)
docker pull gcr.io/vault-ai-487703/nexus-api:latest

# Option B: Build from source (slower but no GCR setup needed)
# git clone ... && docker build -t nexus-api .

# Start NER worker
docker run -d --restart=unless-stopped \
  --name nexus-ner-worker \
  -e POSTGRES_URL_SYNC=postgresql://nexus:${PG_PASS}@${MAIN_VM_IP}:5432/nexus \
  -e REDIS_URL=redis://${MAIN_VM_IP}:6379/0 \
  -e CELERY_BROKER_URL=amqp://nexus:${RABBITMQ_PASS}@${MAIN_VM_IP}:5672/nexus \
  -e QDRANT_URL=http://${MAIN_VM_IP}:6333 \
  -e NEO4J_URI=bolt://${MAIN_VM_IP}:7687 \
  -e NEO4J_USER=neo4j \
  -e NEO4J_PASSWORD=${NEO4J_PASS} \
  gcr.io/vault-ai-487703/nexus-api:latest \
  celery -A workers.celery_app worker -l info -Q ner -c 4 -P prefork --max-tasks-per-child=50
```

`scripts/infra/create_ner_workers.sh`:
```bash
#!/bin/bash
# Create 6 spot NER worker VMs
NUM_WORKERS=${1:-6}
# ... instance template + create commands
```

`scripts/infra/delete_ner_workers.sh`:
```bash
#!/bin/bash
# Tear down all NER workers
gcloud compute instances delete nexus-ner-{1,2,3,4,5,6} --zone=us-west1-a --quiet
```

**Prerequisites**:
- Push Docker image to GCR: `docker tag nexus-api gcr.io/vault-ai-487703/nexus-api && docker push`
- Open firewall rules for RabbitMQ (5672), PostgreSQL (5432), Redis (6379), Qdrant (6333), Neo4j (7687) from internal VPC only
- Credentials passed via instance metadata or startup script env vars

### 1.4 — DS-Specific Adapters (TBD after Phase 0)

**Conditional on Phase 0 format inspection**:

- If DS 9 is .eml files → new `EMLFileAdapter` in `app/ingestion/adapters/eml_files.py` (~2 hours)
  - Parse .eml with Python `email` stdlib
  - Extract headers (from, to, cc, subject, date), body (plain text or HTML→text)
  - Yield `ImportDocument(doc_type="email", email_headers={...})`
  - Register in `ADAPTER_REGISTRY`

- If DS 11 has CSV/XLSX flight records → `FlightManifestAdapter` in `app/ingestion/adapters/flight_manifest.py` (~2-3 hours)
  - Each table row → self-contained chunk with header context prefix
  - Metadata: `record_type=flight_manifest`, date, origin, destination
  - Register in `ADAPTER_REGISTRY`

- If both are just PDFs → no new adapters needed, use `import_pdf_directory.py`

### 1.5 — Tests

- Unit test for NER_BATCH_SIZE config wiring
- Unit test for QUALITY_SCORE_THRESHOLD config wiring
- Unit test for any new adapter (EMLFileAdapter / FlightManifestAdapter)
- Integration test: 10-doc import with deferred NER queue (mock Celery)

---

## Phase 2: Full Download & DS 1-7+12 Ingestion (~3 hours ingest, download overlaps)

### 2.1 — Full Torrent Download

On the downloader VM (already running from Phase 0):
```bash
# Download full torrent, excluding DS 10 (images/videos)
aria2c --select-file=<all-except-DS10> \
  "magnet:?xt=urn:btih:f5cbe5026b1f86617c520d0a9cd610d6254cbe85" \
  --seed-time=0

# Upload to GCS as files complete (can overlap with ingestion)
gsutil -m rsync -r ds1-7/ gs://nexus-epstein-data/ds1-7/
gsutil -m rsync -r ds8/    gs://nexus-epstein-data/ds8/
gsutil -m rsync -r ds9/    gs://nexus-epstein-data/ds9/
gsutil -m rsync -r ds11/   gs://nexus-epstein-data/ds11/
gsutil -m rsync -r ds12/   gs://nexus-epstein-data/ds12/
```

### 2.2 — DS 1-7+12 Ingestion (~4.3GB, ~3 hours)

Highest signal density. Contextual chunks enabled (foundational docs).

```bash
# Set env vars on VM
ENABLE_CONTEXTUAL_CHUNKS=true
ENABLE_CHUNK_QUALITY_SCORING=true
DEFER_NER_TO_QUEUE=true

$COMPOSE exec api python scripts/import_pdf_directory.py \
  --dir /mnt/epstein/ds1-7 \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --dataset-name "DOJ EFTA DS 1-7" \
  --disable-hnsw --resume

$COMPOSE exec api python scripts/import_pdf_directory.py \
  --dir /mnt/epstein/ds12 \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --dataset-name "DOJ EFTA DS 12" \
  --disable-hnsw --resume
```

### GATE 2: Validation

- [ ] Doc count matches expected for DS 1-7+12
- [ ] Contextual chunk prefixes populated (spot-check in Qdrant payload)
- [ ] Quality scores computed (check `quality_score` in chunk metadata)
- [ ] NER queue draining at expected rate
- [ ] Sample query: "Jeffrey Epstein financial transactions" returns DS 1-7 docs
- [ ] No errors in Celery worker logs

---

## Phase 3: DS 8 Ingestion (~10.7GB, ~6 hours)

Validates OCR at medium scale. Docling is the bottleneck.

```bash
# Disable contextual chunks (not worth the LLM cost for DS 8 volume)
ENABLE_CONTEXTUAL_CHUNKS=false

$COMPOSE exec api python scripts/import_pdf_directory.py \
  --dir /mnt/epstein/ds8 \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --dataset-name "DOJ EFTA DS 8" \
  --disable-hnsw --resume
```

### GATE 3: Validation

- [ ] All formats parsed (no Docling crashes on exotic PDFs)
- [ ] OCR quality acceptable (spot-check 10 random scanned docs)
- [ ] NER backlog size manageable
- [ ] Disk usage healthy (GCS FUSE should prevent local disk pressure)

---

## Phase 4: Spin Up NER Workers (~$27)

**Only after Gates 2-3 pass and NER backlog is confirmed large.**

```bash
# Check NER queue depth
$COMPOSE exec rabbitmq rabbitmqctl list_queues name messages consumers
```

If NER backlog > 50K chunks:

### 4.1 — Push Docker Image to GCR

```bash
# On nexus-gpu VM
sudo docker tag nexus-api:latest gcr.io/vault-ai-487703/nexus-api:latest
sudo docker push gcr.io/vault-ai-487703/nexus-api:latest
```

### 4.2 — Open Internal Firewall Rules

```bash
gcloud compute firewall-rules create nexus-internal-services \
  --allow=tcp:5432,tcp:5672,tcp:6333,tcp:6379,tcp:7687 \
  --source-tags=nexus-internal \
  --target-tags=nexus-internal \
  --network=default
```

### 4.3 — Create NER Workers

```bash
bash scripts/infra/create_ner_workers.sh 6
```

### GATE 4: NER Worker Validation

- [ ] All 6 workers connected (RabbitMQ shows 6+1 consumers on `ner` queue)
- [ ] NER drain rate ~6x faster than single-worker baseline
- [ ] No task errors in first 30 minutes
- [ ] Spot preemption rate acceptable (check every few hours)

**If Gate 4 fails**: `bash scripts/infra/delete_ner_workers.sh` — fall back to on-VM NER.

---

## Phase 5: DS 9 — Emails (~180GB, ~50-55 hours)

The bulk of the work. Only start after all gates pass.

```bash
# Aggressive email boilerplate filtering
QUALITY_SCORE_THRESHOLD=0.4
NER_BATCH_SIZE=24
ENABLE_CONTEXTUAL_CHUNKS=false  # Not worth LLM cost at this volume

# Adapter depends on Phase 0 format inspection:
# If PDFs:
$COMPOSE exec api python scripts/import_pdf_directory.py \
  --dir /mnt/epstein/ds9 \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --dataset-name "DOJ EFTA DS 9 - Emails/Correspondence" \
  --disable-hnsw --resume

# If .eml files (and EMLFileAdapter was built):
$COMPOSE exec api python scripts/import_dataset.py eml_directory \
  --data-dir /mnt/epstein/ds9 \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --disable-hnsw --resume
```

**Monitoring cadence**: Check every 12 hours:
- `$COMPOSE exec rabbitmq rabbitmqctl list_queues name messages` — NER backlog
- `SELECT count(*) FROM documents WHERE matter_id = '...-0002'` — doc count
- `df -h` — disk usage (should be minimal with GCS FUSE)
- `$COMPOSE logs --tail=50 worker ner-worker` — error scan

### GATE 5: DS 9 Progress Check (at 25%, 50%, 75%)

- [ ] Ingestion rate sustainable (docs/hour not degrading)
- [ ] NER workers still connected and draining
- [ ] No disk pressure
- [ ] Error rate < 1%

---

## Phase 6: DS 11 — Flight Logs & Financial (~27.5GB, ~10 hours)

Can overlap with DS 9's NER tail. Highest investigation value per byte.

```bash
ENABLE_RELATIONSHIP_EXTRACTION=true  # Worth LLM cost here
ENABLE_CONTEXTUAL_CHUNKS=true        # Worth it for evidentiary docs
QUALITY_SCORE_THRESHOLD=0.2          # Default — don't filter structured data

# Adapter depends on Phase 0 format inspection:
$COMPOSE exec api python scripts/import_pdf_directory.py \
  --dir /mnt/epstein/ds11 \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --dataset-name "DOJ EFTA DS 11 - Financial/Flight" \
  --disable-hnsw --resume
```

---

## Phase 7: Post-Ingestion Passes (~6-8 hours)

Run after all datasets indexed. NER workers can still be draining while these run.

### 7.1 — HNSW Rebuild (auto-triggered, verify)
```bash
# Verify HNSW is active
$COMPOSE exec api python -c "
from qdrant_client import QdrantClient
c = QdrantClient('http://localhost:6333')
info = c.get_collection('nexus_text')
print(f'HNSW: {info.config.hnsw_config}')
print(f'Points: {info.points_count}')
"
```

### 7.2 — Email Threading (DS 9, batched)
Post-ingestion hooks auto-dispatch `ingestion.detect_inclusive_emails`. Verify it ran:
```bash
$COMPOSE logs worker | grep "email_threading"
```

### 7.3 — Entity Resolution Agent
```bash
# Run with looser thresholds for this corpus
$COMPOSE exec api python -c "
from app.entities.tasks import resolve_entities
resolve_entities.delay('00000000-0000-0000-0000-000000000002')
"
```

### 7.4 — GraphRAG Community Summaries
```bash
# Enable and trigger
ENABLE_GRAPHRAG_COMMUNITIES=true
# Dispatched by post-ingestion hooks, or trigger manually via admin API
```

### 7.5 — Graph Centrality (PageRank)
```bash
ENABLE_GRAPH_CENTRALITY=true
# Auto-runs on next entity query, or trigger via admin API
```

### 7.6 — Hot Doc Scoring (overnight batch)
```bash
ENABLE_HOT_DOC_DETECTION=true
# Dispatched by post-ingestion hooks
```

### 7.7 — Tear Down NER Workers
```bash
bash scripts/infra/delete_ner_workers.sh
# Also delete instance template and firewall rule
gcloud compute instance-templates delete nexus-ner-worker --quiet
gcloud compute firewall-rules delete nexus-internal-services --quiet
```

### 7.8 — Delete Downloader VM (GCS stays permanently)
```bash
gcloud compute instances delete nexus-downloader --zone=us-west1-a --quiet
# GCS bucket is PERMANENT — raw data stays for future re-ingestion/re-embedding
# Ongoing cost: ~$4.50/mo for 222GB Standard storage in us-west1
# To reduce cost later: gsutil rewrite -s nearline gs://nexus-epstein-data/** (~$2.50/mo)
```

---

## Feature Flags Per Dataset

| Flag | DS 1-7+12 | DS 8 | DS 9 | DS 11 | Post |
|------|-----------|------|------|-------|------|
| DEFER_NER_TO_QUEUE | true | true | true | true | false |
| ENABLE_CHUNK_QUALITY_SCORING | true | true | true | true | — |
| QUALITY_SCORE_THRESHOLD | 0.2 | 0.2 | **0.4** | 0.2 | — |
| NER_BATCH_SIZE | 8 | 8 | **24** | 8 | — |
| ENABLE_CONTEXTUAL_CHUNKS | **true** | false | false | **true** | — |
| ENABLE_RELATIONSHIP_EXTRACTION | false | false | false | **true** | — |
| ENABLE_SPARSE_EMBEDDINGS | true | true | true | true | — |
| ENABLE_NEAR_DUPLICATE_DETECTION | true | true | true | true | — |
| ENABLE_GRAPHRAG_COMMUNITIES | — | — | — | — | true |
| ENABLE_GRAPH_CENTRALITY | — | — | — | — | true |
| ENABLE_HOT_DOC_DETECTION | — | — | — | — | true |
| ENABLE_EMAIL_THREADING | — | — | — | — | true |

---

## Timeline

| Phase | Duration | Overlap | Cumulative |
|-------|----------|---------|------------|
| 0: Sample & validate | ~4 hours | — | 4h |
| 1: Code changes | ~4-6 hours | — | ~10h |
| 2: DS 1-7+12 (4.3GB) | ~3 hours | Download DS 8/9/11 in parallel | ~13h |
| 3: DS 8 (10.7GB) | ~6 hours | — | ~19h |
| 4: Spin up NER workers | ~1 hour | — | ~20h |
| 5: DS 9 (180GB) | ~50-55 hours | — | ~72h |
| 6: DS 11 (27.5GB) | ~10 hours | Overlaps DS 9 NER tail | ~75h |
| 7: Post-ingestion + teardown | ~6-8 hours | — | ~82h |
| **Total wall clock** | | | **~3.5 days** |

## Cost Estimate

| Item | Cost |
|------|------|
| nexus-gpu VM (3.5 days @ $0.26/hr spot) | ~$22 |
| Downloader VM (e2-medium, ~2 days) | ~$1 |
| 6x NER spot VMs (55 hrs x $0.048/hr x 6) | ~$16 |
| GCS permanent bucket (222GB Standard, first month) | ~$4.50 |
| Gemini API (contextual chunks DS 1-7+11, relationship extraction DS 11) | ~$3 |
| **Total ingestion run** | **~$47** |
| **Ongoing GCS storage** | **~$4.50/mo** (or ~$2.50/mo if moved to Nearline after ingestion) |

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Format surprise (DS 9/11 not what we expect) | Phase 0 sample inspection before committing |
| Spot VM preemption mid-ingestion | `--resume` flag, content hash dedup, Celery task auto-retry |
| DS 9 too large for disk | GCS FUSE mount — data never lands on local SSD |
| NER queue grows unbounded | Monitor every 12h; NER workers scale drain rate 6x |
| Docling crashes on corrupt PDFs | Celery retry 3x, skip on final failure, log doc ID for manual review |
| RabbitMQ memory pressure from large queue | Monitor; set `x-max-length` if needed; prefetch_count=1 on workers |
| Budget overrun | Validation gates at each phase; NER workers only spun up after Phase 3 |
| NER worker can't connect to services | Gate 4 validates connectivity before DS 9 starts |
| Gemini rate limits | Contextual chunks only for DS 1-7+11 (~32GB, well within rate limits) |
| Download stalls/corruption | aria2c supports resume; verify file counts + sizes before ingesting |
| GCS cost creep | Standard class = ~$4.50/mo; switch to Nearline ($2.50/mo) after ingestion complete; set lifecycle policy to auto-transition |

## Code Changes Summary

| Change | Files | Effort |
|--------|-------|--------|
| NER_BATCH_SIZE config | `app/config.py`, `app/ingestion/tasks.py`, `.env.example` | 15 min |
| QUALITY_SCORE_THRESHOLD config | `app/config.py`, `app/ingestion/contextualizer.py`, `.env.example` | 15 min |
| NER worker startup script | `scripts/ner_worker_startup.sh` (new) | 30 min |
| NER worker create/delete scripts | `scripts/infra/create_ner_workers.sh`, `delete_ner_workers.sh` (new) | 30 min |
| GCR Docker image push | One-time manual step on VM | 15 min |
| Firewall rule for internal VPC | One-time gcloud command | 5 min |
| EMLFileAdapter (conditional) | `app/ingestion/adapters/eml_files.py` (new) | ~2 hours |
| FlightManifestAdapter (conditional) | `app/ingestion/adapters/flight_manifest.py` (new) | ~2-3 hours |
| Tests for above | `tests/test_ingestion/` | ~1 hour |
| **Total** | | **~4-6 hours** |

## Verification (Final)

After all phases complete:
1. `SELECT count(*) FROM documents WHERE matter_id = '...-0002'` — expect 100K+ additional docs
2. `SELECT count(*) FROM documents WHERE entity_count > 0 AND matter_id = '...-0002'` — NER coverage >95%
3. Neo4j: `MATCH (n) WHERE n.matter_id = '...-0002' RETURN labels(n)[0], count(n)` — entity distribution
4. Neo4j: `MATCH ()-[r]-() RETURN type(r), count(r)` — relationship types (CO_OCCURS, PARTICIPATED_IN)
5. Sample queries:
   - "Lolita Express passenger manifest"
   - "financial transactions between Epstein and Deutsche Bank"
   - "DOJ correspondence about plea agreement"
   - "flight logs Palm Beach to Little St. James"
6. Frontend: entity network graph shows new clusters, email threading for DS 9, hot docs panel populated
7. GraphRAG: community summaries visible (Palm Beach network, financiers, etc.)
