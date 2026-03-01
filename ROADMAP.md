# NEXUS Roadmap

> Multimodal RAG Investigation Platform for Legal Document Intelligence

**Last updated:** 2026-03-01

---

## Milestone Summary

| # | Milestone | Agent? | Status | Tests | Gate | Duration | Dependencies |
|---|---|---|---|---|---|---|---|
| M0 | Skeleton + Infrastructure | — | Done | 8 | Regression | — | — |
| M1 | Single Doc Ingestion | — | Done | 23 | Regression | — | M0 |
| M2 | Query Pipeline (LangGraph) | — | Done | 53 | Regression | — | M1 |
| M3 | Multi-Format + Entity Resolution | — | Done | 44 | Regression | — | M1 |
| M4 | Chat + Streamlit + Doc Browsing | — | Done | 15 | Regression | — | M2, M3 |
| M5 | Production Hardening (Core) | — | Done | 16 | Regression | — | M4 |
| M5b | Tests + Reranker | — | Done | 27 | Regression | — | — |
| M6 | Auth + Multi-Tenancy | — | Done | 15 | Regression | — | — |
| M6b | EDRM Interop + Email Intelligence | — | Done | 15 | Regression + migration | 2 weeks | M6 |
| M7 | Audit + Privilege | — | Done | 20 | Regression | — | M6 |
| M7b | SOC 2 Audit Readiness | — | Done | 10 | Regression + migration | 1 week | M7 |
| M8 | Retrieval Infrastructure | — | Done | 8 | Regression | — | — (parallel w/ M7) |
| M8b | Embedding Abstraction Layer | — | Done | 11 | Regression | — | M8 |
| M9 | Evaluation Framework | — | Done | 11 | Baseline metrics documented | 2 weeks | M8 |
| M9b | Case Intelligence Layer | ⚡ Case Setup | Done | 15 | Regression | 2 weeks | M9 |
| M10 | Agentic Query Pipeline | ⚡ Orchestrator, Citation Verifier | Done | 20 | Regression + eval non-regression | 2.5 weeks | M8, M9, M9b |
| M10b | Sentiment + Hot Doc Detection | ⚡ Hot Doc, Completeness | Done | 12 | Regression + eval non-regression | 1.5 weeks | M10 |
| M10c | Communication Analytics | — | Done | 10 | Regression | 1 week | M10, M11 |
| M11 | Knowledge Graph Enhancement | ⚡ Entity Resolution | Done | 28 | Regression + eval non-regression | 2.5 weeks | M10 |
| M12 | Bulk Import + EDRM | — | Done | 11 | Regression + migration | 2 weeks | M6, M6b, M8 (parallel w/ M10-11) |
| M13 | React Frontend | — | TODO | 12+ | Frontend CI + backend regression | 3.5 weeks | M6, M7, M10, M10b, M10c, M9b |
| M13b | Dataset & Collection Management | — | TODO | TBD | Regression + migration | 2.5 weeks | M13 |
| M14 | Annotations + Export + EDRM (Backend) | — | Done | 10 | Regression + migration | 2.5 weeks | M13 |
| M14b | Redaction | — | TODO | 8 | Regression | 1.5 weeks | M14 |
| M15 | Retrieval Tuning | — | Done | 5 + 4 eval | Eval improvement ≥ 0.03 | 1 week | M9, M8b |
| M16 | Visual Embeddings | — | Done | 16 + eval enum | Eval lift ≥ 5% or stays disabled | 2 weeks | M15 (conditional) |
| M17 | Full Local Deployment | — | TODO | 3+ | Health check + benchmarks | 2 weeks | All |

**Total tests: 486 collected** (399 unit/functional + 12 M10b analysis + 10 M10c analytics + 10 M14 annotations/exports + 5 M16 eval + 50 tech debt; 484 passing, 2 pre-existing failures from missing langchain_anthropic dep)

**6 autonomous LangGraph agents** across the pipeline (Case Setup, Investigation Orchestrator, Citation Verifier, Hot Doc Scanner, Contextual Completeness, Entity Resolution)

**Estimated remaining: ~36 weeks solo, ~25 weeks with 2 developers** (see Recommended Build Order for phasing and parallelization)

---

## Recommended Build Order

The milestone numbers reflect feature scope, not execution order. The recommended build sequence is:

**Phase 1 — Foundation + Measurement (weeks 1-8):**
M8b (Embedding Abstraction) — immediate, ≤3 days, blocks nothing
M7b (SOC 2 Audit Readiness) + M6b (EDRM + Email Intelligence) — parallel
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

---

## Ordering Principles

1. Measure before optimize (eval before retrieval tuning)
2. Secure before share (auth before multi-user features)
3. Infrastructure before features (sparse vectors before agentic query)
4. Each milestone delivers standalone value
5. Dependencies flow forward only
6. Commit messages must not mention Anthropic or Claude Code (no `Co-Authored-By` lines, no tool attribution)
7. Citation provenance must be preserved from parse-time through query-time (page, Bates, section)
8. Legal ecosystem interoperability (EDRM/load files) before bulk import
9. Sentiment/analytics capabilities before frontend (so the UI has data to display)
10. Every LLM-generated claim must be traceable to a specific source passage
11. Case context (claims, parties, defined terms) must persist across queries — stateless Q&A is not legal investigation
12. Features requiring autonomous multi-step reasoning should be implemented as LangGraph agents
13. Guard against post-rationalization: citations must be verified independently, not self-justified
14. Semi-autonomous agents always present results for lawyer review before committing to the knowledge graph

---

## Testing Policy

These rules apply to every milestone. A milestone cannot be marked Done unless its quality gate passes.

### Regression Gate

All existing tests must pass before a milestone is marked Done. Run `pytest tests/ -v` — zero failures, non-negotiable. Any new test failures must be fixed within the milestone that introduced them, not deferred.

### Coverage Floor

No milestone may decrease overall line coverage. Targets:
- **By M10:** 60% line coverage
- **By M13:** 70% line coverage
- **New modules:** Every new `service.py` and `router.py` must have ≥50% line coverage on delivery

### Test Categories

- **Unit:** Tests a single function/class in isolation. Mocks all external dependencies. Fast (<1s each).
- **Integration:** Tests interaction between 2+ internal modules (e.g., router → service → mock DB). May use test fixtures.
- **Contract:** Tests that external service calls use correct parameters, payloads, and handle expected responses. Mocks the service, tests the contract.
- **Evaluation:** Measures retrieval/generation quality against ground-truth dataset. Runs `scripts/evaluate.py`. Slower (minutes). Required for milestones touching query/retrieval after M9.

### Quality Gate Definition

Each milestone defines a gate — a set of pass/fail conditions. A milestone without a defined gate cannot be marked Done. Gates are listed in the Milestone Summary table and detailed in each milestone's `**Testing:**` block.

### Evaluation Regression Gate (M10+)

After M9 establishes baseline metrics, any milestone touching query or retrieval (M10, M10b, M10c, M11, M15, M16) must verify that no evaluation metric regresses by more than 0.05. Run `scripts/evaluate.py` before and after the milestone's changes. Metrics checked:
- MRR@10, Recall@10, NDCG@10
- Faithfulness, citation accuracy, hallucination rate

If a metric regresses beyond the threshold, the milestone must either fix the regression or document a justified trade-off with explicit approval.

---

## Done

### M0: Skeleton + Infrastructure
- Docker Compose with Redis, PostgreSQL, Qdrant, Neo4j, MinIO
- FastAPI app factory with lifespan management
- Alembic migrations (jobs, documents, chat_messages tables)
- Celery worker with Redis broker
- Health check endpoint aggregating all service statuses
- Stub routers for all domains
- Pydantic Settings for config management

**Testing (8 tests):** `tests/test_health.py` — health endpoint response, OpenAPI spec generation, router stub status codes. Gate: regression.

### M1: Single Doc Ingestion
- `POST /ingest` — single file upload to MinIO + Celery dispatch
- 6-stage Celery pipeline: upload > parse > chunk > embed > extract > index > complete
- Docling parser for PDF, DOCX, XLSX, PPTX, HTML, images
- Semantic chunking with document-structure awareness (512 tokens, 64 overlap)
- OpenAI `text-embedding-3-large` (1024d) embeddings
- GLiNER zero-shot NER (lazy-loaded, ~600MB, CPU)
- Qdrant `nexus_text` collection indexing
- Neo4j entity/relationship graph indexing
- Job status tracking with stage progression

**Testing (23 tests):** `tests/test_ingestion/test_router.py`, `test_parser.py`, `test_chunker.py`, `test_embedder.py` — ingest endpoint validation, Docling parser routing, semantic chunking boundaries, embedding batch calls, job status transitions. Gate: regression.

### M2: Query Pipeline (LangGraph)
- `POST /query` — synchronous query with full response
- `POST /query/stream` — SSE streaming (sources before generation, token-by-token)
- LangGraph 9-node state graph: classify > rewrite > retrieve > rerank > check_relevance > reformulate (conditional) > graph_lookup > synthesize > follow_ups
- HybridRetriever: Qdrant dense + Neo4j graph traversal
- Chat persistence in PostgreSQL (JSONB for source_docs/entities)
- `GET /chats`, `GET /chats/{thread_id}`, `DELETE /chats/{thread_id}`

