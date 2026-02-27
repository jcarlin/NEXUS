# ROADMAP.md Update Instructions

> Give this file to Claude Code along with your existing ROADMAP.md.
> Prompt: "Read ROADMAP-UPDATE-PROMPT.md and apply all changes to ROADMAP.md"

---

## Overview

Update `ROADMAP.md` with the following changes based on an enterprise legal AI architecture review. The review evaluated NEXUS against 10 real litigation query patterns used by law firms, compared against Harvey AI, Relativity aiR, DISCO Cecilia, Hebbia Matrix, and CoCounsel. It identified critical workflow gaps, missing milestones, reordering needs, and features that should be implemented as autonomous agents. Preserve the existing format, tone, and structure of the roadmap. All "Done" milestones stay unchanged.

---

## 1. Add New Milestones

### Add M6b: EDRM Interop + Email Intelligence (2 weeks)
Insert after M6 in the "Next Up" / "Future" section. Depends on M6, parallel with M7.

```markdown
### M6b: EDRM Interop + Email Intelligence (2 weeks)
*Legal ecosystem interoperability — required for any firm using Relativity/DISCO. Depends on M6.*

- [ ] Concordance DAT and Opticon OPT load file import parser
- [ ] EDRM XML import/export support
- [ ] Email threading engine: RFC 5322 headers (Message-ID, In-Reply-To, References) + content-based segment matching fallback
- [ ] Inclusive email chain detection (identify most complete version of each thread)
- [ ] Near-duplicate detection: MinHash + LSH via `datasketch` library (Jaccard threshold ≥0.80), Redis-backed
- [ ] Document version detection: content hash + edit-distance scoring for draft/final identification
- [ ] Alembic migration: `thread_id`, `is_inclusive`, `duplicate_cluster_id`, `version_group_id` fields on documents table
- [ ] ~12 tests (threading accuracy, dedup precision/recall, load file round-trip)

**Key files:** `app/ingestion/email_threading.py`, `app/ingestion/dedup.py`, `app/ingestion/load_file_parser.py`, Alembic migration
```

### Add M8b: Embedding Abstraction Layer (0.5 weeks)
Insert after M8. No new dependencies — pure refactor. **This is urgent due to privilege risk.**

```markdown
### M8b: Embedding Abstraction Layer (0.5 weeks)
*Post-Heppner (SDNY, Feb 2026), documents processed through consumer-grade AI may lose attorney-client privilege. Must decouple from OpenAI before processing privileged documents. Depends on M8.*

- [ ] `app/common/embedder.py` abstraction: `EmbeddingProvider` protocol with `embed_texts()` and `embed_query()` methods
- [ ] OpenAI provider (existing behavior, now behind interface)
- [ ] Local provider stub: BGE-large-en-v1.5 via sentence-transformers (CPU/GPU auto-detect, follows Reranker pattern)
- [ ] Config: `EMBEDDING_PROVIDER=openai|local`, `LOCAL_EMBEDDING_MODEL` setting
- [ ] All embedding calls routed through abstraction (ingestion pipeline + query pipeline)
- [ ] Audit logging: every external embedding API call logged with data hash (for privilege compliance verification)
- [ ] Optional: legal domain embeddings support (voyage-law-2 or similar fine-tuned model) as third provider
- [ ] ~5 tests

**Key files:** `app/common/embedder.py`, `app/ingestion/embedder.py` (refactor), `app/query/retriever.py` (refactor)

**Note:** Harvey AI uses custom legal embeddings (voyage-law-2-harvey) as a key differentiator. Even if we start with OpenAI/BGE, the abstraction layer enables swapping in legal-domain embeddings later without pipeline changes.
```

### Add M9b: Case Intelligence Layer (2 weeks) — ⚡ AGENT: Case Setup Agent
Insert after M9. Depends on M9. **This is the single biggest workflow gap — it's what separates a legal investigation tool from a generic chatbot.**

```markdown
### M9b: Case Intelligence Layer (2 weeks)
*The foundation that makes Q1-Q10 flow like a real investigation, not 10 disconnected queries. Depends on M9.*

**⚡ AGENT: Case Setup Agent** — When a Complaint or anchor document is uploaded, this agent autonomously:
1. Parses the document end-to-end (full-document retrieval, not chunked)
2. Extracts all Claims/Causes of Action with their legal elements
3. Identifies all Parties with roles (plaintiff, defendant, third-party, witness)
4. Builds a Defined Terms glossary from capitalized terms ("the Company" → "Acme Corp", "Defendant A" → "John Smith, CEO")
5. Extracts a preliminary case timeline from date references
6. Populates Neo4j with the initial case graph
7. Presents results for lawyer review/confirmation

**Implementation:**
- [ ] Alembic migration: `case_contexts` table (matter_id FK, anchor_document_id, status, created_by)
- [ ] Alembic migration: `case_claims` table (case_context_id FK, claim_label, claim_text, legal_elements JSONB)
- [ ] Alembic migration: `case_parties` table (case_context_id FK, name, role, aliases JSONB, entity_id FK to Neo4j)
- [ ] Alembic migration: `case_defined_terms` table (case_context_id FK, term, definition, entity_id FK nullable)
- [ ] Case Setup Agent: LangGraph agent graph — `parse_anchor_doc → extract_claims → extract_parties → extract_defined_terms → build_timeline → populate_graph → present_for_review`
- [ ] `POST /cases/{matter_id}/setup` — upload anchor document, trigger Case Setup Agent
- [ ] `GET /cases/{matter_id}/context` — retrieve full case context (claims, parties, terms, timeline)
- [ ] `PATCH /cases/{matter_id}/context` — lawyer reviews/confirms/edits extracted objects
- [ ] Case context resolution in query pipeline: "Claim A", "Defendant A", "the Company" auto-resolve to stored objects
- [ ] Investigation session model: `investigation_sessions` table — accumulate structured findings across queries within a session
- [ ] ~15 tests

**Key files:** `app/cases/agent.py` (Case Setup Agent), `app/cases/models.py`, `app/cases/router.py`, `app/cases/context_resolver.py`, Alembic migrations

**Why this matters:** Without this, the lawyer must re-explain "Claim A means the fraud allegation described in paragraph 42 of the Complaint" every single query. Harvey and CoCounsel both maintain persistent case context. This is what separates a legal investigation tool from a generic chatbot.
```

