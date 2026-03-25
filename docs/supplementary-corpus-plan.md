# Supplementary Corpus Ingestion Plan (Post-EFTA)

## Context

After the DOJ EFTA ingestion completes (~128 GB, ~570K docs covering DS 1-9+11+12), there are ~1 GB of supplementary publicly available text sources that fill gaps in the corpus. These are court filings, FBI FOIA releases, and state investigation records that may overlap with the DOJ release but contain unique documents not in the EFTA production.

These can run while DS 9's NER queue drains, using idle worker capacity. No additional infrastructure needed — all scripts already exist.

## Sources

| # | Source | Size | Est. Docs | Script | Notes |
|---|--------|------|-----------|--------|-------|
| 1 | Giuffre v. Maxwell (CourtListener) | ~200 MB | ~500 filings | `scripts/download_courtlistener.py --docket-id 4355835` | Unsealed 2019/2024 court filings |
| 2 | US v. Maxwell (CourtListener) | ~100 MB | ~300 filings | `scripts/download_courtlistener.py --docket-id 17318376` | Criminal case filings |
| 3 | FBI FOIA Vault (22 parts) | ~100 MB | ~3K pages | `scripts/download_fbi_vault.py` | FBI's separate FOIA disclosure |
| 4 | FL Palm Beach State Attorney | ~200 MB | ~5K pages | New script or manual + `import_pdf_directory.py` | State investigation records |
| 5 | DocumentCloud 2019/2024 unsealing | ~300 MB | ~5K pages | New `scripts/download_documentcloud.py` | Court-ordered document releases |
| 6 | rhowardstone/Epstein-research-data | ~5 MB | 606 entities | New `scripts/import_entity_graph.py` | Pre-built entity graph (2,302 connections) |
| 7 | theelderemo/FULL_EPSTEIN_INDEX | 3.3 MB | Index CSV | New script | Bates number cross-reference metadata |
| **Total** | | **~1 GB** | **~14K docs** | | |

## Implementation

### Step 1: Court Filings (~300 MB, ~2 hours)

```bash
COMPOSE="sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.gpu.yml"

# Giuffre v. Maxwell
$COMPOSE exec api python scripts/download_courtlistener.py \
  --docket-id 4355835 --output-dir /tmp/courtlistener/giuffre

$COMPOSE exec api python scripts/import_pdf_directory.py \
  --dir /tmp/courtlistener/giuffre \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --disable-hnsw --resume

# US v. Maxwell
$COMPOSE exec api python scripts/download_courtlistener.py \
  --docket-id 17318376 --output-dir /tmp/courtlistener/us-v-maxwell

$COMPOSE exec api python scripts/import_pdf_directory.py \
  --dir /tmp/courtlistener/us-v-maxwell \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --disable-hnsw --resume
```

### Step 2: FBI FOIA Vault (~100 MB, ~4 hours including OCR)

```bash
$COMPOSE exec api python scripts/download_fbi_vault.py \
  --output-dir /tmp/fbi_vault

$COMPOSE exec api python scripts/import_pdf_directory.py \
  --dir /tmp/fbi_vault \
  --matter-id 00000000-0000-0000-0000-000000000002 \
  --disable-hnsw --resume
```

### Step 3: FL Palm Beach State Attorney (~200 MB, ~6 hours)

Scanned police/prosecution records (16 PDF collections). New download script or manual wget needed.

### Step 4: DocumentCloud Collections (~300 MB, ~4 hours)

New `scripts/download_documentcloud.py` to query DocumentCloud API for Epstein-related project collections.

### Step 5: Entity Graph Import (~5 MB, ~30 min)

New `scripts/import_entity_graph.py` to parse `rhowardstone/Epstein-research-data` and merge 606 entities + 2,302 connections into Neo4j.

### Step 6: EFTA Index Cross-Reference (~3 MB, ~15 min)

Load `theelderemo/FULL_EPSTEIN_INDEX` CSV to enrich document metadata in PostgreSQL.

## New Code Needed

| Script | Purpose | Effort |
|--------|---------|--------|
| `scripts/download_fl_state_attorney.py` | Download FL State Attorney PDFs | ~30 min |
| `scripts/download_documentcloud.py` | Query DocumentCloud API | ~1 hour |
| `scripts/import_entity_graph.py` | Import pre-built entity graph to Neo4j | ~1 hour |
| `scripts/import_efta_index.py` | Load Bates index CSV to PostgreSQL | ~30 min |
| **Total** | | **~3 hours** |

## Cost

Zero additional GCP cost. All downloads <1 GB, run on existing GPU VM.