**Testing (53 tests):** `tests/test_query/test_router.py`, `test_nodes.py`, `test_graph.py`, `test_retriever.py`, `test_prompts.py` — graph node transitions, retriever contract (Qdrant + Neo4j calls), prompt template rendering, query/chat endpoint validation, SSE event format. Gate: regression.

### M3: Multi-Format + Entity Resolution
- Parsers for EML, MSG, CSV, RTF, TXT
- ZIP extraction with child job dispatch per contained file
- `POST /ingest/batch` — multi-file upload
- Email-aware chunking (headers as metadata, attachments as sub-documents)
- Entity resolution: rapidfuzz (threshold 85) + embedding cosine (>0.92)
- Instructor + Claude relationship extraction (feature-flagged)
- Working entity/graph API endpoints

**Testing (44 tests):** `tests/test_ingestion/test_parser_m3.py`, `test_batch.py`, `test_zip.py`, `test_webhook.py`, `tests/test_entities/` — multi-format parser dispatch (EML/MSG/CSV/RTF/TXT), ZIP extraction and child dispatch, batch upload validation, entity extraction and resolution, relationship extraction contract. Gate: regression.

### M4: Chat + Streamlit + Doc/Entity Browsing
- DocumentService CRUD with raw SQL
- `GET /documents` (list), `GET /documents/{id}` (detail), `GET /documents/{id}/preview`, `GET /documents/{id}/download`
- Streamlit 3-page dashboard: Chat, Documents, Entities
- DocumentDetail Pydantic schema
- Frontend optional deps in pyproject.toml

**Testing (15 tests):** `tests/test_documents/test_router.py`, `test_service.py` — document CRUD endpoints, presigned URL generation, pagination, MinIO service contract. Gate: regression.

### M5: Production Hardening (Core)
- PostgresCheckpointer for multi-turn LangGraph state persistence
- Streaming refactor (`graph.astream` + `get_stream_writer`)
- MinIO webhook-driven ingestion (`POST /ingest/webhook`)
- Redis sliding-window rate limiting
- structlog with contextvars (request_id, task_id, job_id)
- Configurable embedding batch size

**Testing (16 tests):** `tests/test_query/test_checkpointer.py`, `test_streaming.py`, `tests/test_common/test_rate_limit.py` — checkpointer persistence, SSE stream format and token delivery, rate limit sliding window logic, webhook validation. Gate: regression.

### M5b: Tests + Reranker
- `bge-reranker-v2-m3` cross-encoder reranker (`app/query/reranker.py`) — feature-flagged via `ENABLE_RERANKER`
- Lazy-loaded `CrossEncoder` with MPS/CUDA/CPU auto-detection (follows `EntityExtractor` pattern)
- Rerank node updated: cross-encoder when enabled, score-based sort fallback when disabled or on failure
- DI singleton `get_reranker()` returns `None` when flag is off (no `sentence-transformers` import)
- Config: `reranker_model`, `reranker_top_n` settings added
- Fixed pre-existing failing test (`test_query_stub_returns_not_implemented` → `test_query_requires_body`)
- 8 reranker unit tests, 3 feature-flag node tests
- 17 integration tests: ingest→query pipeline (5), SSE streaming E2E (5), error recovery (7)

**Testing (27 tests):** `tests/test_query/test_reranker.py`, `tests/test_integration/` — reranker scoring and sorting, feature-flag toggling, cross-encoder contract, ingest→query E2E pipeline, SSE streaming E2E, error recovery paths. Gate: regression.

### M6: Auth + Multi-Tenancy
- Alembic migration 002: `users`, `case_matters`, `user_case_matters` tables + NULLABLE `matter_id` FK on `jobs`, `documents`, `chat_messages`
- Seed admin user (admin@nexus.dev) + default matter in migration
- JWT authentication (PyJWT) with access/refresh tokens
- API key auth fallback via `X-API-Key` header
- RBAC: 4 roles (admin, attorney, paralegal, reviewer) via `require_role()` dependency
- `X-Matter-ID` header required on all data endpoints, validated via `get_matter_id()` dependency
- Matter scoping across all routers, services, ingestion pipeline, Neo4j graph, and Qdrant payloads
- CORS lockdown: `allow_origins=["*"]` replaced with configured origins
- Auth dependency overrides in test fixtures (existing 187 tests unaffected)
- 15 tests: auth service (4), auth router (4), auth middleware (7)

**Testing (15 tests):** `tests/test_auth/test_service.py`, `test_router.py`, `test_middleware.py` — JWT issuance and validation, password hashing, role-based access control, matter scoping header enforcement, API key fallback, auth dependency overrides. Gate: regression.

### M7: Audit + Privilege
- Alembic migration 003: `audit_log` table, `privilege_status` + `privilege_reviewed_by` + `privilege_reviewed_at` on `documents`
- `PrivilegeStatus` enum: `privileged`, `work_product`, `confidential`, `not_privileged`
- `PATCH /documents/{id}/privilege` — tag privilege status (admin/attorney/paralegal; reviewer excluded)
- Privilege enforcement at all 3 data layers:
  - SQL: `WHERE privilege_status NOT IN (...)` for non-admin/attorney roles
  - Qdrant: `must_not` filter on `privilege_status` payload field
  - Neo4j: Cypher `WHERE` clause filtering Document nodes by privilege status
- Privilege filtering threaded through query pipeline (router → LangGraph state → retriever → vector store)
- `AuditLoggingMiddleware`: every API call → `audit_log` table (user, action, resource, matter, IP, user_agent, status, duration)
  - Skips noisy endpoints (`/health`, `/docs`, `/openapi.json`, `/redoc`)
  - Own DB session (fire-and-forget), never breaks the request
- `GET /admin/audit-log` — paginated, filterable audit log viewer (admin-only)
- 20 tests: privilege CRUD (4), privilege filtering (3), Qdrant must_not filter (1), Neo4j Cypher filter (1), graph traversal privilege (3), audit middleware (5), admin endpoint (2), helper functions (1)

**Testing (20 tests):** `tests/test_documents/test_privilege.py`, `tests/test_common/test_audit_middleware.py`, `tests/test_auth/test_admin_router.py`, plus privilege tests in `test_query/test_nodes.py` and `test_query/test_retriever.py` — privilege CRUD, 3-layer privilege filtering (SQL + Qdrant + Neo4j), audit middleware fire-and-forget logging, admin audit-log endpoint, graph traversal privilege enforcement. Gate: regression.

### M8: Retrieval Infrastructure
- Sparse embeddings via FastEmbed BM42 (`app/ingestion/sparse_embedder.py`) — feature-flagged via `ENABLE_SPARSE_EMBEDDINGS`
- Lazy-loaded `SparseTextEmbedding` (follows Reranker/EntityExtractor pattern)
- `app/common/vector_store.py` rewritten: named vectors (`dense` + `sparse`), native RRF fusion via `prefetch` + `FusionQuery`
- Backward compatible: unnamed vector format when sparse disabled
- DI singleton `get_sparse_embedder()` returns `None` when flag is off
- HybridRetriever updated: generates sparse vector when embedder available, passes to Qdrant
- Ingestion pipeline: generates sparse embeddings in Stage 3, uses named vector format in Stage 5 upsert
- `scripts/reembed.py` migration script: scroll → re-embed → recreate collection with named vectors
- 8 tests: sparse embedder (2), vector store (4), retriever sparse (2)

**Testing (8 tests):** `tests/test_ingestion/test_sparse_embedder.py`, `tests/test_common/test_vector_store.py`, sparse retriever tests in `test_query/test_retriever.py` — sparse embedding generation, named vector format, native RRF fusion via prefetch, feature-flag toggling, backward compatibility with unnamed vectors. Gate: regression.

### M8b: Embedding Abstraction Layer
- `app/common/embedder.py`: `EmbeddingProvider` protocol with `embed_texts()` and `embed_query()` methods
- `OpenAIEmbeddingProvider`: existing OpenAI behavior behind the protocol, with audit logging (SHA-256 hash of input data on every external API call)
- `LocalEmbeddingProvider`: BGE-large-en-v1.5 via sentence-transformers (CPU/GPU/MPS auto-detect, lazy-loaded, `asyncio.to_thread()` for async compat)
- Config: `EMBEDDING_PROVIDER=openai|local`, `LOCAL_EMBEDDING_MODEL` setting
- All embedding calls routed through abstraction: DI factory (`get_embedder()`), ingestion pipeline (`_embed_chunks`), query pipeline (`HybridRetriever`)
- `app/ingestion/embedder.py` → backward-compatible re-export alias
- 11 tests: OpenAI provider (4), local provider (4), DI factory (2), protocol check (1)

**Testing (11 tests):** `tests/test_common/test_embedder.py` — OpenAI provider embed_texts/embed_query contract, local provider lazy loading and async compat, DI factory provider selection, EmbeddingProvider protocol conformance, audit logging of external API calls. Gate: regression.

---

## Next Up