### Add M10b: Sentiment + Hot Document Detection (1.5 weeks) — ⚡ AGENTS: Hot Doc Agent + Contextual Completeness Agent
Insert after M10. Depends on M10.

```markdown
### M10b: Sentiment + Hot Document Detection (1.5 weeks)
*Enables Q7-Q8: finding legally significant emotions, admissions, concealment patterns. Depends on M10.*

**⚡ AGENT: Hot Document Scanning Agent** — Batch agent that runs across the entire corpus at ingestion time (not query time). For each document:
1. Scores 7 sentiment dimensions (positive, negative, pressure, opportunity, rationalization, intent, concealment — based on Fraud Triangle theory used by Reveal-Brainspace)
2. Detects admission/guilt signals, inappropriate enthusiasm, deliberate vagueness
3. Computes anomaly score vs. sender's baseline communication patterns
4. Stores all scores as Qdrant payload fields + PostgreSQL columns for fast filtering

**⚡ AGENT: Contextual Completeness Agent** — Specialized agent for Q7 ("emails that don't make sense without additional context"):
1. Analyzes email threads for references to attachments not present in corpus
2. Detects mentions of prior conversations/meetings not captured ("as we discussed", "per our call")
3. Identifies forward references to events with no follow-up in corpus
4. Flags coded language, unusual terseness, or deliberate ambiguity
5. Scores each email's "context gap" — how much missing context is implied

- [ ] Sentiment/intent classification layer: 7 dimensions per Fraud Triangle + legal-specific signals
- [ ] Hot Document Scanning Agent: LangGraph batch agent — runs per-document at ingestion, stores scores
- [ ] Contextual Completeness Agent: LangGraph agent — `analyze_thread_context → detect_missing_refs → detect_coded_language → score_context_gap`
- [ ] Communication anomaly baseline: per-person pattern modeling (avg length, frequency, tone), flag deviations
- [ ] Sentiment scores stored as Qdrant payload fields (filterable) and PostgreSQL columns
- [ ] `sentiment_search`, `hot_doc_search`, `context_gap_search` tools exposed to agentic pipeline (M10)
- [ ] ~12 tests

**Key files:** `app/analysis/sentiment.py`, `app/analysis/hot_docs_agent.py`, `app/analysis/completeness_agent.py`, `app/query/tools.py`
```

### Add M10c: Communication Analytics + Pre-computed Matrices (1 week)
Insert after M10b. Depends on M10, M11.

```markdown
### M10c: Communication Analytics + Pre-computed Matrices (1 week)
*Enables Q5 and Q10: org hierarchy analysis and full communication network analytics. Depends on M10, M11.*

- [ ] Pre-computed communication matrices during ingestion: sender-recipient pair counts, stored in PostgreSQL
- [ ] Neo4j GDS centrality metrics: betweenness (information brokers), PageRank (influence), degree (activity) — stored as node properties, recomputed on ingestion
- [ ] Organizational hierarchy import: `POST /cases/{matter_id}/org-chart` — lawyer uploads or manually defines reporting structure (JSON or simple CSV)
- [ ] Org hierarchy inference from email patterns as fallback: REPORTS_TO edges in Neo4j with `confidence` score, presented for lawyer confirmation
- [ ] Topic auto-clustering via BERTopic: unsupervised clustering of result sets with auto-generated labels (enables Q9 "breakdown by subject matter")
- [ ] `GET /analytics/communication-matrix?matter_id=X` — returns full NxN matrix for all communicators
- [ ] `GET /analytics/network-centrality?matter_id=X` — returns ranked entity list by centrality metric
- [ ] `communication_matrix`, `network_analysis`, and `topic_cluster` tools exposed to agentic pipeline
- [ ] ~10 tests

**Key files:** `app/analytics/communication.py`, `app/analytics/network.py`, `app/analytics/clustering.py`, `app/analytics/router.py`
```

### Add M14b: Redaction (1.5 weeks)
Insert after M14. Depends on M14.

```markdown
### M14b: Redaction (1.5 weeks)
*Legal production compliance — required for GDPR, CCPA, ABA Rule 1.6. Depends on M14.*

- [ ] Permanent redaction engine: remove underlying text data + metadata, not just visual masking
- [ ] PII/PHI auto-detection: SSN, phone, email, DOB, medical terms (spaCy + regex patterns)
- [ ] Privilege redaction: auto-suggest redactions based on privilege tags from M7
- [ ] Redaction log: immutable record of what was redacted, by whom, when (audit compliance)
- [ ] PDF redaction output: produce production-ready redacted PDFs
- [ ] `POST /documents/{id}/redact` — apply redaction set
- [ ] `GET /documents/{id}/redaction-log` — view redaction history
- [ ] ~8 tests

**Key files:** `app/redaction/engine.py`, `app/redaction/pii_detector.py`, `app/redaction/router.py`
```

