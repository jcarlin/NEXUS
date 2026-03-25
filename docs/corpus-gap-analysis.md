# Complete Epstein Corpus Gap Analysis

## Overview

The DOJ's Epstein Library (justice.gov/epstein) contains **3.5 million responsive pages** across multiple disclosure categories. Our EFTA ingestion (DS 1-12) covers the bulk, but the full publicly available corpus includes additional sections.

## Full Corpus Map

| Category | Est. Pages | Est. Size | Status |
|----------|-----------|-----------|--------|
| **A. DS 1-12 (excl DS 10)** | ~3M | ~128 GB | **In progress** |
| **B. DOJ Court Records** | ~50K | ~5-10 GB | Missing |
| **C. DOJ FOIA (CBP, FBI, BOP, FL)** | ~20K | ~2-5 GB | Missing |
| **D. Prior DOJ Disclosures** | ~5K | ~1 GB | Missing |
| **E. House Oversight Committee** | ~53K | ~5-10 GB | Missing |
| **F. Supplementary sources** | ~14K | ~1 GB | Planned |
| **Total** | **~3.14M** | **~142-155 GB** | |

## A. DOJ Disclosures (DS 1-12) — IN PROGRESS

The bulk release under H.R. 4405. See `docs/epstein-efta-ingestion-plan.md`.

## B. DOJ Court Records — MISSING

- **URL**: justice.gov/epstein/court-records
- **Content**: 40+ consolidated court cases (FL state, federal, Maxwell, Epstein death)
- **Format**: PDFs with DOJ redaction markings
- **Overlap**: Partial with CourtListener, but DOJ's consolidated/redacted versions
- **Script needed**: `scripts/download_doj_epstein_library.py`

## C. DOJ FOIA Records — MISSING

- **URL**: justice.gov/epstein/foia
- **Agencies**: CBP (travel records), FBI (investigation), BOP (prison), Florida (state)
- **Overlap**: FBI section may partially overlap with vault.fbi.gov release
- **Script needed**: Same as above (multi-section crawler)

## D. Prior DOJ Disclosures — MISSING

- AG Bondi's First Phase Declassified Files (Feb 2026)
- Maxwell Proffer (cooperation documents)
- Memoranda and Correspondence
- BOP Video Footage (skip — video)
- **Script needed**: Same as above

## E. House Oversight Committee — MISSING (SEPARATE CORPUS)

- **Source**: oversight.house.gov → Google Drive / Dropbox
- Sept 2025: 33,295 pages from DOJ (may overlap with DS 1-12)
- Nov 2025: 20,000+ pages from Epstein Estate (**unique** — bank accounts, personal records)
- **Script needed**: `scripts/download_house_oversight.py`
- **Highest value unique addition**: Estate documents not in any DOJ release

## F. Supplementary Sources — PLANNED

See `docs/supplementary-corpus-plan.md`.

## Implementation Priority

1. **House Oversight Estate docs** (20K pages, unique, high value)
2. **DOJ Court Records** (40+ cases, consolidated versions)
3. **DOJ FOIA** (CBP travel records especially valuable)
4. **Prior DOJ Disclosures** (Maxwell Proffer, declassified files)
5. **Supplementary sources** (CourtListener, FBI Vault, etc.)

## Scripts Needed

| Script | Purpose | Effort |
|--------|---------|--------|
| `scripts/download_doj_epstein_library.py` | Crawl DOJ court records + FOIA + prior disclosures | ~2 hours |
| `scripts/download_house_oversight.py` | Download Google Drive/Dropbox folders | ~1.5 hours |
| `scripts/download_documentcloud.py` | DocumentCloud API | ~1 hour |
| `scripts/download_fl_state_attorney.py` | FL State Attorney records | ~30 min |
| `scripts/import_entity_graph.py` | Pre-built entity graph to Neo4j | ~1 hour |
| `scripts/import_efta_index.py` | Bates index cross-reference | ~30 min |
| **Total** | | **~6.5 hours** |

## Note on DOJ WAF

The DOJ site (justice.gov) is behind Akamai WAF which blocks automated scraping. The download script may need:
- Proper User-Agent headers
- Browser-based scraping (Playwright)
- Rate limiting / delays
- Running from the downloader VM (GCP IP may be less blocked than residential)