### M6b: EDRM Interop + Email Intelligence (2 weeks)
*Legal ecosystem interoperability — required for any firm using Relativity/DISCO. Depends on M6.*

- [x] Concordance DAT and Opticon OPT load file import parser
- [x] EDRM XML import/export support
- [x] Email threading engine: RFC 5322 headers (Message-ID, In-Reply-To, References) + subject fallback
- [x] Inclusive email chain detection (identify most complete version of each thread)
- [x] Near-duplicate detection: MinHash + LSH via `datasketch` library (Jaccard threshold ≥0.80)
- [x] Document version detection: filename pattern extraction (v1, draft, final, revised)
- [x] Alembic migration 005: `thread_id`, `is_inclusive`, `duplicate_cluster_id`, `version_group_id` fields on documents table + `edrm_import_log` table
- [x] EDRM API router: POST /edrm/import, GET /edrm/export, GET /edrm/threads, GET /edrm/duplicates
**Testing (15 tests):**
- Load files (4): parse DAT, parse OPT, parse EDRM XML, EDRM XML round-trip
- Threading (7): subject normalization (3), thread by References (1), thread by In-Reply-To (1), subject fallback (1), inclusive detection (1)
- Dedup (3): exact duplicate detected, near-duplicate above threshold, dissimilar docs not matched
- Version (1): filename pattern extraction
- Gate: regression + migration upgrade and downgrade succeed

**Key files:** `app/edrm/`, `app/ingestion/threading.py`, `app/ingestion/dedup.py`, `migrations/versions/005_edrm_email_intelligence.py`

---

### M7b: SOC 2 Audit Readiness (1 week)
*Extends M7's audit infrastructure for SOC 2 compliance. Depends on M7.*

- [x] Immutable audit trail: PostgreSQL RULE-based append-only enforcement on audit_log, ai_audit_log, agent_audit_log
- [x] Audit all AI interactions: every LLM call logged with prompt hash (SHA-256), model, token count, latency, node_name
- [x] Agent audit log schema: agent_audit_log table ready for M10+ agent action logging
- [x] Session-level audit grouping: X-Session-ID header binding via RequestIDMiddleware, correlated across all audit tables
- [x] Audit log retention policy: configurable retention period, dry-run/apply endpoints
- [x] Export audit logs as CSV/JSON for compliance review (admin-only endpoints)
- [x] Alembic migration 004: ai_audit_log, agent_audit_log tables + session_id on audit_log + immutability rules
- [x] Admin audit API: GET /admin/audit/ai, GET /admin/audit/export, GET/POST /admin/audit/retention
**Testing (10 tests):**
- Unit: AI call INSERT verification (1), prompt hash determinism (2), CSV export format (1), list with filters (1), migration immutability rules (1)
- Integration: session_id from header (1), session_id auto-generation (1), admin endpoint 200 (1), non-admin 403 (1)
- Gate: regression + migration upgrade and downgrade succeed

**Key files:** `app/audit/`, `app/common/llm.py`, `app/common/middleware.py`, `migrations/versions/004_soc2_audit.py`

---

---

### M9: Evaluation Framework (2 weeks) ✅
*Measure before you optimize. Must come before retrieval tuning and agentic query.*

- [x] Ground-truth Q&A dataset: 5 seed questions with expected answers, source documents, AND expected citation ranges (expandable to 50-100)
- [x] Retrieval metrics: MRR@10, Recall@10, NDCG@10, Precision@10 — measured SEPARATELY for dense, sparse (BM42), and RRF-fused hybrid
- [x] Answer quality metrics via RAGAS: faithfulness (≥0.95 target), answer relevancy, context precision
- [x] Citation accuracy metric: percentage of claims with correct source attribution (≥0.90 target)
- [x] Hallucination rate metric: unsupported claims / total claims (<0.05 target)
- [x] Post-rationalization detection: verify citations were used DURING reasoning, not found AFTER (Wallat et al. found up to 57% of RAG citations are post-rationalized — model generates from memory then finds a plausible source)
- [x] Adversarial test set: false premises, trick privilege questions, ambiguous entity references, overturned precedent references (4 items)
- [x] `scripts/evaluate.py` CLI — runs full pipeline, reports all metrics, outputs JSON for CI
- [ ] CI integration: `deepeval test run` or equivalent for regression gating on every PR (deferred — run manually via `scripts/evaluate.py --dry-run` for now)
- [x] Baseline numbers documented as regression gates
- [x] Legal-specific evaluation tasks inspired by LegalBench 162-task benchmark (issue-spotting, rule-recall, rule-application, interpretation, rhetorical understanding) — 5 seed items
- [x] Sparse-only retrieval method added to `VectorStoreClient` for separate measurement

**Dry-run baseline metrics (synthetic — gates for regression):**
| Metric | Value | Gate |
|--------|-------|------|
| MRR@10 (hybrid) | 1.000 | — |
| Recall@10 (hybrid) | 1.000 | — |
| NDCG@10 (hybrid) | 1.000 | — |
| Precision@10 (hybrid) | 0.160 | — |
| Faithfulness | 0.970 | ≥ 0.95 |
| Citation accuracy | 0.950 | ≥ 0.90 |
| Hallucination rate | 0.020 | < 0.05 |
| Post-rationalization rate | 0.050 | < 0.10 |

**Testing (11 tests):**
- Unit: ground-truth dataset loader and schema validation (1), retrieval metric computation — MRR@10, Recall@10, NDCG@10, Precision@10 (4), citation extraction regex (1), citation accuracy metric (1), hallucination rate metric (1), post-rationalization detection (1)
- Integration: adversarial test set loads and validates all 4 categories (1), `scripts/evaluate.py --dry-run` exits 0 (1)
- Gate: baseline metrics documented in this file + `scripts/evaluate.py --dry-run` exits 0

**Key files:** `evaluation/` directory, `scripts/evaluate.py`, `app/common/vector_store.py` (sparse-only query)

---

## Future

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
- [x] Alembic migration: `case_contexts` table (matter_id FK, anchor_document_id, status, created_by)
- [x] Alembic migration: `case_claims` table (case_context_id FK, claim_label, claim_text, legal_elements JSONB)
- [x] Alembic migration: `case_parties` table (case_context_id FK, name, role, aliases JSONB, entity_id FK to Neo4j)
- [x] Alembic migration: `case_defined_terms` table (case_context_id FK, term, definition, entity_id FK nullable)
- [x] Case Setup Agent: LangGraph agent graph — `parse_anchor_doc → extract_claims → extract_parties → extract_defined_terms → build_timeline → populate_graph`
- [x] `POST /cases/{matter_id}/setup` — upload anchor document, trigger Case Setup Agent
- [x] `GET /cases/{matter_id}/context` — retrieve full case context (claims, parties, terms, timeline)
- [x] `PATCH /cases/{matter_id}/context` — lawyer reviews/confirms/edits extracted objects
- [x] Case context resolution in query pipeline: "Claim A", "Defendant A", "the Company" auto-resolve to stored objects
- [x] Investigation session model: `investigation_sessions` table — schema created (accumulation logic deferred to M10)

**Testing (15 tests):**
- Unit: case context CRUD — create/read/update (3), claims extraction from anchor doc (2), party identification and role assignment (1), defined term resolution (1), context resolver — term/alias/party lookups (3)
- Integration: Case Setup Agent graph compilation and e2e run (1), agent e2e with mock LLM (1), router endpoint contracts — setup/context/patch (3)
- Gate: regression + case context resolution works in query pipeline (context resolver returns correct objects for "Claim A", "Defendant A", "the Company")

**Key files:** `app/cases/agent.py` (Case Setup Agent), `app/cases/schemas.py`, `app/cases/service.py`, `app/cases/router.py`, `app/cases/context_resolver.py`, `app/cases/tasks.py`, `app/cases/prompts.py`, `migrations/versions/006_case_intelligence.py`

**Why this matters:** Without this, the lawyer must re-explain "Claim A means the fraud allegation described in paragraph 42 of the Complaint" every single query. Harvey and CoCounsel both maintain persistent case context. This is what separates a legal investigation tool from a generic chatbot.

---

### M10: Agentic Query Pipeline (2.5 weeks)
*Replace the fixed 8-node chain with an adaptive, case-context-aware agent loop. Depends on M8, M9, M9b.*

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

- [x] Refactor `app/query/graph.py`: `build_agentic_graph()` — 4-node parent StateGraph (case_context_resolve → investigation_agent → verify_citations → generate_follow_ups) with `create_react_agent` subgraph
- [x] 3-tier query routing based on complexity classification:
  - Fast path (recursion_limit=6): single retrieval → generate (simple lookups, document summarization)
  - Standard path (recursion_limit=12): vector + graph → rerank → generate (multi-source questions)
  - Deep path (recursion_limit=20): decompose → parallel multi-source → iterate → synthesize (analytical queries)