---

## 2. Expand Existing Milestones

### M7: Audit + Privilege — expand scope for SOC 2 readiness
Add these items to M7's task list:

```markdown
- [ ] Immutable audit trail: append-only table, no UPDATE/DELETE permissions on audit_log
- [ ] Audit all AI interactions: every LLM call logged with prompt hash, model, token count, latency
- [ ] Audit all agent actions: every tool call, every agent decision, every iteration logged with agent_id and session_id
- [ ] Session-level audit grouping: correlate all actions within a single user session
- [ ] Audit log retention policy: configurable retention period, automated archival
- [ ] Export audit logs as CSV/JSON for compliance review
```

Update M7 duration from 1.5 weeks to 2 weeks. Update test count estimate from ~10 to ~15.

### M9: Evaluation Framework — expand scope significantly
Add/replace items in M9's task list:

```markdown
- [ ] Ground-truth Q&A dataset: 50-100 questions with expected answers, source documents, AND expected citation ranges
- [ ] Retrieval metrics: MRR@10, Recall@10, NDCG@10, Precision@10 — measured SEPARATELY for dense, sparse (BM42), and RRF-fused hybrid
- [ ] Answer quality metrics via RAGAS: faithfulness (≥0.95 target), answer relevancy, context precision
- [ ] Citation accuracy metric: percentage of claims with correct source attribution (≥0.90 target)
- [ ] Hallucination rate metric: unsupported claims / total claims (<0.05 target)
- [ ] Post-rationalization detection: verify citations were used DURING reasoning, not found AFTER (Wallat et al. found up to 57% of RAG citations are post-rationalized — model generates from memory then finds a plausible source)
- [ ] Adversarial test set: false premises, trick privilege questions, ambiguous entity references, overturned precedent references
- [ ] `scripts/evaluate.py` CLI — runs full pipeline, reports all metrics, outputs JSON for CI
- [ ] CI integration: `deepeval test run` or equivalent for regression gating on every PR
- [ ] Baseline numbers documented as regression gates
- [ ] Legal-specific evaluation tasks inspired by LegalBench 162-task benchmark (issue-spotting, rule-recall, rule-application, interpretation, rhetorical understanding)
```

Update M9 duration from 1.5 weeks to 2 weeks.

### M10: Agentic Query Pipeline — ⚡ AGENTS: Investigation Orchestrator + Citation Verifier
Update the M10 description and add dependencies:

```markdown
### M10: Agentic Query Pipeline (2.5 weeks)
*Replace the fixed 8-node chain with an adaptive, case-context-aware agent loop. Depends on M8, M9, M9b.*
```

Note the **new dependency on M9b** (Case Intelligence Layer). Add all of the following items to M10:

```markdown
**⚡ AGENT: Investigation Orchestrator** — The core query agent. Unlike a fixed pipeline, this agent:
1. Resolves case context references ("Claim A", "Defendant A", "the Company") via M9b's context resolver
2. Classifies query complexity and selects a routing tier
3. Decomposes complex queries into sub-queries with tool selection per sub-query
4. Maintains investigation session state — each query can reference findings from prior queries in the session
5. Assembles structured responses with CitedClaim objects
6. Returns browsable result sets for document-list queries (Q6, Q7, Q8) vs. narrative answers for analytical queries (Q1-Q5, Q9)

**⚡ AGENT: Citation Verification Agent (CoVe)** — Post-generation agent that independently verifies every claim:
1. Decomposes the generated response into individual factual claims
2. For each claim, generates a verification question
3. Retrieves evidence independently (separate retrieval from the original query)
4. Compares verification evidence with the original claim
5. Flags unsupported claims, downgrades grounding scores, or triggers re-generation
6. Guards against post-rationalization (model generating from parametric knowledge then finding plausible citations)

- [ ] Refactor `app/query/graph.py`: case_context_resolve → classify_and_plan → execute_action → assess_sufficiency → synthesize → verify_citations
- [ ] 3-tier query routing based on complexity classification:
  - Fast path (2-3s): single retrieval → generate (simple lookups, document summarization)
  - Standard path (5-8s): vector + graph → rerank → generate (multi-source questions)
  - Deep path (15-30s streaming): decompose → parallel multi-source → iterate → synthesize (analytical queries)
- [ ] Query routing decision matrix (which backend handles which query type):
  - "What did document X say about Y?" → Qdrant vector search (fast path)
  - "Who communicated with Person A?" → Neo4j Cypher traversal (fast path)
  - "People connected to Person A who discussed Topic X" → Hybrid: vector for topic, graph for relationships (standard path)
  - "Board Director communication counts" → Pre-computed aggregation from PostgreSQL (fast path)
  - "Temporal queries between dates involving Person X" → Neo4j temporal + date range filters (standard path)
  - "All communications relating to Claim A, deduplicated" → Decompose + multi-source + dedup + iterate (deep path)
- [ ] Tool set for agentic dispatch (10 tools):
  - `vector_search` — Qdrant dense+sparse hybrid retrieval
  - `graph_query` — Neo4j Cypher traversal (entity relationships, paths, neighborhoods)
  - `temporal_search` — date-range filtered retrieval across Qdrant + Neo4j
  - `entity_lookup` — entity resolution, aliases, case-defined terms (via M9b context resolver)
  - `document_retrieval` — full document by ID (for doc-level summarization, not chunked)
  - `case_context` — retrieve claims, parties, defined terms, session findings from M9b
  - `sql_aggregation` — metadata aggregations, pre-computed analytics from PostgreSQL
  - `sentiment_search` — filter by sentiment/hot-doc scores (via M10b)
  - `communication_matrix` — pre-computed network analytics (via M10c)
  - `topic_cluster` — BERTopic clustering of result sets (via M10c)
- [ ] Structured CitedClaim output: every factual assertion maps to document_id + page + Bates range + excerpt + grounding_score
- [ ] Citation Verification Agent: LangGraph sub-agent — `decompose_claims → generate_verification_questions → independent_retrieval → compare → flag_or_accept`
- [ ] Self-RAG checkpoints at 4 stages: retrieval decision, relevance check, groundedness check, answer adequacy
- [ ] Two response modes:
  - **Narrative mode** (Q1-Q5, Q9): natural language answer with inline CitedClaim citations
  - **Result set mode** (Q6, Q7, Q8, Q10): returns a browsable, filterable, exportable document collection with metadata (dedup applied, sentiment scores, pagination, sort)
- [ ] Investigation session state: `session_id` groups queries, each query can access prior query findings via `case_context` tool
- [ ] Max iteration hard cap: 1 for fast, 2 for standard, 3 for deep path
- [ ] ~20 tests
```

