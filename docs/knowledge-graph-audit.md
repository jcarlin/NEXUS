# Knowledge Graph & Entity Pipeline Audit

**Date:** 2026-03-26
**Scope:** Full deep-dive maturity and bug audit of entity extraction, knowledge graph population, entity resolution, and graph utilization across the NEXUS platform. Live data analysis performed against the GCP GPU VM (`nexus-gpu` / `34.169.203.200`).

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Live Data Assessment](#live-data-assessment)
3. [Root Cause Analysis](#root-cause-analysis)
4. [Entity-to-Chunk Data Model Gap](#entity-to-chunk-data-model-gap)
5. [Graph Utilization in Query Pipeline](#graph-utilization-in-query-pipeline)
6. [Feature Flag State (GCP VM)](#feature-flag-state-gcp-vm)
7. [GraphRAG and Alternative Framework Assessment](#graphrag-and-alternative-framework-assessment)
8. [Maturity Scorecard](#maturity-scorecard)
9. [Remediation Plan](#remediation-plan)
10. [Operational Concerns](#operational-concerns)

---

## Executive Summary

The NEXUS knowledge graph has **31,990 entities** across a corpus of **45,374 documents**. Entity quality is significantly degraded by three root causes: (1) OCR artifacts flowing uncleaned into entity names, (2) the entity resolution agent running per-document but being ineffective at scale, and (3) missing pre-extraction normalization. The graph is closer to a **noisy entity index** than a mature knowledge graph.

**Key numbers:**

| Metric | Value | Assessment |
|--------|-------|------------|
| Total entities | 31,990 | ~10x higher than expected for this corpus |
| Single-mention entities | 23,696 (74%) | Massive noise floor |
| Entities with newlines in name | 155 | OCR line-break artifacts |
| Entities with hyphenation artifacts | 97+ | OCR word-break artifacts |
| Entities 51+ chars (garbage) | 248 | URL slugs, sentence fragments |
| Entities 1-2 chars (noise) | 456 | State abbreviations + garbage |
| ALIAS_OF relationships | 0 | Resolution agent not linking aliases |
| Entities with aliases property | 3,565 (11%) | Some merging happened, but not via graph edges |
| CO_OCCURS edges | 1,272,163 | 98.6% weight=1 — never queried in pipeline |
| Resolution agent runs | 63 node actions | Running but clearly insufficient |

**Estimated true entity count** for a well-resolved graph of this corpus: **2,000-3,500** unique entities. Current state represents roughly **10x entity inflation**.

---

## Live Data Assessment

All queries run against the live Neo4j and PostgreSQL instances on `nexus-gpu`.

### Entity Count by Type

| Type | Count |
|------|-------|
| person | 11,130 |
| organization | 8,990 |
| location | 3,259 |
| date | 3,100 |
| monetary_amount | 1,696 |
| case_number | 944 |
| address | 792 |
| vehicle | 753 |
| court | 575 |
| phone_number | 400 |
| email_address | 224 |
| flight_number | 126 |

### Entity Mention Distribution

| Bucket | Count | % |
|--------|-------|---|
| Single mention | 23,696 | 74% |
| 2-5 mentions | 6,757 | 21% |
| 6-20 mentions | 1,279 | 4% |
| 21-100 mentions | 283 | 0.9% |
| 100+ mentions | 24 | 0.08% |

74% of all entities appear only once in the entire corpus. The high-signal core is ~307 entities with 21+ mentions.

### Name Length Distribution

| Bucket | Count |
|--------|-------|
| 6-15 chars | 16,690 |
| 16-30 chars | 9,881 |
| 3-5 chars | 3,108 |
| 31-50 chars | 1,607 |
| 1-2 chars | 456 |
| 51+ chars | 248 |

### Entities Per Matter

| Matter | Count |
|--------|-------|
| EFTA corpus (`...0002`) | 31,851 |
| Demo/seed (`...0001`) | 139 |

### CO_OCCURS Weight Distribution

| Weight | Count | % |
|--------|-------|---|
| 1 | 1,253,261 | 98.6% |
| 2-5 | 17,752 | 1.4% |
| 6-20 | 509 | 0.04% |
| 21-100 | 2 | <0.01% |

98.6% of co-occurrence edges represent a single shared document. Only 511 edges have weight > 5.

### Relationship Counts

| Relationship | Count |
|-------------|-------|
| CO_OCCURS | 1,272,163 |
| HAS_CHUNK | 304,680 |
| MENTIONED_IN | 69,312 |
| PART_OF | 26,005 |
| SOURCED_FROM | 9 |
| SENT | 5 |
| SENT_TO | 5 |
| CC | 2 |

### Neo4j vs PostgreSQL Document Count Mismatch

- **Neo4j Documents:** 47,428
- **PostgreSQL documents:** 45,374
- **Discrepancy:** 2,054 stale Document nodes in Neo4j (likely from failed re-ingestions or deletions not propagated)

### Ingestion Job Status

| Status | Count |
|--------|-------|
| complete | 70,118 |
| pending | 12,549 |
| failed | 201 |
| processing | 2 |

### Top 30 Entities by Mention Count

| Entity | Type | Mentions | Assessment |
|--------|------|----------|------------|
| J [mailto:jeevacation@gmail.com] | email_address | 1,011 | Garbage — mailto prefix in name |
| Trumps | person | 889 | Plural form — should merge with "Trump" |
| Jeff N. Epstein | person | 738 | Non-canonical form |
| Jeffrey Edward Epstein | person | 572 | Full legal name |
| $15.26 million | monetary_amount | 300 | Legitimate |
| Ep- stein | person | 263 | **OCR hyphenation artifact** |
| Donald Trump Jr. | person | 228 | Legitimate |
| New - York | location | 206 | **OCR hyphenation artifact** |
| Jeffrey Lisa | person | 189 | Garbage — OCR merge of two names |
| CLINT \nON | person | 166 | **OCR newline artifact** |
| addressee(s) | person | 138 | Garbage — boilerplate text |
| Today | date | 138 | Low-value relative date |
| 3,680,000.00 0.45 | monetary_amount | 134 | Garbage — trailing noise |
| shes | person | 125 | Garbage — pronoun leak |
| jeffrey E. | person | 124 | Truncated name |
| Bill CLinton | person | 121 | OCR case artifact |
| Money | monetary_amount | 120 | Garbage — word, not amount |
| People | person | 103 | Garbage — generic noun |
| Michael Wolff iis | person | 100 | OCR trailing noise |

### "Jeffrey Epstein" Name Variants (Sample)

The canonical entity "Jeffrey Epstein" appears in **15+ distinct variants**:

| Variant | Type | Mentions | Issue |
|---------|------|----------|-------|
| Jeff N. Epstein | person | 738 | Non-canonical form |
| Jeffrey Edward Epstein | person | 572 | Full legal name |
| Ep- stein | person | 263 | OCR hyphenation |
| jeffrey E. | person | 124 | Truncated |
| Edwards adv. Epstein | person | 23 | Court style |
| Jeffrrey Epstein | person | 15 | Source typo |
| Epstein, Jefferey | person | 12 | Last-first + misspelling |
| MR. JeFFery Epstein | person | 10 | OCR case artifact |
| effrey Epstein | person | 3 | OCR truncation |
| JBPPREY EPSTEIN | person | 1 | Severe OCR error |
| Jettery Epstein Ivernight | person | 1 | OCR garbage |

### "Maxwell" Name Variants (Sample)

| Variant | Type | Mentions | Issue |
|---------|------|----------|-------|
| Ghis- laine Maxwell | person | 77 | OCR hyphenation |
| Maxwell | person/org/location | 34/6/1 | Ambiguous, multi-typed |
| Miss Maxwell | person | 26 | Title variant |
| G Maxwell | person | 6 | Abbreviated |
| Maxvved Maxwell | person | 1 | OCR error |
| Ms Maxwell's closet By Microwave | person | 1 | Parsing failure |

### Garbage Entity Categories

| Category | Example | Count |
|----------|---------|-------|
| URL slugs as entities | `"steve-bannon-trump-tower-interview..."` → person | ~100+ |
| Twitter handles | `"@realDonaldTrump"` → person | ~20+ |
| Descriptive phrases | `"wealthy, Clinton-connected financier"` → person | ~50+ |
| Form control artifacts | `"DefaultOcxName13"` → person | ~10+ |
| Pure numbers mistyped | `"22"` → person, `"6178179452"` → location | 19+ |
| Relative dates | "Today", "Tomorrow", "Friday", "yesterday" | ~500+ |
| Generic nouns as monetary | "Money" (120), "Cash" (14), "rs" (13) | ~150+ |

---

## Root Cause Analysis

### Root Cause 1: OCR Artifacts Flow Directly into Entity Names

The EFTA corpus is scanned legal documents processed by Docling's OCR. OCR errors produce:

- **Line-break injection** (155 entities): `"CLINT \nON"` (166 mentions), `"Ghislaine\n\nBelow"`, `"Kim Jong\nUn"`, `"Melania\n\nTrump"` — OCR line breaks become literal `\n` in entity names
- **Hyphenation artifacts** (97+ entities): `"Ep- stein"` (263 mentions), `"Ghis- laine Maxwell"` (77), `"New - York"` (206), `"gov- ernment"` (93), `"millions of dol- lars"` (15) — OCR preserves page-margin hyphenation
- **Garbled OCR**: `"JBPPREY EPSTEIN"`, `"PaWeRhiRsiTEY ABI evEaehaGBy Mpyelret BD Sito"`, `"Maxvved Maxwell"` — character misrecognition
- **Trailing noise**: `"November 14, 20051"`, `"Michael Wolff iis"`, `"3,680,000.00 0.45"` — OCR picks up adjacent characters

**The extractor's `_is_garbage_entity()` filter (commit `1cb7b2f`) handles pronouns/stopwords but does NOT:**
- Strip newlines from entity names
- Rejoin hyphenation at line breaks
- Detect garbled text patterns
- Reject URL slugs or descriptive phrases

The whitespace normalization (`" ".join(text.split())`) uses Python's `str.split()` which splits on spaces/tabs but **does not split `\n` within a string literal stored in a JSON field** — newlines survive into Neo4j.

### Root Cause 2: Entity Resolution Is Structurally Ineffective at Scale

The resolution agent is triggered **per document** at ingestion completion (`app/ingestion/tasks.py:1345`):

```python
resolve_entities.delay(matter_id=ctx.matter_id)
```

Problems:
1. With 70,118 completed jobs, the agent was called **tens of thousands of times** redundantly
2. Only **63 node actions** recorded in agent audit log (March 23-25), meaning most runs either failed silently or found nothing
3. The NER worker is actively being **SIGKILL'd by OOM** — tasks pile up and fail

### Root Cause 3: First-Character Blocking Misses Key Duplicates

The fuzzy resolver (`app/entities/resolver.py:95-119`) uses first-character blocking: only compares names starting with the same or adjacent letters. This means:

| Pair | First Chars | Compared? | Result |
|------|-------------|-----------|--------|
| "Jeffrey Epstein" vs "Epstein, Jeffrey" | J vs E | **No** (4 apart) | Missed |
| "Ep- stein" vs "Jeffrey Epstein" | E vs J | **No** | Missed |
| "Ghis- laine Maxwell" vs "Miss Maxwell" | G vs M | **No** | Missed |
| "CLINT \nON" vs "Bill Clinton" | C vs B | Yes (adjacent) | `\n` tanks fuzzy score |

This is a fundamental limitation. First-char blocking is reasonable for well-formed names but fails on OCR-corrupted text and last-name-first formats.

### Root Cause 4: Low-Value Entity Types Extracted Without Discrimination

GLiNER's confidence threshold is **0.3** (quite low). Several entity types produce mostly noise:

- **`date`** (3,100 entities): "Today", "Tomorrow", "Friday", bare years — useless without temporal grounding
- **`monetary_amount`** (1,696): "Money", "Cash", "rs", garbage number strings
- **`vehicle`** (753): High noise-to-signal for legal documents
- **`flight_number`** (126): Useful for this corpus but many false positives

### Root Cause 5: Neo4j MERGE Key Is Case-Sensitive

The MERGE query uses exact name matching:

```cypher
MERGE (e:Entity {name: $name, type: $entity_type, matter_id: $matter_id})
```

"Jeffrey Epstein" and "JEFFREY EPSTEIN" create **separate nodes**. There is no case normalization on the MERGE key.

---

## Entity-to-Chunk Data Model Gap

This is a critical architectural gap. Here's the current data-level relationship:

```
Qdrant                          Neo4j                           PostgreSQL
─────────                       ─────────                       ──────────
Point (chunk)                   (:Chunk)                        documents
  payload:                        id (= chunk UUID)               id
    doc_id ─────────────────────  -[PART_OF]-> (:Document) ←──── id
    chunk_id                      qdrant_point_id (= Qdrant ID)
    page_number                   page_number
    chunk_index
    matter_id                   (:Entity)
    privilege_status              -[MENTIONED_IN]-> (:Document)
                                  r.page_number

                                (:Entity) -[CO_OCCURS]-> (:Entity)
                                  (per-document co-occurrence)
```

### The Missing Link: No Direct Entity → Chunk Relationship

Entities are linked to **Documents**, not to the specific chunks they were extracted from. To go from an entity to the text that mentioned it requires a 3-hop indirect join:

```
Entity -[MENTIONED_IN]-> Document <-[PART_OF]- Chunk -> qdrant_point_id
```

With page-level granularity only (a page can have 5-10 chunks).

### The Irony

During ingestion, entities are extracted **per-chunk** (`tasks.py:1010` — `extractor.extract_batch(chunk_texts)`), but the chunk association is **discarded** when indexing to Neo4j (`graph_service.py:272` — `MERGE (e)-[:MENTIONED_IN]->(d:Document)`). The chunk-entity mapping exists transiently in memory but is never persisted.

### What This Costs

- **No chunk-level entity retrieval** — can't query "find chunks that mention both Epstein AND Maxwell"
- **No chunk-level co-occurrence** — CO_OCCURS computed at document level (10+ pages) instead of chunk level (~100 tokens). A 10-page document with 20 entities produces 190 CO_OCCURS edges, most meaningless. Chunk-level would produce far fewer, far more meaningful edges.
- **No entity-aware vector retrieval** — can't rerank Qdrant results by entity graph distance
- **No precise citation** — entity mentions point to documents, not to the specific text

---

## Graph Utilization in Query Pipeline

### Features Actively Used in RAG

| Feature | How It's Used | Assessment |
|---------|---------------|------------|
| Entity canonicalization | Dedup via MENTIONED_IN + mention counting | Working, but degraded by duplication |
| 1-hop relationship lookup | `graph_query` tool — agent retrieves entity neighborhood | Working, shallow |
| Email communication graph | `communication_matrix` tool via SENT/SENT_TO/CC/BCC | Working, but only 12 email edges exist |
| Timeline construction | Entity mentions across documents with timestamps | Working |
| Privilege enforcement | Edges to privileged documents filtered at query time | Working |

### Features Implemented but Dormant

| Feature | Status | Why Dormant |
|---------|--------|-------------|
| CO_OCCURS (1.27M edges) | Created on every ingestion | **Never queried** — no tool or retrieval step uses them |
| Community detection (Louvain) | Computed, stored in PostgreSQL | Optional tool only, not auto-triggered |
| Graph centrality (GDS) | Feature flag enabled | Not used to reweight vector results |
| Multi-hop path finding | API endpoint exists | Not in default query flow — agent rarely chooses it |
| Entity-weighted reranking | Not implemented | Vector and graph retrieval are parallel, not integrated |

### Assessment

The graph is **supplementary context, not integral to relevance scoring**. The agentic pipeline prioritizes `vector_search` (fast, high recall) and uses `graph_query` as an optional enrichment tool the LLM may or may not invoke. This is a reasonable default, but means the graph investment is underutilized.

---

## Feature Flag State (GCP VM)

Environment variables on the running VM:

| Flag | State | Impact on Entities |
|------|-------|--------------------|
| `DEFER_NER_TO_QUEUE` | **ON** | NER on dedicated queue — but NER worker is OOM-crashing |
| `ENABLE_RELATIONSHIP_EXTRACTION` | **ON** | LLM extracts typed relationships — good, but noisy inputs |
| `ENABLE_COREFERENCE_RESOLUTION` | **OFF** | Placeholder node — would help with pronoun → entity linking |
| `ENABLE_GRAPH_CENTRALITY` | **ON** | Computes centrality metrics — unreliable on noisy graph |
| `ENABLE_EMAIL_THREADING` | **ON** | Builds SENT/SENT_TO/CC/BCC — but only 12 such edges |
| `ENABLE_NEAR_DUPLICATE_DETECTION` | **ON** | Document-level dedup, not entity-level |
| `ENABLE_HOT_DOC_DETECTION` | **ON** | Entity-independent |
| `ENABLE_TOPIC_CLUSTERING` | **ON** | Runs on noisy entity data |
| `ENABLE_VISUAL_EMBEDDINGS` | **OFF** | Not entity-related |
| `ENABLE_SPARSE_EMBEDDINGS` | **ON** | Not entity-related |

Runtime DB overrides (`feature_flag_overrides` table):

| Flag | Enabled |
|------|---------|
| enable_chunk_quality_scoring | true |
| enable_ocr_correction | true |
| enable_page_comms_matrix | false |
| enable_page_exports | false |
| enable_page_hot_docs | false |
| enable_page_result_set | false |
| enable_page_timeline | false |

---

## GraphRAG and Alternative Framework Assessment

### Why GraphRAG Would NOT Solve These Problems

| Problem | GraphRAG's Answer | Reality |
|---------|-------------------|---------|
| OCR artifacts in names | LLM extraction "understands" context | LLM gets the same garbled input — garbage in, garbage out |
| Entity deduplication | Exact name match within chunks | **Worse** than current fuzzy + embedding approach |
| Entity resolution at scale | Not addressed | No framework solves this well |
| Cost at 50K+ documents | LLM call per chunk | $150-400 (GPT-4o-mini) to $6,000+ (GPT-4o) |
| Incremental updates | Full re-indexing required | Regression from current incremental pipeline |
| Graph database | Parquet files via NetworkX | **Downgrade** from current Neo4j infrastructure |

### Framework Comparison

| Framework | Extraction | Entity Resolution | Graph Store | Cost (50K docs) | Incremental? |
|-----------|-----------|-------------------|-------------|-----------------|--------------|
| **Current NEXUS** | GLiNER (free, CPU) | Fuzzy + embedding | Neo4j | $0 | Yes |
| Microsoft GraphRAG | LLM per chunk | Exact name match | Parquet/NetworkX | $150-6,000 | No |
| LazyGraphRAG | NLP noun phrases | None | In-memory | ~$0 | No |
| LightRAG | LLM per chunk | Within-chunk only | Pluggable (Neo4j) | $100-4,000 | Yes |
| neo4j-graphrag-python | LLM per chunk | Fuzzy + spaCy + exact | Neo4j (native) | $100-4,000 | Partial |
| LlamaIndex PropertyGraph | LLM per chunk | DIY | Neo4j (native) | $100-4,000 | Yes |

### Research Validation

A July 2025 paper ("Towards Practical GraphRAG", arXiv 2507.03226) tested spaCy dependency parsing against LLM-based extraction and found **94% of LLM quality at zero marginal cost**. The hybrid retrieval (graph traversal + vector RRF) compensates for slightly lower extraction quality.

Microsoft's own follow-up (LazyGraphRAG) uses NLP noun-phrase extraction instead of LLM calls, costs 0.1% of GraphRAG, and **outperformed it on all 96 benchmarks**. This is an implicit admission that LLM-per-chunk extraction was the wrong approach.

### Verdict

The NEXUS architecture (GLiNER + Neo4j + custom resolution) is **aligned with where the research is heading**. The problems are implementation gaps, not architectural mistakes.

---

## Maturity Scorecard

### Current State: 2/10

| Dimension | Expected (Enterprise) | Current State | Score |
|-----------|----------------------|---------------|-------|
| Entity count accuracy | 2,000-3,500 | 31,990 (~10x inflated) | 1/10 |
| Entity name quality | Clean, normalized | OCR artifacts, garbage | 2/10 |
| Alias resolution | ALIAS_OF linking variants | 0 ALIAS_OF edges | 0/10 |
| Relationship quality | Typed, meaningful (EMPLOYED_BY, etc.) | CO_OCCURS dominates (1.27M), mostly noise | 2/10 |
| Entity-chunk linkage | Direct Entity→Chunk edges | Entity→Document only (page-level) | 2/10 |
| Community detection | Auto-triggered in queries | Computed but dormant | 3/10 |
| Graph in RAG pipeline | Entity-weighted reranking, multi-hop | 1-hop optional tool | 3/10 |
| Entity properties | Description, role, temporal metadata | Name + mention_count only | 2/10 |
| Resolution infrastructure | Token-based blocking, batch runs | First-char blocking, per-document | 3/10 |
| Pre-extraction normalization | OCR denoising, pattern filtering | Pronoun/stopword filter only | 2/10 |

---

## Remediation Plan

### Phase 1: Clean the Existing Graph (Operational — No Code Changes)

**1a. Bulk garbage removal** — Delete entities matching clear noise patterns:
- All entities with `\n` or `\r` in names (155)
- All entities with 51+ char names matching URL slug patterns
- All entities with 1-2 char names that aren't state abbreviations
- All person/org/location entities that are pure numbers
- Known garbage: "addressee(s)", "shes", "People", "Money", "Cash", "E-Mail", "Today", "Tomorrow", day names

**1b. Prune CO_OCCURS** — Delete all weight=1 edges (1.25M of 1.27M). They are never queried and add no information.

**1c. Run batch entity resolution** — Single batch run per matter (not per-document) to collapse obvious duplicates.

### Phase 2: Fix Pre-Extraction Normalization (Code Changes)

**2a. OCR text cleanup before NER** — In the extractor or ingestion pipeline, before chunks go to GLiNER:
- Strip/collapse newlines: `name.replace('\n', ' ').replace('\r', '')`
- Rejoin hyphenation: `re.sub(r'(\w)- (\w)', r'\1\2', name)`
- Collapse multiple spaces

**2b. Enhanced `_is_garbage_entity()` filter:**
- Reject names matching URL slug patterns (3+ consecutive hyphen-separated lowercase words)
- Reject names longer than ~50 chars
- Reject names with 3+ consecutive uppercase/garbled chars not matching known patterns
- Raise GLiNER confidence threshold from 0.3 to 0.4 or 0.5
- Filter relative dates ("Today", "Tomorrow", day names) from date entities
- Filter generic nouns from monetary amounts ("Money", "Cash")

**2c. Case-normalize MERGE key** — Use `toLower(trim(name))` in the Neo4j MERGE to prevent case-variant duplicates.

### Phase 3: Fix Entity Resolution (Code Changes)

**3a. Replace first-character blocking** with token-based blocking:
- Bucket entities by any shared token (not just first character)
- "Jeffrey Epstein" and "Epstein, Jeffrey" share token "Epstein" → compared
- Much better recall for last-name-first formats and OCR-corrupted names

**3b. Debounce resolution agent** — Run at most once per matter per N minutes, or only after bulk import completion. Not per-document.

**3c. Add batch resolution endpoint** — Admin-triggered bulk resolution for an entire matter, separate from the per-document trigger.

### Phase 4: Entity→Chunk Linkage (Code Change — Structural)

**4a. Add `EXTRACTED_FROM` relationship** — Entity → Chunk (in addition to Entity → Document via MENTIONED_IN):
```cypher
MERGE (e:Entity {name: $name, type: $type, matter_id: $matter_id})
MERGE (e)-[:EXTRACTED_FROM]->(c:Chunk {id: $chunk_id})
```

**4b. Recompute CO_OCCURS at chunk level** — Entity pairs co-occurring in the same chunk, not same document. Far fewer, far more meaningful edges.

**4c. Store entity mentions in Qdrant payload** — Add extracted entity names to each chunk's Qdrant payload for entity-aware vector filtering.

### Phase 5: Enrich the Graph (Code Changes, Flag-Gated)

**5a. Add spaCy SVO triple extraction** — Subject-Verb-Object relationship extraction on every chunk at ingestion time. Free, CPU-based, 94% of LLM quality per research. Produces typed relationships (EMPLOYED_BY, ASSOCIATED_WITH, etc.) without LLM cost.

**5b. Wire community summaries into query pipeline** — Make `get_community_context` auto-trigger when queries span multiple entities in the same community. This is GraphRAG's actual killer feature and we already have the infrastructure.

**5c. Entity descriptions** — LLM-generated one-line descriptions for high-mention entities (>10 mentions). Stored as entity property, injected into RAG context.

**5d. Enable coreference resolution** — `ENABLE_COREFERENCE_RESOLUTION` flag. Links pronouns to entities within document context after base entity quality is clean.

### Priority & Effort Matrix

| Improvement | Phase | Effort | Impact | Cost |
|-------------|-------|--------|--------|------|
| OCR normalization before NER | 2 | Low | **Critical** — eliminates ~5,000+ garbage entities | $0 |
| Enhanced garbage filtering | 2 | Low | **High** — removes URL slugs, phrases, generic nouns | $0 |
| Case-normalize MERGE key | 2 | Low | **Medium** — prevents case-variant duplicates | $0 |
| Token-based blocking in resolver | 3 | Medium | **High** — catches cross-initial duplicates | $0 |
| Debounce resolution agent | 3 | Low | **Medium** — prevents redundant runs | $0 |
| Bulk garbage deletion | 1 | Low | **High** — immediate graph quality improvement | $0 |
| Prune CO_OCCURS weight=1 | 1 | Low | **Medium** — removes 1.25M useless edges | $0 |
| Entity→Chunk edges | 4 | Medium | **High** — enables entity-aware retrieval | $0 |
| Chunk-level CO_OCCURS | 4 | Medium | **High** — meaningful co-occurrence | $0 |
| spaCy SVO triples | 5 | Medium | **High** — typed relationships on all chunks | $0 |
| Wire community summaries | 5 | Medium | **High** — GraphRAG's best feature, already built | $0 |
| Entity descriptions (LLM) | 5 | Low | **Medium** — richer entity context in RAG | ~$20-50 |

---

## Operational Concerns

### NER Worker OOM (Critical)

The NER Celery worker is being SIGKILL'd (OOM) during GLiNER model loading:

```
[2026-03-26 18:42:03] ERROR Process 'ForkPoolWorker-872' pid:32743
                       exited with 'signal 9 (SIGKILL)'
[2026-03-26 18:42:03] ERROR Task handler raised error:
                       WorkerLostError('Worker exited prematurely: signal 9 (SIGKILL)')
```

12,549 jobs are pending. The ~600MB GLiNER model + worker memory pressure on the n1-standard-8 (30GB shared across all containers) causes thrashing. Each OOM kills a worker, which restarts and re-loads the model, only to OOM again.

**Fix:** Increase NER worker memory limit, reduce fork concurrency, or switch to `--pool=solo` for the NER worker.

### Neo4j/PostgreSQL Document Mismatch

47,428 Document nodes in Neo4j vs 45,374 rows in PostgreSQL. 2,054 stale nodes need reconciliation.

### Qdrant Client Version Mismatch

Client v1.17.1 vs server v1.13.2. Generating warnings but functional. May cause subtle issues with newer API features.

### Resolution Agent Inefficiency

70K+ trigger calls for 63 actual executions. Per-document triggering doesn't scale. Needs debouncing or batch-only mode.

---

## Appendix: Current Entity Pipeline Architecture

```
Document Upload
  │
  ▼
[PARSE] → Docling OCR → extracted text
  │
  ▼
[CHUNK] → Semantic chunking (max_tokens, overlap)
  │
  ├──────────────────────────────┐
  ▼                              ▼
[EMBED]                        [EXTRACT]
  Dense + Sparse → Qdrant        GLiNER NER (batch, threshold=0.3)
                                   │
                                   ├─ _is_garbage_entity() filter
                                   │    ✓ Pronouns, stopwords
                                   │    ✗ Newlines, hyphenation, URLs
                                   │
                                   ├─ Within-doc dedup by (name_lower, type)
                                   │
                                   ▼
                                 [INDEX TO NEO4J]
                                   MERGE (e:Entity {name, type, matter_id})
                                   → Entity → Document (MENTIONED_IN)
                                   → CO_OCCURS between all entity pairs
                                   ✗ Entity → Chunk link DISCARDED
  │
  ▼
[COMPLETE]
  │
  ├─ resolve_entities.delay(matter_id)  ← fires per document
  │    │
  │    ▼
  │  [RESOLUTION AGENT]
  │    Fuzzy match (first-char blocking, threshold=85)
  │    → Auto-merge if score ≥ 90
  │    → Flag uncertain (60-89) for review
  │    → DETACH DELETE alias, transfer edges
  │
  └─ (optional) Relationship extraction via LLM (feature-flagged)
```

### Configuration Parameters

| Parameter | Value | Location |
|-----------|-------|----------|
| GLiNER model | `urchade/gliner_multi_pii-v1` | `app/config.py` |
| GLiNER confidence threshold | 0.3 | `app/entities/extractor.py:170` |
| NER batch size | 8 (24 for emails) | `app/config.py` |
| Fuzzy match threshold | 85 | `app/entities/resolver.py:60` |
| Auto-merge threshold (fuzzy) | 90 | `app/entities/resolution_agent.py:23` |
| Embedding similarity threshold | 0.92 | `app/entities/resolver.py:61` |
| Auto-merge threshold (cosine) | 0.95 | `app/entities/resolution_agent.py:24` |
| Neo4j MERGE key | `(name, type, matter_id)` — **case-sensitive** | `app/entities/graph_service.py:272` |

### Entity Types Extracted

12 types via GLiNER (`app/entities/extractor.py`):

```
person, organization, location, date, monetary_amount, case_number,
court, vehicle, phone_number, email_address, flight_number, address
```

### Neo4j Uniqueness Constraint

```cypher
CREATE CONSTRAINT entity_name_type_matter
FOR (e:Entity) REQUIRE (e.name, e.type, e.matter_id) IS UNIQUE
```