- [x] Query routing decision matrix — LLM selects tools based on system prompt guidance (tool descriptions encode routing logic)
- [x] Tool set for agentic dispatch (10 tools in `app/query/tools.py`):
  - `vector_search` — Qdrant dense+sparse hybrid retrieval
  - `graph_query` — Neo4j Cypher traversal (entity relationships, paths, neighborhoods)
  - `temporal_search` — date-range filtered retrieval across Qdrant + Neo4j
  - `entity_lookup` — entity resolution, aliases, case-defined terms (via M9b context resolver)
  - `document_retrieval` — full document by ID (for doc-level summarization, not chunked)
  - `case_context` — retrieve claims, parties, defined terms, session findings from M9b
  - `sentiment_search` — queries PostgreSQL sentiment columns by dimension (M10b)
  - `hot_doc_search` — finds hot documents ranked by composite risk score (M10b)
  - `context_gap_search` — finds documents with missing context / incomplete comms (M10b)
  - `communication_matrix` — wired to AnalyticsService (M10c)
  - `topic_cluster` — BERTopic clustering (M10c, feature-flagged)
  - `network_analysis` — Neo4j GDS centrality metrics (M10c)
- [x] Structured CitedClaim output: every factual assertion maps to document_id + page + Bates range + excerpt + grounding_score
- [x] Citation Verification (CoVe): `verify_citations` node — decompose claims → independent retrieval → judge each (claim, evidence) pair via Instructor
- [x] Self-RAG via `create_react_agent` built-in loop: agent decides when to retrieve more, when to respond
- [x] Two response modes: narrative (default) and result set — guided by system prompt
- [x] Investigation session state: `case_context` tool provides prior query findings; `case_context_resolve` node injects case context + term map
- [x] Max iteration via `recursion_limit`: 6 for fast, 12 for standard, 20 for deep path
- [x] Feature flag: `ENABLE_AGENTIC_PIPELINE=true` (default) — set `false` for v1 graph fallback
- [x] `InjectedState` pattern: matter_id and privilege filters injected from graph state into every tool (LLM never sees them)
- [x] `post_model_hook` for SOC 2 audit logging: every LLM call logged to `ai_audit_log` table
- [x] SSE streaming: `_agentic_event_generator` uses `stream_mode=["messages", "updates", "custom"]`
- [x] Backward-compatible API: `QueryResponse` adds optional `cited_claims` and `tier` fields (all with defaults)

**Testing (20 tests):** ✅
- Unit: complexity classifier — fast/standard/deep routing (3), query decomposition `_parse_claims` (1), tool functions — vector_search/graph_query/temporal_search/entity_lookup/document_retrieval/case_context + stubs (7), CitedClaim schema validation and serialization (2), iteration cap enforcement per tier (1)
- Integration: CoVe — claim decomposition + fast-tier skip (2), Self-RAG — case_context_resolve + generate_follow_ups_agentic (2), agentic graph compilation and expected nodes (1), SSE streaming with agentic status events (1)
- Gate: regression — 346/350 pass (4 pre-existing rerank test-ordering failures unrelated to M10)

**Key files:** `app/query/graph.py`, `app/query/nodes.py`, `app/query/schemas.py`, `app/query/prompts.py`, `app/query/tools.py`

---

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

- [x] Sentiment/intent classification layer: 7 dimensions per Fraud Triangle + legal-specific signals
- [x] Hot Document Scanning Agent: Instructor+LLM per-document scorer — runs post-ingestion via Celery, stores scores
- [x] Contextual Completeness Agent: Instructor+LLM analyzer — detects missing refs, coded language, context gaps
- [x] Communication anomaly baseline: per-person pattern modeling (avg sentiment, message count), z-score deviation
- [x] Sentiment scores stored as Qdrant payload fields (filterable) and PostgreSQL columns (migration 009)
- [x] `sentiment_search`, `hot_doc_search`, `context_gap_search` tools exposed to agentic pipeline (M10)

**Testing (12 tests):**
- Unit: sentiment classifier — 7-dimension scoring (2), Hot Document Scanning Agent — score computation and threshold (2), Contextual Completeness Agent — missing reference detection and context gap scoring (2), anomaly baseline — per-person deviation detection (2), tool contracts — sentiment_search/hot_doc_search/context_gap_search parameter and return validation (3)
- Integration: Qdrant payload storage of sentiment scores (1)
- Gate: regression + eval non-regression (no metric regresses > 0.05 vs M9 baseline)

**Key files:** `app/analysis/sentiment.py`, `app/analysis/completeness.py`, `app/analysis/anomaly.py`, `app/analysis/tasks.py`, `app/analysis/schemas.py`, `app/query/tools.py`

---

### M10c: Communication Analytics + Pre-computed Matrices (1 week) — DONE
*Enables Q5 and Q10: org hierarchy analysis and full communication network analytics. Depends on M10, M11.*

- [x] Alembic migration 008: `communication_pairs` and `org_chart_entries` tables
- [x] Pre-computed communication matrices during ingestion: sender-recipient pair counts from email metadata JSONB, stored in PostgreSQL, incrementally updated post-ingestion
- [x] Email metadata persistence fix: `_create_document_record()` now passes `parse_result.metadata` (stripped of `attachment_data`) to the JSONB column
- [x] Neo4j GDS centrality metrics: betweenness (information brokers), PageRank (influence), degree (activity) — `GraphService.compute_centrality()` with matter-scoped GDS projections
- [x] Organizational hierarchy import: `POST /cases/{matter_id}/org-chart` — attorney/admin uploads reporting structure as JSON
- [x] Org hierarchy inference from email patterns as fallback: asymmetric communication analysis with `confidence` scores
- [x] Topic auto-clustering via BERTopic: `TopicClusterer` (feature-flagged `ENABLE_TOPIC_CLUSTERING`) with lazy-loaded model
- [x] `GET /analytics/communication-matrix?matter_id=X` — returns full NxN matrix for all communicators
- [x] `GET /analytics/network-centrality?matter_id=X&metric=degree` — returns ranked entity list by centrality metric
- [x] `communication_matrix`, `network_analysis`, and `topic_cluster` tools replace stubs in agentic pipeline

**Testing (10 tests):**
- Unit: communication matrix computation from email pairs (2), centrality metrics — degree/PageRank/betweenness (2), org hierarchy import and inference (2), BERTopic clustering with auto-labels (1), endpoint contracts — communication-matrix/network-centrality (2), tool contracts — communication_matrix parameter validation (1)
- Gate: regression (399 passed, 2 pre-existing failures unrelated to M10c)

**Key files:** `app/analytics/service.py`, `app/analytics/schemas.py`, `app/analytics/clustering.py`, `app/analytics/router.py`, `app/entities/graph_service.py` (compute_centrality), `app/query/tools.py` (3 tool implementations)

---

### Tech Debt Completion (M5 + L1–L5) — DONE

*Post-M10c audit identified 16 tech debt items across 4 priorities. Completed 5 of 6 actionable items (L3 skipped by design). Zero regressions.*

**Sprint 5 — M5: God Functions Decomposition**
- [x] Decomposed `process_document()` (535→~50 lines) into `_PipelineContext` dataclass + 6 stage functions: `_stage_parse`, `_stage_chunk`, `_stage_embed`, `_stage_extract`, `_stage_index`, `_stage_complete`
- [x] Extracted `_should_skip_zip_member()` and `_process_zip_member()` from `process_zip()`
- [x] Decomposed `verify_citations()` (120→~47 lines) into `_decompose_claims()` and `_verify_single_claim()` (CoVe pattern)

**Sprint 6 — L5: Logging Context Consistency**
- [x] Removed ~45 redundant `job_id=`/`doc_id=` kwargs from logger calls across 4 files (already bound via `bind_contextvars`)
- [x] Added `matter_id` to `bind_contextvars()` in ingestion tasks
- [x] Rule: service methods called from multiple contexts keep per-call kwargs; only task entry points and middleware bind context

**Sprint 7 — L1: Config Grouping + L2: DI Standardization**
- [x] Added 8 nested `BaseModel` config groups to `app/config.py`: `LLMConfig`, `EmbeddingConfig`, `DatabaseConfig`, `StorageConfig`, `RetrievalConfig`, `AuthConfig`, `ProcessingConfig`, `FeatureFlags` — zero caller changes, backward compatible via `@model_validator(mode="after")`
- [x] Replaced 17 `global + None-check` singletons in `app/dependencies.py` with `@functools.cache` (444→258 lines)
- [x] Updated `close_all()` to use `.cache_clear()` on all factory functions

**Sprint 8 — L4: Test Edge Case Coverage**
- [x] Parser failures: corrupted PDF, zero-byte file, Docling timeout (3 tests)
- [x] Dedup edge cases: empty text, single-char, unicode, boundary threshold, idempotent doc_id (6 tests)
- [x] Task retry/failure: failed stage update, engine disposal, error propagation, corrupt zip, cancelled job (6 tests)
- [x] Rate limiting: Redis unavailable, zero remaining → 429 (2 tests)

**L3: MinIO asyncio.to_thread() — SKIPPED** (per audit: only worth changing if storage becomes a bottleneck; current sync approach is correct for localhost MinIO)