### M11: Knowledge Graph Enhancement — ⚡ AGENT: Entity Resolution Agent
Add agent designation and expanded items to M11:

```markdown
**⚡ AGENT: Entity Resolution Agent** — Goes beyond GLiNER's initial zero-shot extraction:
1. Resolves aliases across documents (J. Smith, John Smith, JS, Mr. Smith → single entity)
2. Merges duplicate entities using embedding cosine similarity (>0.92) + rapidfuzz (>85) + coreference resolution
3. Infers org hierarchy from email patterns (REPORTS_TO edges with confidence scores)
4. Links case-defined terms from M9b to resolved entities
5. Runs after initial ingestion AND incrementally as new documents arrive
6. Presents uncertain merges for lawyer confirmation

**Note:** CORE-KG research found that removing coreference resolution increases node duplication by 28%, while removing structured prompts increases noisy nodes by 73%. Both must be implemented.

- [ ] Implement 9 core node types: `:Person`, `:Organization`, `:Department`, `:Role`, `:Email`, `:Document`, `:Event`, `:Allegation`, `:Topic`
- [ ] Entity Resolution Agent: LangGraph agent — `extract → deduplicate → resolve_coreferences → merge → infer_hierarchy → link_defined_terms → present_uncertain`
- [ ] Coreference resolution: spaCy `coreferee` or neuralcoref to resolve pronouns and anaphora before entity extraction (prevents 28% node duplication)
- [ ] Temporal properties on ALL organizational relationships: `since` and `until` on MANAGES, HAS_ROLE, MEMBER_OF, BOARD_MEMBER, REPORTS_TO edges
- [ ] Email-as-node modeling: Email nodes connected via SENT, SENT_TO, CC, BCC to Person nodes
- [ ] DISCUSSES edges from Email/Document nodes to Topic nodes
- [ ] Neo4j GDS centrality algorithms: betweenness, PageRank, degree — computed per matter, stored as node properties
- [ ] Legal defined-term support: parse definitions sections, create ALIAS_OF edges for capitalized terms
- [ ] Qdrant↔Neo4j integration: vector search results map to Neo4j nodes by entity_id, enabling graph context enrichment of retrieval results (QdrantNeo4jRetriever pattern)
- [ ] `GraphService.get_communication_pairs(person_a, person_b, date_from, date_to)` — filtered email traversal
- [ ] `GraphService.get_reporting_chain(person, date)` — temporal org hierarchy
- [ ] `GraphService.find_path(entity_a, entity_b, max_hops=5)` — shortest path with relationship type filtering
- [ ] Union-find transitive closure in `app/entities/resolver.py`
- [ ] ~15 tests
```

Add the Neo4j schema spec as a note block in M11:

```markdown
**Neo4j Schema (target state):**
- Node types: `:Person`, `:Organization`, `:Department`, `:Role`, `:Email`, `:Document`, `:Event`, `:Allegation`, `:Topic`
- Relationship types: `SENT`, `SENT_TO`, `CC`, `BCC`, `MANAGES {since, until}`, `HAS_ROLE {since, until}`, `MEMBER_OF {since, until}`, `BOARD_MEMBER {since, until}`, `PARTICIPATED_IN`, `CO_OCCURS_WITH`, `ALIAS_OF`, `DISCUSSES`, `MENTIONS`, `RELATES_TO`, `REPORTS_TO {since, until}`
- All organizational edges carry temporal properties for point-in-time queries
- All nodes carry `matter_id` for tenant isolation
- Qdrant↔Neo4j integration: vector search results map to Neo4j nodes by `entity_id`, enabling graph context enrichment
```

Update M11 duration from 1.5 weeks to 2.5 weeks. Update test count from ~10 to ~15.

### M12: Bulk Import — add EDRM/load files, email threading, scale optimizations, and agent triggers
Add these items to M12's task list:

```markdown
- [ ] EDRM XML import adapter (uses M6b parser)
- [ ] Concordance DAT load file import adapter (uses M6b parser)
- [ ] Email threading pass during bulk import (uses M6b threading engine)
- [ ] Near-duplicate detection pass during bulk import (uses M6b dedup engine)
- [ ] Qdrant bulk optimization: disable HNSW during import (m=0), rebuild after (m=16) for 5-10x faster inserts
- [ ] OpenAI Batch API integration for embeddings (50% cost reduction at scale)
- [ ] Progress tracking: real-time stats (docs processed, errors, ETA) via WebSocket or polling endpoint
- [ ] Post-ingestion agent triggers: queue Hot Document Scanning Agent (M10b) and Entity Resolution Agent (M11) as Celery batch jobs after import completes
```

### M13: React Frontend — add case setup wizard, result set browser, analytics views
Add these items to M13's task list:

```markdown
- [ ] Case setup wizard: upload Complaint, review/edit Case Setup Agent's extracted claims/parties/terms (M9b)
- [ ] Defined terms sidebar: case-specific glossary auto-populated from case context + knowledge graph ALIAS_OF edges, editable by lawyer
- [ ] Investigation session UI: persistent sidebar showing accumulated findings across query chain within a session
- [ ] Result set browser: for Q6/Q7/Q8 queries — browsable, filterable, sortable document list with dedup indicators, sentiment scores, context gap scores, pagination, bulk export
- [ ] Communication matrix heatmap: interactive NxN grid of sender-recipient volumes (from M10c)
- [ ] Network graph visualization: D3/vis.js force-directed graph of entity relationships with clickable nodes
- [ ] Timeline view: chronological event/communication timeline with entity and topic filters
- [ ] Hot document queue: ranked list of flagged documents from sentiment analysis (from M10b)
- [ ] Org chart editor: visual hierarchy that lawyer can confirm/edit (from M10c inference or manual import)
```

### M14: Annotations + Export — add EDRM export and production management
Add these items to M14's task list:

```markdown
- [ ] EDRM XML export: produce standard-compliant export packages for Relativity/DISCO import
- [ ] Privilege log export: auto-generated privilege log with Bates ranges, privilege basis, reviewer
- [ ] Production set management: define production sets, track production status per document
- [ ] Result set export: export any query result set (from M10 result set mode) as CSV, XLSX, or PDF bundle with citation index
```

### M16: Visual Embeddings — add handwriting support and compression strategy
Add these items to M16:

```markdown
- [ ] Handwriting recognition supplement: LlamaParse agentic OCR or dedicated handwriting model for margin annotations, initials, handwritten notes (Docling does not support handwriting)
- [ ] Selective visual embedding: only apply ColQwen2.5 to pages classified as visually complex during ingestion (tables, charts, degraded scans), not all pages — Docling's 97.9% table extraction accuracy means most legal docs are well-served by text alone
- [ ] Light-ColQwen2 compression: semantic clustering at merge factor 9 (retains ~98% NDCG while keeping ~12% of tokens) + Qdrant binary quantization (16x compression)
```

---

## 3. Resequence Milestones

The current ordering delays core value. Key changes:
- **M8b (Embedding Abstraction)** inserted immediately — privilege risk requires this before processing any real client data
- **M9b (Case Intelligence Layer)** is the foundation for all 10 query patterns — must come before M10
- **M15 (Retrieval Tuning)** moves to immediately after M9 — tune retrieval before building agents on top
- **M12 (Bulk Import)** moves earlier because agents need realistic-scale data

Add a new section titled "Recommended Build Order" right after the Milestone Summary Table:

```markdown
## Recommended Build Order

The milestone numbers reflect feature scope, not execution order. The recommended build sequence is:

**Phase 1 — Foundation + Measurement (weeks 1-8):**
M8b (Embedding Abstraction) — immediate, ≤3 days, blocks nothing
M7 (Audit + Privilege + SOC 2) + M6b (EDRM + Email Intelligence) — parallel
→ M9 (Evaluation Framework)
→ M15 (Retrieval Tuning) — moved up, uses M9 eval to optimize before building on top

**Phase 2 — Case Intelligence + Agents (weeks 9-21):**
M9b (Case Intelligence Layer + ⚡ Case Setup Agent) — foundation for all query patterns
→ M10 (Agentic Query Pipeline + ⚡ Investigation Orchestrator + ⚡ Citation Verifier)
→ M11 (KG Enhancement + ⚡ Entity Resolution Agent) + M12 (Bulk Import + EDRM) — parallel
→ M10b (⚡ Hot Doc Agent + ⚡ Completeness Agent) + M10c (Communication Analytics + Topic Clustering) — parallel

**Phase 3 — User-Facing (weeks 22-31):**
M13 (React Frontend — case setup wizard, result set browser, analytics views)
→ M14 (Annotations + Export + EDRM)
→ M14b (Redaction)

**Phase 4 — Optimization (weeks 32-36):**
M16 (Visual Embeddings) — conditional on M9 eval showing text retrieval gaps
→ M17 (Full Local Deployment)

**Why M8b is first:** Attorney-client privilege risk. Cannot process real client documents through external embedding APIs without an abstraction layer that supports local alternatives.

**Why M15 moves before M10:** Retrieval quality is the platform's core value proposition. Building an agentic pipeline on untuned retrieval means the agent compensates for bad retrieval with extra iterations — slower, more expensive, harder to debug. Tune first, then build the agent on a solid foundation.

**Why M9b comes before M10:** The Investigation Orchestrator agent depends on case context resolution. Without persistent Claims, Parties, and Defined Terms, every query is isolated and the lawyer must re-explain context every time. This is the #1 workflow differentiator vs. generic RAG chatbots.
```

---