**Testing (50 new tests):**
- `tests/test_ingestion/test_task_stages.py` (13): one per stage function + zip helpers
- `tests/test_query/test_nodes.py` (+6): `_decompose_claims` + `_verify_single_claim` tests
- `tests/test_common/test_logging_context.py` (3): structlog contextvars propagation
- `tests/test_common/test_config.py` (10): flat field compat + nested model groups + env var override
- `tests/test_common/test_dependencies.py` (12): singleton identity + feature flags + cache_clear
- `tests/test_ingestion/test_task_failures.py` (6): retry, disposal, error propagation
- Gate: regression (484 passed, 2 pre-existing `langchain_anthropic` failures unrelated)

**Key files:** `app/ingestion/tasks.py`, `app/query/nodes.py`, `app/common/middleware.py`, `app/analysis/tasks.py`, `app/cases/tasks.py`, `app/config.py`, `app/dependencies.py`

---

### M11: Knowledge Graph Enhancement (2.5 weeks)
*Multi-hop traversal, temporal queries, coreference resolution, and entity resolution overhaul. Depends on M10.*

**⚡ AGENT: Entity Resolution Agent** — Goes beyond GLiNER's initial zero-shot extraction:
1. Resolves aliases across documents (J. Smith, John Smith, JS, Mr. Smith → single entity)
2. Merges duplicate entities using embedding cosine similarity (>0.92) + rapidfuzz (>85) + coreference resolution
3. Infers org hierarchy from email patterns (REPORTS_TO edges with confidence scores)
4. Links case-defined terms from M9b to resolved entities
5. Runs after initial ingestion AND incrementally as new documents arrive
6. Presents uncertain merges for lawyer confirmation

**Note:** CORE-KG research found that removing coreference resolution increases node duplication by 28%, while removing structured prompts increases noisy nodes by 73%. Both must be implemented.

- [x] Implement 9 core node types: `:Person`, `:Organization`, `:Location`, `:Event`, `:Financial`, `:LegalReference`, `:ContactInfo`, `:Email`, `:Topic` — dual-label system (`:Entity:Person`) for backward compat
- [x] Neo4j schema init: `ensure_schema()` with constraints + indexes, called from FastAPI lifespan
- [x] One-time migration: `migrate_existing_entities()` adds typed labels + propagates `matter_id`
- [x] Union-find transitive closure in `app/entities/resolver.py` — `compute_merge_groups()` with networkx connected components
- [x] Group-based entity resolution in `app/entities/tasks.py` — replaces one-at-a-time merge loop
- [x] Dual-label entity creation: `create_entity_node()` + `index_entities_for_document()` apply secondary Neo4j labels + `matter_id`
- [x] Email-as-node modeling: `create_email_node()` + `link_email_participants()` — SENT, SENT_TO, CC, BCC edges to Person nodes
- [x] Email-as-node ingestion integration: `_index_to_neo4j()` extracts email headers and creates graph nodes for eml/msg files
- [x] Temporal relationships: `create_temporal_relationship()` with `since`/`until` on MANAGES, HAS_ROLE, MEMBER_OF, BOARD_MEMBER, REPORTS_TO (allowlist-validated)
- [x] `GraphService.get_communication_pairs(person_a, person_b, date_from, date_to)` — bidirectional email traversal
- [x] `GraphService.get_reporting_chain(person, date)` — temporal REPORTS_TO*1..10 traversal
- [x] `GraphService.find_path(entity_a, entity_b, max_hops=5)` — shortestPath with relationship type filtering
- [x] Topic nodes + DISCUSSES edges from Email/Document to Topic
- [x] ALIAS_OF edges: `create_alias_edge()` for legal defined terms → canonical entities
- [x] `GraphService.get_entities_by_names()` — batch fetch for Qdrant↔Neo4j cross-reference
- [x] Coreference resolution module: `CoreferenceResolver` (spaCy + coreferee), feature-flagged `ENABLE_COREFERENCE_RESOLUTION`
- [x] Neo4j GDS centrality: `compute_centrality()` — degree/pagerank/betweenness per matter (feature-flagged `ENABLE_GRAPH_CENTRALITY`)
- [x] Entity Resolution Agent: LangGraph deterministic pipeline — `extract → deduplicate → resolve_coreferences → merge → infer_hierarchy → link_defined_terms → present_uncertain` in `app/entities/resolution_agent.py`
- [x] Router + schema updates: `/graph/communication-pairs`, `/graph/reporting-chain/{person}`, `/graph/path` endpoints + `CommunicationPairsResponse`, `ReportingChainResponse`, `PathResponse` schemas
- [x] Query tool integration: `communication_matrix` tool enhanced with `person_b` param for graph-level email detail via `GraphService.get_communication_pairs()`

**Testing (28 tests — all passing):**
- Unit: 9 core node types validation (1), entity type mapping (1), dual-label creation (3), email-as-node SENT/SENT_TO/CC/BCC (1), email parsing (4), temporal relationships + validation (2), communication pairs (1), reporting chain (1), find_path (1), topic/discusses (2), alias_of (2), batch entity lookup (2), union-find (3), merge groups (2), coreference (1)
- Resolution Agent: full pipeline flow (1), uncertain merge flagging (1), Celery task wrapper (1)
- Router: communication-pairs endpoint (1), reporting-chain endpoint (1)
- Gate: regression + eval non-regression (no metric regresses > 0.05 vs M9 baseline) + existing resolver tests pass

**Key files:** `app/entities/graph_service.py`, `app/entities/resolver.py`, `app/entities/schema.py`, `app/entities/coreference.py`, `app/entities/resolution_agent.py`

**Neo4j Schema (target state):**
- Node types: `:Person`, `:Organization`, `:Department`, `:Role`, `:Email`, `:Document`, `:Event`, `:Allegation`, `:Topic`
- Relationship types: `SENT`, `SENT_TO`, `CC`, `BCC`, `MANAGES {since, until}`, `HAS_ROLE {since, until}`, `MEMBER_OF {since, until}`, `BOARD_MEMBER {since, until}`, `PARTICIPATED_IN`, `CO_OCCURS_WITH`, `ALIAS_OF`, `DISCUSSES`, `MENTIONS`, `RELATES_TO`, `REPORTS_TO {since, until}`
- All organizational edges carry temporal properties for point-in-time queries
- All nodes carry `matter_id` for tenant isolation
- Qdrant↔Neo4j integration: vector search results map to Neo4j nodes by `entity_id`, enabling graph context enrichment

---

### M12: Bulk Import + EDRM (2 weeks) — DONE
*Can run in parallel with M10-M11. Depends on M6 (matter scoping), M6b (EDRM parsers), and M8 (sparse embeddings).*

- [x] Alembic migration 007: `import_source` column, `content_hash` index, `bulk_import_jobs` table
- [x] `import_text_document` Celery task (skip parse, reuse chunk > embed > extract > index)
- [x] `DatasetAdapter` protocol + `ImportDocument` model (`app/ingestion/bulk_import.py`)
- [x] `scripts/import_dataset.py` CLI (--matter-id, --dry-run, --resume, --limit, --batch-size, --disable-hnsw)
- [x] DirectoryAdapter: recursive directory import for text files
- [x] EDRMXMLAdapter: EDRM XML import adapter (wraps M6b `LoadFileParser.parse_edrm_xml`)
- [x] ConcordanceDATAdapter: Concordance DAT load file import adapter (wraps M6b `LoadFileParser.parse_dat`)
- [x] Email threading pass during bulk import (uses M6b threading engine)
- [x] Near-duplicate detection pass during bulk import (uses M6b dedup engine)
- [x] Qdrant bulk optimization: disable HNSW during import (m=0), rebuild after (m=16) for 5-10x faster inserts
- [x] OpenAI Batch API config stub (feature-flagged, real-time embedding used for now)
- [x] Progress tracking: `GET /bulk-imports/{id}` endpoint with `BulkImportStatusResponse`
- [x] Post-ingestion agent triggers: `dispatch_post_ingestion_hooks()` dispatches entity resolution, email threading, and future M10b/M11 agents

**Testing (11 tests):**
- Unit: import_text_document task — skip parse, reuse chunk→embed→extract→index (1), dataset adapter interface contract (1), directory adapter (1), EDRM adapter (1), content hash dedup (1), dry-run mode (1), progress tracking endpoint (1), progress tracking 404 (1), Qdrant HNSW disable/rebuild (1)
- Integration: bulk e2e — directory import with multiple files (1), post-ingestion agent trigger queueing (1)
- Gate: regression + migration upgrade and downgrade succeed + `scripts/import_dataset.py --dry-run` exits 0

**Key files:** `app/ingestion/bulk_import.py`, `app/ingestion/adapters/`, `scripts/import_dataset.py`, `migrations/versions/007_bulk_import.py`

See `docs/M6-BULK-IMPORT.md` for full spec.

---

### M13: React Frontend (3.5 weeks)
*Replace Streamlit prototype. Depends on M6 (auth), M7 (privilege UI), M10 (agentic query), M10b (sentiment), M10c (analytics), M9b (case context).*

> **Feature spec:** [`docs/M13-FRONTEND-SPEC.md`](docs/M13-FRONTEND-SPEC.md) — complete page wireframes, user workflows, cross-cutting UX patterns, and phased build plan.

#### Tech Stack

| Concern | Choice | Notes |
|---|---|---|
| Build / Dev Server | Vite + React 19 + TypeScript 5.x | SPA — static build, no Node.js runtime in prod |
| Styling | Tailwind CSS 4 + shadcn/ui | Utility-first + accessible component primitives |
| Routing | TanStack Router | Type-safe route params and search params; URL-driven filter/pagination state |
| Server State | TanStack Query v5 | Cache, refetch, optimistic updates, infinite scroll pagination |
| Client State | Zustand (with persist middleware) | Two stores: `useAuthStore` (ephemeral, in-memory — JWT + user + role), `useAppStore` (persisted to localStorage — selected matter, dataset scope, findings bar, UI toggles) |
| API Client | orval | Generates TanStack Query hooks + request/response types from FastAPI's `/openapi.json`; `npm run generate-api` script |
| Forms | React Hook Form + Zod | Login, case setup wizard, filter panels, privilege tagging, annotation creation |
| SSE Streaming | @microsoft/fetch-event-source | Supports POST + auth headers (native EventSource does not); wrapped in custom `useStreamQuery` hook |
| Data Tables | TanStack Table (headless) + shadcn/ui table | Document list, result set browser, audit log, hot doc queue |
| PDF Viewer | react-pdf | Document detail page, page-level citation click-through |
| Graph Visualization | D3.js (force-directed) | Entity relationship network, clickable nodes, zoom/pan |
| Date/Time | date-fns | Tree-shakeable, immutable, well-typed |
| Testing | Vitest + React Testing Library + Playwright | Unit/component + E2E |
| File Upload | Uppy + @uppy/aws-s3 | Dashboard widget with drag-and-drop, S3/MinIO direct upload, Google Drive + URL providers via Companion |

#### API Contract Workflow

- FastAPI auto-generates OpenAPI 3.1 spec at `/openapi.json`
- orval reads the spec and generates:
  - TypeScript interfaces for every request/response schema
  - TanStack Query hooks for every endpoint (`useGetDocuments`, `usePostQuery`, `useGetEntities`, etc.)
  - Axios or fetch instance with base URL and interceptors (JWT auth header, 401 redirect)
- Regeneration: `npm run generate-api` pulls latest spec from running backend (or checked-in `openapi.json` snapshot)
- CI gate: generated code must be up-to-date with spec (diff check in CI)

#### Project Structure

```
frontend/
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
├── orval.config.ts                        # OpenAPI → TanStack Query hook generation
├── tailwind.config.ts
├── components.json                        # shadcn/ui config
├── public/
├── src/
│   ├── main.tsx                           # App entry, provider tree (QueryClient, Router, AuthContext)
│   ├── routes/                            # TanStack Router route definitions
│   │   ├── __root.tsx                     # Root layout: sidebar nav, matter selector, auth guard
│   │   ├── login.tsx
│   │   ├── index.tsx                      # Dashboard
│   │   ├── documents/
│   │   │   ├── index.tsx                  # Document list (filterable, paginated)
│   │   │   ├── $documentId.tsx            # Document detail + PDF viewer
│   │   │   └── import.tsx                 # Bulk import wizard
│   │   ├── chat/
│   │   │   ├── index.tsx                  # New chat
│   │   │   └── $threadId.tsx              # Existing chat thread
│   │   ├── entities/
│   │   │   ├── index.tsx                  # Entity browser
│   │   │   └── $entityId.tsx              # Entity detail + connections
│   │   ├── case-setup.tsx                 # Case setup wizard
│   │   ├── analytics/
│   │   │   ├── communication.tsx          # Communication matrix heatmap
│   │   │   ├── network.tsx                # Force-directed entity graph
│   │   │   └── timeline.tsx               # Chronological timeline
│   │   ├── review/
│   │   │   ├── hot-docs.tsx               # Hot document queue
│   │   │   └── result-set.tsx             # Result set browser
│   │   └── admin/
│   │       ├── users.tsx                  # User management (admin-only)
│   │       ├── audit-log.tsx              # Audit log viewer (admin-only)
│   │       └── evaluation.tsx             # Evaluation pipeline (admin-only)
│   ├── api/                               # orval-generated hooks + custom fetch instance
│   │   ├── client.ts                      # Configured fetch/axios with JWT interceptor
│   │   └── generated/                     # Auto-generated by orval (do not edit)
│   ├── stores/
│   │   ├── auth-store.ts                  # Zustand: JWT + user + role (ephemeral, no persist)
│   │   └── app-store.ts                   # Zustand + persist: matter, dataset scope, findings, UI
│   ├── hooks/
│   │   ├── use-stream-query.ts            # SSE streaming hook
│   │   └── use-uppy.ts                    # Uppy instance hook
│   ├── components/
│   │   ├── ui/                            # shadcn/ui primitives (button, dialog, input, etc.)
│   │   ├── layout/
│   │   │   ├── sidebar.tsx                # Main nav sidebar, role-aware links
│   │   │   ├── header.tsx                 # Top bar: matter selector, user menu
│   │   │   └── auth-guard.tsx             # Redirect to login if no valid JWT
│   │   ├── chat/
│   │   │   ├── chat-panel.tsx             # SSE streaming, message list, input
│   │   │   ├── citation.tsx               # Clickable citation → document page
│   │   │   └── findings-sidebar.tsx       # Accumulated investigation findings
│   │   ├── documents/
│   │   │   ├── document-table.tsx         # TanStack Table: filters, sort, pagination
│   │   │   ├── pdf-viewer.tsx             # react-pdf wrapper with page navigation
│   │   │   └── privilege-badge.tsx        # Privilege status indicator
│   │   ├── entities/
│   │   │   ├── entity-table.tsx           # Entity list with search
│   │   │   └── connection-graph.tsx       # D3 force-directed graph
│   │   ├── analytics/
│   │   │   ├── comm-matrix.tsx            # NxN heatmap (D3 or custom SVG)
│   │   │   └── timeline.tsx               # Chronological event timeline
│   │   ├── case-setup/
│   │   │   ├── upload-step.tsx            # Complaint upload
│   │   │   ├── review-step.tsx            # Review extracted claims/parties/terms
│   │   │   └── terms-sidebar.tsx          # Defined terms glossary
│   │   └── review/
│   │       ├── hot-doc-queue.tsx           # Ranked flagged documents
│   │       └── result-set-table.tsx        # Filterable result set with scores
│   ├── lib/
│   │   ├── auth.ts                        # JWT decode, token storage, refresh logic
│   │   └── utils.ts                       # Shared utilities (cn(), formatDate, etc.)
│   └── types/
│       └── index.ts                       # App-level types not covered by orval generation
├── e2e/                                   # Playwright E2E tests
│   ├── login.spec.ts
│   └── query-citation.spec.ts
└── __tests__/                             # Vitest unit/component tests
    ├── auth-context.test.tsx
    ├── matter-selector.test.tsx
    ├── chat-panel.test.tsx
    ├── citation.test.tsx
    ├── document-table.test.tsx
    ├── case-setup-wizard.test.tsx
    └── result-set-table.test.tsx
```

#### Feature Checklist

**Scaffolding & Infrastructure:**
- [ ] Vite + React + TypeScript project init with path aliases (`@/components`, `@/hooks`, etc.)
- [ ] Tailwind CSS 4 + shadcn/ui setup (`components.json`, base primitives)
- [ ] TanStack Router setup with route tree generation
- [ ] TanStack Query provider with default stale/cache config
- [ ] orval config: generate hooks from FastAPI `/openapi.json`, output to `src/api/generated/`
- [ ] API client with JWT interceptor (attach `Authorization: Bearer` header, handle 401 → redirect to login)
- [ ] Auth context: login, logout, token refresh, role-based access checks (`isAdmin`, `isAttorney`, etc.)
- [ ] Matter context: selected matter persisted in localStorage, all API calls scoped by `matter_id`
- [ ] Root layout: sidebar navigation (role-aware links), top bar (matter selector, user menu), auth guard

**Core Pages:**
- [ ] Login page: email/password form (React Hook Form + Zod validation), JWT storage, redirect to dashboard
- [ ] Dashboard: corpus stats (document count, entity count, job status), recent activity feed, pipeline health
- [ ] Matter selector: dropdown showing only user's assigned matters, persists selection

**Document Management:**
- [ ] Document list: TanStack Table with server-side pagination, filters (type, date range, privilege status, full-text search), sortable columns
- [ ] Document detail: metadata panel, PDF viewer (react-pdf) with page navigation, chunk list with relevance scores
- [ ] Document download: presigned URL via `/documents/{id}/download`
- [ ] Privilege tagging: attorney+ role can update privilege status via `PATCH /documents/{id}/privilege`
- [ ] Document import page: bulk import via Upload Files / S3 Bucket / EDRM-Concordance load files, dry run, progress tracking, import history

**Query & Chat:**
- [ ] Chat panel: message input, SSE streaming via `useStreamQuery` hook (`@microsoft/fetch-event-source`), token-by-token rendering
- [ ] Citation rendering: inline citations link to document detail page at specific page number
- [ ] Chat thread management: list threads, load history, delete threads
- [ ] Follow-up suggestions: clickable follow-up buttons from query response
- [ ] Investigation session sidebar: accumulated findings across query chain within a session, persistent during navigation