## 4. Update Milestone Summary Table

Replace the milestone summary table with this updated version. Note the new "Agent?" column:

| # | Milestone | Agent? | Status | Tests | Duration | Dependencies |
|---|---|---|---|---|---|---|
| M0 | Skeleton + Infrastructure | — | Done | 8 | — | — |
| M1 | Single Doc Ingestion | — | Done | 23 | — | M0 |
| M2 | Query Pipeline (LangGraph) | — | Done | 53 | — | M1 |
| M3 | Multi-Format + Entity Resolution | — | Done | 44 | — | M1 |
| M4 | Chat + Streamlit + Doc Browsing | — | Done | 15 | — | M2, M3 |
| M5 | Production Hardening (Core) | — | Done | 16 | — | M4 |
| M5b | Tests + Reranker | — | Done | 27 | — | — |
| M6 | Auth + Multi-Tenancy | — | Done | 15 | — | — |
| M6b | EDRM Interop + Email Intelligence | — | TODO | — | 2 weeks | M6 (parallel w/ M7) |
| M7 | Audit + Privilege + SOC 2 Prep | — | TODO | — | 2 weeks | M6 |
| M8 | Retrieval Infrastructure | — | Done | 8 | — | — |
| M8b | Embedding Abstraction Layer | — | TODO | — | 0.5 weeks | M8 |
| M9 | Evaluation Framework | — | TODO | — | 2 weeks | M8 |
| M9b | Case Intelligence Layer | ⚡ Case Setup | TODO | — | 2 weeks | M9 |
| M10 | Agentic Query Pipeline | ⚡ Orchestrator, Citation Verifier | TODO | — | 2.5 weeks | M8, M9, M9b |
| M10b | Sentiment + Hot Doc Detection | ⚡ Hot Doc, Completeness | TODO | — | 1.5 weeks | M10 |
| M10c | Communication Analytics | — | TODO | — | 1 week | M10, M11 |
| M11 | Knowledge Graph Enhancement | ⚡ Entity Resolution | TODO | — | 2.5 weeks | M10 |
| M12 | Bulk Import + EDRM | — | TODO | — | 2 weeks | M6, M6b, M8 (parallel w/ M10-11) |
| M13 | React Frontend | — | TODO | — | 3.5 weeks | M6, M7, M10, M10b, M10c, M9b |
| M14 | Annotations + Export + EDRM | — | TODO | — | 2.5 weeks | M13 |
| M14b | Redaction | — | TODO | — | 1.5 weeks | M14 |
| M15 | Retrieval Tuning | — | TODO | — | 1 week | M9, M8b |
| M16 | Visual Embeddings | — | TODO | — | 2 weeks | M15 (conditional) |
| M17 | Full Local Deployment | — | TODO | — | 2 weeks | All |

---

## 5. Update Ordering Principles

Add these principles to the existing list:

```markdown
7. Citation provenance must be preserved from parse-time through query-time (page, Bates, section)
8. Legal ecosystem interoperability (EDRM/load files) before bulk import
9. Sentiment/analytics capabilities before frontend (so the UI has data to display)
10. Every LLM-generated claim must be traceable to a specific source passage
11. Case context (claims, parties, defined terms) must persist across queries — stateless Q&A is not legal investigation
12. Features requiring autonomous multi-step reasoning should be implemented as LangGraph agents
13. Guard against post-rationalization: citations must be verified independently, not self-justified
14. Semi-autonomous agents always present results for lawyer review before committing to the knowledge graph
```

---

## 6. Update Dependency Graph

Replace the existing dependency graph with:

```
M5b ──────────────────────┐
                           │
M6 ───┬── M6b ────────────┤
      │                    │
      ├── M7 ──────────────┤
      │                    │
      │   M8 ── M8b ──────┤──── M9 ── M15 (tuning)
      │                    │           │
      │                    │    M9b ───┤ (⚡ Case Setup Agent)
      │                    │           │
      │                    │    M10 ──┬── M10b (⚡ Hot Doc + Completeness Agents)
      │                    │          │
      │                    │    M11 ──┤── M10c (analytics + topic clustering)
      │                    │   (⚡ ER) │
      │            M6b+M8 ── M12 ─────┤
      │                               │
      M6+M7+M9b+M10+M10b+M10c ── M13 ── M14 ── M14b
                                                      All ── M17
                                   M15 ── M16 (conditional)
```

---

## 7. Add New Section: "Agent Architecture"

Add this section after the Dependency Graph, before "Legal Query Capability Matrix":

```markdown
## Agent Architecture

NEXUS uses 6 autonomous LangGraph agents for tasks requiring multi-step reasoning, judgment, and iteration. Each agent follows Anthropic's guidance: "Start with simple prompts, optimize with comprehensive evaluation, and add multi-step agentic systems only when simpler solutions fall short."

| Agent | Milestone | Trigger | Autonomy Level |
|---|---|---|---|
| **Case Setup Agent** | M9b | Upload of anchor document (Complaint) | Semi-autonomous: extracts, then presents for lawyer review/edit |
| **Investigation Orchestrator** | M10 | Every user query | Fully autonomous: plans, retrieves, synthesizes, cites |
| **Citation Verification Agent** | M10 | Post-generation on every response | Fully autonomous: verifies or flags, no human input needed |
| **Hot Document Scanning Agent** | M10b | Post-ingestion batch job (Celery) | Fully autonomous: scores all documents in corpus |
| **Contextual Completeness Agent** | M10b | Q7-type queries + batch mode | Fully autonomous: analyzes email threads for context gaps |
| **Entity Resolution Agent** | M11 | Post-ingestion + incremental on new docs | Semi-autonomous: resolves, presents uncertain merges for review |

**Design principles for agents:**
- Each agent is a LangGraph state graph with typed state, conditional edges, and explicit tool bindings
- Agents share the same tool set (vector_search, graph_query, etc.) but with different system prompts and iteration budgets
- All agent actions are logged to the audit trail (M7) — every tool call, every LLM invocation, every decision
- Agents that produce user-facing output always return structured CitedClaim objects (M10 citation architecture)
- Semi-autonomous agents ALWAYS present results for lawyer review before committing to the knowledge graph — the lawyer is the final authority
- Agent iteration budgets: Case Setup (1 pass + review), Investigation Orchestrator (1-3 iterations by tier), Citation Verifier (1 pass per claim), Hot Doc Scanner (1 pass per document), Entity Resolution (1 pass + uncertain queue)
```