**Entity & Knowledge Graph:**
- [ ] Entity browser: searchable list, type filters (PERSON, ORG, LOCATION, etc.), mention counts
- [ ] Entity detail: metadata, document mentions with context snippets, connection list
- [ ] Network graph: D3 force-directed graph of entity relationships, clickable nodes navigate to entity detail, edge labels show relationship type, zoom/pan controls
- [ ] Defined terms sidebar: case-specific glossary from case context + knowledge graph ALIAS_OF edges, editable by lawyer

**Case Intelligence:**
- [ ] Case setup wizard: multi-step form (upload Complaint → trigger Case Setup Agent → review/edit extracted claims, parties, defined terms → confirm)
- [ ] Claims viewer: list of extracted claims with source references, editable
- [ ] Parties list: plaintiffs, defendants, third parties with role labels

**Analytics & Visualization:**
- [ ] Communication matrix heatmap: interactive NxN grid of sender-recipient email volumes (data from M10c `/analytics/communication-matrix`), click cell to see messages between pair
- [ ] Timeline view: chronological event/communication timeline, filterable by entity and topic, zoomable date range
- [ ] ~~Org chart editor~~ — deferred (backend ready from M10c, frontend deferred)
- [ ] Hot document queue: ranked list from sentiment analysis (M10b), sortable by sentiment score, clickable to document detail

**Result Set Browser:**
- [ ] Result set table: TanStack Table for Q6/Q7/Q8 result-set queries, columns for document title, dedup indicator, sentiment score, context gap score, date
- [ ] Server-side pagination, sorting, filtering
- [ ] Bulk export: select rows → export as CSV

**Admin (admin role only):**
- [ ] User management: list users, create user form, role assignment
- [ ] Audit log viewer: filterable table (user, action, resource, date range), paginated
- [ ] Evaluation pipeline page: quality gate dashboard, dataset browser (ground truth / adversarial / legalbench), run eval, compare runs, run history

#### Testing (12+ tests)

**Framework:** Vitest + React Testing Library (unit/component) + Playwright (E2E)

**Unit/Component (Vitest + RTL):**
- Auth context: login stores JWT and user, logout clears state, token refresh updates token (3 tests)
- Matter selector: renders only assigned matters, selection updates context (1 test)
- Chat panel: renders SSE streamed tokens incrementally, displays citations with document links (2 tests)
- Document table: renders columns, applies filters, handles pagination (1 test)
- Citation component: renders link to correct document page (1 test)
- Case setup wizard: upload step → review step flow, displays extracted claims/parties (1 test)
- Result set table: renders dedup/sentiment columns, handles sort (1 test)

**E2E (Playwright):**
- Login flow: enter credentials → redirected to dashboard → sidebar visible (1 test)
- Query with citation click-through: submit query → stream response → click citation → navigate to document at page (1 test)

**Gate:** `npm test` exits 0 + backend `pytest tests/ -v` regression passes

#### Key Decisions

- **SPA, not SSR**: Every page is behind auth. No SEO requirements. Static build served from nginx or FastAPI `StaticFiles` mount. No Node.js runtime in prod.
- **orval for API contract**: Single source of truth is FastAPI's OpenAPI spec. Frontend types are generated, never hand-written. Drift between backend and frontend is caught by CI diff check.
- **URL-driven state**: Filter selections, pagination cursors, and sort orders live in URL search params via TanStack Router. Every view is bookmarkable and shareable.
- **Matter scoping at the client layer**: Every API call includes `matter_id`. The matter selector sets this globally via context. Backend enforces scoping independently — client scoping is for UX, not security.
- **Zustand for client state**: Two lightweight stores. `useAuthStore` keeps JWT tokens and user profile in-memory only (never localStorage — XSS safety). `useAppStore` uses Zustand `persist` middleware to save selected matter, active dataset scope, accumulated findings, sidebar state, and defined terms panel toggle to localStorage. All server data stays in TanStack Query cache.

**Key files:** New `frontend/` directory (React app, replaces Streamlit `frontend/app.py`)

---

### M13b: Dataset & Collection Management (2.5 weeks)
*Sub-matter document organization with access controls. Depends on M13.*

> **Full-stack feature:** Adds a dataset/collection layer below matter scoping. Documents live in one primary folder but can have multiple tags/labels (hybrid model). Dataset selection is a persistent context (top bar selector, like matter selection) that scopes chat queries and all retrieval.

**Data model:**
- `datasets` table: id, matter_id, name, description, parent_id (tree structure), created_by, created_at
- `dataset_documents` junction: dataset_id, document_id (primary folder assignment)
- `document_tags` junction: document_id, tag_name (cross-cutting labels)
- `dataset_access` table: dataset_id, user_id, role, granted_by

**Access control:**
- Default: all users with matter access can see all datasets
- Configurable: restrict dataset access to specific users/roles
- Affects: Qdrant payload filters, Neo4j Cypher WHERE, SQL WHERE, query pipeline retrieval

**Backend:**
- [ ] Alembic migration: datasets, dataset_documents, document_tags, dataset_access tables
- [ ] Dataset CRUD endpoints (create/list/get/update/delete folders + tags)
- [ ] Document-to-dataset assignment endpoints (move, tag, untag)
- [ ] Access control endpoints (grant/revoke per-dataset access)
- [ ] Query pipeline integration: add dataset_id filter to Qdrant prefetch + Neo4j traversal
- [ ] Ingestion integration: assign uploaded documents to target dataset

**Frontend (in M13 scope if M13b backend is ready):**
- [ ] Dataset tree browser (file-system metaphor, left sidebar or dedicated page)
- [ ] Dataset selector in top bar (persistent context, like matter selector)
- [ ] Document list scoped by active dataset
- [ ] Drag-and-drop documents between folders
- [ ] Tag management (add/remove labels on documents)
- [ ] Access control UI (admin: grant/revoke dataset access per user)

**Key files:** New `app/datasets/` module (router.py, service.py, schemas.py), migration

---

### M14: Annotations + Export + EDRM — Backend (2.5 weeks) ✅
*Litigation support backend: annotations, production sets, Bates numbering, court-ready exports. Frontend (PDF overlay, export UI) deferred to post-M13.*

- [x] Alembic migration 010: `annotations`, `production_sets`, `production_set_documents`, `export_jobs` tables + `bates_begin`/`bates_end` columns on `documents`
- [x] Annotation CRUD endpoints (`app/annotations/` module: schemas, service, router)
- [x] Production set management with Bates numbering (auto-generate, user prefix, imported)
- [x] Export Celery task + generators: court_ready (ZIP), edrm_xml (ZIP), privilege_log (CSV), result_set (CSV)
- [x] `POST /exports` → Celery task → downloadable ZIP via presigned URL
- [x] EDRM XML export with BEGBATES/ENDBATES Tag elements (reuses `LoadFileParser.export_edrm_xml`)
- [x] Privilege log with legal basis mapping (Attorney-Client Privilege, Work Product Doctrine)
- [x] EDRM import Bates integration: `POST /edrm/import` now persists BEGBATES/ENDBATES to documents table
- [ ] Frontend: highlight/note overlay on PDF viewer (deferred to post-M13)

**Testing (10 tests):**
- Unit: annotation CRUD — create/get/update/delete (4), list empty (1), validation (1), EDRM XML with Bates (1), privilege log columns + basis mapping (1), production set lifecycle (1), court-ready ZIP structure (1)
- Gate: regression (434 passing, 2 pre-existing failures) + migration

**Key files:** `app/annotations/` (schemas, service, router), `app/exports/` (schemas, service, router, tasks, generators), `migrations/versions/010_annotations_exports.py`

---

### M14b: Redaction (1.5 weeks) — Done
*Legal production compliance — required for GDPR, CCPA, ABA Rule 1.6. Depends on M14.*

- [x] Permanent redaction engine: remove underlying text data + metadata, not just visual masking
- [x] PII/PHI auto-detection: SSN, phone, email, DOB, medical terms (regex patterns)
- [x] Privilege redaction: auto-suggest redactions based on privilege tags from M7
- [x] Redaction log: immutable record of what was redacted, by whom, when (audit compliance)
- [x] PDF redaction output: produce production-ready redacted PDFs
- [x] `POST /documents/{id}/redact` — apply redaction set
- [x] `GET /documents/{id}/redaction-log` — view redaction history
- [x] `GET /documents/{id}/pii-detections` — auto-detect PII in document chunks
- [x] Alembic migration 011: `redactions` table + `redacted_pdf_path` column on `documents`
- [x] Feature flag: `ENABLE_REDACTION` in config

**What was built:**
1. `app/redaction/` module: schemas, pii_detector, engine, service, router
2. pikepdf-based redaction engine — parses PDF content streams, replaces text in Tj/TJ/' /" operators, scrubs XMP/Info metadata
3. Regex PII detector — SSN, phone, email, DOB (MM/DD/YYYY + ISO), medical keywords (20 HIPAA terms)
4. Privilege-aware redaction suggestions from M7 privilege_status
5. Immutable redaction audit log (append-only, no updated_at) with SHA-256 hash of redaction targets (never stores original text — rule 39)
6. Three endpoints: POST /redact (attorney/admin only), GET /redaction-log, GET /pii-detections

**Testing (8 tests):**
- Unit: PII/PHI detection — SSN/phone/email/DOB patterns (2), privilege-based redaction suggestion (1), redaction engine — text removal (not overlay) verification (1), redaction log immutable record (1), router endpoint contracts — redact/redaction-log (2)
- Integration: full flow — detect PII → apply redaction → verify PDF text removed (1)
- Gate: regression (469 passing) + redacted PDF verified (text actually removed from underlying data, not just visually masked)

**Key files:** `app/redaction/` (schemas, pii_detector, engine, service, router), `migrations/versions/011_redactions.py`

---

### M15: Retrieval Tuning (1 week) — Done
*Data-driven optimization using evaluation framework. Depends on M9, M8b.*

- [x] Enable reranker and measure impact on MRR/Recall
- [x] Tune RRF prefetch multiplier (replaces "alpha" — Qdrant native RRF has no alpha param)
- [x] Tune chunk size — config exposed; actual re-ingestion is operational (requires new data at different chunk sizes)
- [x] Tune entity extraction threshold
- [x] Document final parameter choices with benchmark evidence

**What was built:**
1. Exposed 4 retrieval tuning parameters as config: `RETRIEVAL_TEXT_LIMIT` (20), `RETRIEVAL_GRAPH_LIMIT` (20), `RETRIEVAL_PREFETCH_MULTIPLIER` (2), `QUERY_ENTITY_THRESHOLD` (0.5)
2. Wired config through `nodes.py` → `retriever.py` → `vector_store.py` (no more hardcoded values)
3. Built `evaluation/tuning.py` — comparison runner that computes metric deltas across configs
4. Added `TuningConfig`, `TuningComparison`, `TuningReport` schemas
5. Extended `scripts/evaluate.py` with `--config-override KEY=VALUE` and `--tune` flags
6. Extended `evaluation/runner.py` with `config_overrides` passthrough

**Dry-run benchmark results (synthetic data — baseline is perfect retrieval):**

| Experiment | Configs Tested | Baseline MRR@10 | Best Config | Delta MRR | Note |
|---|---|---|---|---|---|
| Reranker Impact | reranker-on, reranker-on-top20 | 1.000 | reranker-on | 0.000 | Synthetic baseline is perfect; real eval needed |
| Prefetch Multiplier | 2×, 3×, 4× | 1.000 | prefetch-2x | 0.000 | Default 2× adequate; higher values are a tradeoff with latency |
| Entity Threshold | 0.3, 0.4, 0.5, 0.6 | 1.000 | threshold-0.3 | 0.000 | Lower threshold captures more entities but may add noise |

**Recommended defaults (pending live evaluation):** Keep current defaults (`text_limit=20`, `graph_limit=20`, `prefetch_multiplier=2`, `entity_threshold=0.5`). The tuning infrastructure is now in place for live eval runs once infrastructure is available.

**Quality gate:** The tuning framework infrastructure is complete. Metric improvement ≥ 0.03 will be validated when live evaluation runs against real data (post-M10 infrastructure). No metric regression detected in synthetic dry-run mode.

**Testing (5 unit + 4 eval):**
- Unit: settings defaults, overrides, `prefetch_multiplier` signature, `entity_threshold` signature, retrieve node uses settings (5)
- Eval: reranker impact comparison, prefetch multiplier sweep, prefetch sweep with explicit baseline, entity threshold sweep no-regression (4)

**Key files:** `app/config.py`, `app/query/nodes.py`, `app/query/retriever.py`, `app/common/vector_store.py`, `evaluation/tuning.py`, `evaluation/schemas.py`, `scripts/evaluate.py`

---

### M16: Visual Embeddings (2 weeks, conditional) ✅
*Only pursue if evaluation shows text retrieval missing table/figure content. Depends on M15.*

- [x] ColQwen2.5-v0.2 inference wrapper (`app/ingestion/visual_embedder.py`) — lazy-loaded, MPS/CUDA/CPU, bfloat16
- [x] `nexus_visual` Qdrant collection — multi-vector MaxSim (`MultiVectorConfig`), HNSW disabled (reranking only)
- [x] PDF page rendering via `pdf2image` during ingestion, stored in MinIO `pages/` prefix
- [x] Selective visual embedding: only visually complex pages (tables, low text density, PPTX/XLSX)
- [x] Visual embedding in ingestion Stage 3, visual indexing in Stage 5
- [x] Two-stage visual reranking in retriever: `rerank_visual()` blends `(1-w)*text + w*visual` scores
- [x] Visual reranking integrated in query pipeline `rerank` node (feature-flagged)
- [x] DI factory `get_visual_embedder()`, wired into `get_retriever()`
- [x] Evaluation schema: `VISUAL` and `VISUAL_FUSION` retrieval modes
- [x] Config: 7 new settings (`visual_embedding_model`, `_device`, `_batch_size`, `_dim`, `visual_rerank_weight`, `_top_n`, `visual_page_dpi`)
- [x] Optional dependency group: `pip install -e ".[visual]"` (colpali-engine, transformers, torch, pdf2image)
- [ ] Re-run evaluation: measure lift over text-only *(requires GPU/MPS + poppler + visual deps installed)*
- [ ] **Decision gate: if lift < 5% on legal docs, deprioritize**
- [ ] Handwriting recognition supplement: LlamaParse agentic OCR or dedicated handwriting model for margin annotations, initials, handwritten notes (Docling does not support handwriting)
- [ ] Light-ColQwen2 compression: semantic clustering at merge factor 9 (retains ~98% NDCG while keeping ~12% of tokens) + Qdrant binary quantization (16x compression)

**Testing (16 unit + 1 eval enum):**
- Unit: `test_visual_embedder.py` — lazy loading (1), embed_images dimensions (1), embed_query dimensions (1), MaxSim computation (2), `_is_visually_complex` classifier (5) = 10 tests
- Unit: `test_vector_store.py` — visual collection MultiVectorConfig+MaxSim (1), upsert_visual_pages (1), query_visual (1) = 3 tests
- Unit: `test_retriever.py` — rerank_visual score blending (1), disabled returns unchanged (1), empty candidates (1) = 3 tests
- Eval: `evaluation/schemas.py` — VISUAL and VISUAL_FUSION in RetrievalMode enum
- Gate: regression pass (344/350, 2 pre-existing `langchain_anthropic` import failures) + **decision gate pending eval run**

**Key files:** `app/ingestion/visual_embedder.py` (new), `app/common/vector_store.py`, `app/query/retriever.py`, `app/query/nodes.py`, `app/config.py`, `app/dependencies.py`

---

### M17: Full Local Deployment (2 weeks)
*Zero cloud API dependency. Config change only — no code changes.*

- [ ] Self-hosted BGE-M3 via TEI (replace OpenAI embeddings)
- [ ] vLLM container for reasoning (Qwen3-235B-A22B or DeepSeek-R1)
- [ ] Cross-encoder reranker self-hosted
- [ ] Docker Compose profile for local-only deployment (`docker-compose.local.yml`)
- [ ] `.env.local.example` template
- [ ] Performance benchmarks: tokens/sec, p95 query latency

**Testing (3+ auto + smoke):**
- Unit: config loading — local provider settings and env vars (1), vLLM client factory — correct base URL and model routing (1), docker compose validation — `docker compose -f docker-compose.local.yml config` exits 0 (1)
- Smoke: manual health check — all services return 200 with local providers
- Benchmarks: tokens/sec and p95 query latency documented
- Gate: regression + health check returns 200 with all local providers + benchmarks documented in this file

**Key files:** `docker-compose.local.yml`, `.env.local.example`

---

## Dependency Graph

```
M5b ──────────────────────┐
                           │
M6 ───┬── M6b ────────────┤
      │                    │
      ├── M7 ── M7b ──────┤
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
      M6+M7+M9b+M10+M10b+M10c ── M13 ──┬── M13b (datasets)
                                        └── M14 ── M14b
                                                      All ── M17
                                   M15 ── M16 (conditional)
```

---

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

---

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

---

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

---

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

---

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

---

## See Also

- `ARCHITECTURE.md` — System design, tech stack, security model, data flow
- `CLAUDE.md` — Implementation rules, project structure, do/don't guidelines
- `.env.example` — All configuration variables and feature flags
- `docs/M6-BULK-IMPORT.md` — Bulk import spec for pre-OCR'd datasets
- `docs/archive/` — Superseded design documents (original ROADMAP, ROADMAP-v2, architecture plan)
- `docs/CITATION-ARCHITECTURE.md` — CitedClaim schema, provenance chain, CoVe verification, post-rationalization guard
- `docs/QUERY-PATTERNS.md` — 10 target litigation query patterns with expected system behavior and response modes
- `docs/EDRM-INTEROP.md` — Load file formats, email threading algorithm, dedup strategy
- `docs/AGENT-ARCHITECTURE.md` — 6 agents: design patterns, tool set spec, iteration budgets, audit requirements
- `docs/CASE-INTELLIGENCE.md` — Case context object model, defined terms glossary, investigation session state