---

## 8. Add New Section: "Legal Query Capability Matrix"

Add this section after Agent Architecture:

```markdown
## Legal Query Capability Matrix

Maps the 10 target litigation query patterns to the milestones, agents, and response modes that enable them.

| # | Query Pattern | Required Milestones | Agent(s) | Response Mode | Primary Systems |
|---|---|---|---|---|---|
| Q1 | Summarize Complaint / doc analysis | M9b, M10 | Case Setup (initial), Orchestrator | Narrative | Full-doc retrieval + LLM synthesis |
| Q2 | Evidence responsiveness reasoning | M9b, M10 | Orchestrator | Narrative | Case context (claims) + LLM reasoning |
| Q3 | Key players + defined terms | M9b, M11 | Case Setup, Entity Resolution | Narrative | GLiNER + Neo4j + case glossary |
| Q4 | Multi-hop "who participated" | M9b, M10, M11 | Orchestrator, Entity Resolution | Narrative | Neo4j multi-hop + claims + parties |
| Q5 | Org hierarchy + topic ranking | M10c, M11 | Orchestrator | Narrative + Table | GDS centrality + org chart + topics |
| Q6 | Email dedup + inclusive chains | M6b, M10, M12 | Orchestrator | **Result Set** | Threading + dedup + case context filter |
| Q7 | Sentiment + missing context | M10b | Orchestrator, Completeness Agent | **Result Set** | Sentiment + context gap scores |
| Q8 | Corpus-wide admission detection | M10b, M8 | Hot Doc Agent, Orchestrator | **Result Set** | Pre-computed hot doc scores |
| Q9 | Temporal comms + topic breakdown | M11, M10, M10c | Orchestrator | Narrative + Grouped | Neo4j temporal + BERTopic clusters |
| Q10 | Full communication matrix | M10c, M11 | Orchestrator | **Table** | Pre-computed Cypher aggregation |

**Response modes:**
- **Narrative**: Natural language answer with inline CitedClaim citations (default)
- **Result Set**: Browsable, filterable, exportable document collection with metadata columns (dedup status, sentiment scores, relevance score). Supports pagination, sorting, and bulk export.
- **Table**: Structured data output (matrices, rankings) rendered as interactive tables/heatmaps in frontend
- **Grouped**: Narrative or result set organized into auto-labeled topic clusters (via BERTopic)
```

---

## 9. Add New Section: "Citation Architecture"

Add this section after the Legal Query Capability Matrix:

```markdown
## Citation Architecture

Every response must produce structured, verifiable citations. This is non-negotiable for legal use.

**CitedClaim output schema** (implemented in M10):
- `claims[].text` — the factual assertion in the system's own words
- `claims[].citations[].document_id` — source document
- `claims[].citations[].bates_range` — Bates number range (start, end)
- `claims[].citations[].page` — page number
- `claims[].citations[].section` — section header (if applicable)
- `claims[].citations[].excerpt` — verbatim supporting passage (≤100 words)
- `claims[].citations[].grounding_score` — 0.0–1.0 confidence
- `overall_grounding_score` — weighted average across all claims
- `unsupported_claims[]` — claims the system could not ground (transparency — never hidden)

**Provenance chain** (preserved from ingestion through query):
1. Docling parse → page numbers, section headers, paragraph indices, Bates ranges stored as chunk metadata
2. Qdrant index → all spatial anchors carried in payload
3. Retrieval → source chunks returned with full metadata
4. Synthesis → Investigation Orchestrator generates CitedClaim objects with source references
5. Verification → Citation Verification Agent validates each claim independently

**Post-rationalization guard (critical):**
Research found that up to 57% of RAG citations involve "post-rationalization" — the model generates from parametric knowledge then finds a plausible-looking source. The Citation Verification Agent combats this by:
- Retrieving evidence INDEPENDENTLY for each claim (separate retrieval from the original query)
- Comparing verification evidence with the cited source — if they diverge, the citation is flagged
- Downgrading grounding scores when the claim is correct but the citation doesn't actually support it

**Target metrics** (measured by M9 evaluation framework):
- Faithfulness ≥ 0.95 (claims supported by context / total claims)
- Citation accuracy ≥ 0.90 (claims with correct source attribution)
- Hallucination rate < 0.05 (unsupported claims / total claims)
- Post-rationalization rate < 0.10 (cited source doesn't actually support the claim)
- Unsupported claim disclosure: 100% (always surface ungrounded claims to the lawyer)
```

---

## 10. Add New Section: "Privilege + Data Isolation Architecture"

Add after Citation Architecture:

```markdown
## Privilege + Data Isolation Architecture

**Embedding privacy risk:** OpenAI embedding API sends document text externally. Post-*Heppner* (SDNY, Feb 2026), documents processed through consumer-grade AI may lose attorney-client privilege protection.

**Mitigations (implemented across milestones):**
- M8b provides embedding abstraction layer — hot-swap between OpenAI, local, and legal-domain models
- M17 provides full local embeddings (BGE-M3 via TEI), eliminating external API dependency entirely
- Until M17: require OpenAI zero-data-retention (ZDR) API agreement for all deployments
- All embedding API calls logged in audit trail (M7) with data-sent hash for compliance verification
- Optional: legal domain embeddings (voyage-law-2 or equivalent) for improved legal retrieval quality

**Matter-level isolation (M6):**
- Qdrant: `matter_id` payload filter on every query
- Neo4j: `matter_id` property on all nodes, enforced in all Cypher queries
- PostgreSQL: `matter_id` FK on all data tables, enforced via `get_matter_id()` dependency
- Ethical walls: users see only matters assigned via `user_case_matters` junction table
- Case context objects (M9b): scoped to matter_id, never cross-matter accessible
- Agent actions: all agent tool calls scoped to current matter, enforced at tool level
```

---

## 11. Add New Section: "Scaling for 50,000+ Page Productions"

Add this section after "Privilege + Data Isolation Architecture":

```markdown
## Scaling for 50,000+ Page Productions

**Ingestion pipeline optimization:**
- Qdrant: disable HNSW index during bulk import (`m=0`), rebuild after (`m=16`) for 5-10x faster inserts
- Batch upserts: 1,000–10,000 points per Qdrant upsert call
- OpenAI Batch API for embeddings: 50% cost reduction ($0.065/1M tokens for text-embedding-3-large)
- Cost estimate: 50,000 docs × 500 avg tokens ≈ $1.63 via Batch API
- Celery worker pools: `gevent`/`eventlet` pool for I/O-bound tasks (OpenAI API, MinIO), `forkpool` for compute (Docling OCR, GLiNER NER, text extraction)
- Pipeline pattern: `chain(upload > parse > chunk > embed > extract > index)` with `group()` for parallel document processing — scales linearly with worker count
- Post-ingestion agent batch: Hot Document Scanning Agent + Entity Resolution Agent queued as Celery tasks after import completes

**Query-time latency targets:**
- Vector retrieval (Qdrant HNSW, warm cache): <100ms
- Cross-encoder reranking (BGE-reranker-v2-m3): 50–200ms
- Graph traversal (Neo4j, 2-hop): <50ms
- Case context resolution (M9b): <10ms (PostgreSQL/Redis cached)
- LLM generation: 1–5 seconds
- Citation verification (CoVe agent): 1–3 seconds (parallelized with streaming)
- First token via SSE streaming: ~200ms perceived latency
- Total end-to-end: 2–8s fast/standard, 15–30s deep path

**Caching strategy:**
- Redis semantic cache: cache query embeddings + responses for repeated/similar queries (~2.5s → ~400ms)
- Cache invalidation: on new document ingestion per matter, clear matter-specific entries
- Pre-computed analytics (communication matrices, centrality scores, hot doc rankings): PostgreSQL, refreshed on ingestion
- Case context objects: cached in Redis per matter, invalidated on edit

**Memory and storage estimates for 50K-page production:**
- Qdrant dense vectors (1024d float32): ~200MB
- Qdrant sparse vectors (BM42): ~50MB
- ColQwen2.5 visual vectors (if enabled, compressed): ~2-4GB for visually complex pages only
- Neo4j graph (entities + relationships + email nodes): ~500MB-1GB
- PostgreSQL (metadata + case context + audit log + analytics): ~200MB
- MinIO raw documents: varies (original file sizes)
- Redis (cache + semantic cache + dedup index): ~100MB
- Total infrastructure overhead: ~1-5GB excluding raw documents
```

---

## 12. Update "See Also" Section

Add these entries:

```markdown
- `docs/CITATION-ARCHITECTURE.md` — CitedClaim schema, provenance chain, CoVe verification, post-rationalization guard
- `docs/QUERY-PATTERNS.md` — 10 target litigation query patterns with expected system behavior and response modes
- `docs/EDRM-INTEROP.md` — Load file formats, email threading algorithm, dedup strategy
- `docs/AGENT-ARCHITECTURE.md` — 6 agents: design patterns, tool set spec, iteration budgets, audit requirements
- `docs/CASE-INTELLIGENCE.md` — Case context object model, defined terms glossary, investigation session state
```

---

## 13. Update Total Estimates

Update the summary line near the top:

```markdown
**Total tests: 210 passing** (as of M8 completion)

**6 autonomous LangGraph agents** across the pipeline (Case Setup, Investigation Orchestrator, Citation Verifier, Hot Doc Scanner, Contextual Completeness, Entity Resolution)

**Estimated remaining: ~36 weeks solo, ~25 weeks with 2 developers** (see Recommended Build Order for phasing and parallelization)
```

---

## Formatting Notes

- Preserve the existing markdown style exactly (heading levels, table alignment, checkbox format)
- Keep all "Done" milestone content unchanged
- New milestones use the same format as existing ones (description italic, task list with checkboxes, key files line, test count estimate)
- The ⚡ emoji marks agent-based features — use consistently in milestone headers and summary table
- Dependency references in parentheses follow the existing convention
- Do not change any content in the "Done" section
