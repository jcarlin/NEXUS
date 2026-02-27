# NEXUS Roadmap

> Multimodal RAG Investigation Platform for Legal Document Intelligence

**Last updated:** 2026-02-26

---

## Milestone Summary

| # | Milestone | Status | Tests | Duration | Dependencies |
|---|---|---|---|---|---|
| M0 | Skeleton + Infrastructure | Done | 8 | — | — |
| M1 | Single Doc Ingestion | Done | 23 | — | M0 |
| M2 | Query Pipeline (LangGraph) | Done | 53 | — | M1 |
| M3 | Multi-Format + Entity Resolution | Done | 44 | — | M1 |
| M4 | Chat + Streamlit + Doc Browsing | Done | 15 | — | M2, M3 |
| M5 | Production Hardening (Core) | Done | 16 | — | M4 |
| M5b | Tests + Reranker | Done | 27 | — | — |
| M6 | Auth + Multi-Tenancy | Done | 15 | — | — |
| M7 | Audit + Privilege | Done | 17 | — | M6 |
| M8 | Retrieval Infrastructure | Done | 8 | — | — (parallel w/ M7) |
| M9 | Evaluation Framework | TODO | — | 1.5 weeks | M8 |
| M10 | Agentic Query Pipeline | TODO | — | 2.5 weeks | M8, M9 |
| M11 | Knowledge Graph Enhancement | TODO | — | 1.5 weeks | M10 |
| M12 | Bulk Import | TODO | — | 1.5 weeks | M6, M8 (parallel w/ M10-11) |
| M13 | React Frontend | TODO | — | 3 weeks | M6, M7, M10 |
| M14 | Annotations + Export | TODO | — | 2 weeks | M13 |
| M15 | Retrieval Tuning | TODO | — | 1 week | M9, M10, M12 |
| M16 | Visual Embeddings | TODO | — | 2 weeks | M15 (conditional) |
| M17 | Full Local Deployment | TODO | — | 2 weeks | All |

**Total tests: 227 passing** (as of M7 completion)

**Estimated total: ~23 weeks solo, ~18 weeks with 2 developers** (M7+M8 parallel, M12 parallel with M10-11)

---

## Ordering Principles

1. Measure before optimize (eval before retrieval tuning)
2. Secure before share (auth before multi-user features)
3. Infrastructure before features (sparse vectors before agentic query)
4. Each milestone delivers standalone value
5. Dependencies flow forward only
6. Commit messages must not mention Anthropic or Claude Code (no `Co-Authored-By` lines, no tool attribution)

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

### M2: Query Pipeline (LangGraph)
- `POST /query` — synchronous query with full response
- `POST /query/stream` — SSE streaming (sources before generation, token-by-token)
- LangGraph 9-node state graph: classify > rewrite > retrieve > rerank > check_relevance > reformulate (conditional) > graph_lookup > synthesize > follow_ups
- HybridRetriever: Qdrant dense + Neo4j graph traversal
- Chat persistence in PostgreSQL (JSONB for source_docs/entities)
- `GET /chats`, `GET /chats/{thread_id}`, `DELETE /chats/{thread_id}`

### M3: Multi-Format + Entity Resolution
- Parsers for EML, MSG, CSV, RTF, TXT
- ZIP extraction with child job dispatch per contained file
- `POST /ingest/batch` — multi-file upload
- Email-aware chunking (headers as metadata, attachments as sub-documents)
- Entity resolution: rapidfuzz (threshold 85) + embedding cosine (>0.92)
- Instructor + Claude relationship extraction (feature-flagged)
- Working entity/graph API endpoints

### M4: Chat + Streamlit + Doc/Entity Browsing
- DocumentService CRUD with raw SQL
- `GET /documents` (list), `GET /documents/{id}` (detail), `GET /documents/{id}/preview`, `GET /documents/{id}/download`
- Streamlit 3-page dashboard: Chat, Documents, Entities
- DocumentDetail Pydantic schema
- Frontend optional deps in pyproject.toml

### M5: Production Hardening (Core)
- PostgresCheckpointer for multi-turn LangGraph state persistence
- Streaming refactor (`graph.astream` + `get_stream_writer`)
- MinIO webhook-driven ingestion (`POST /ingest/webhook`)
- Redis sliding-window rate limiting
- structlog with contextvars (request_id, task_id, job_id)
- Configurable embedding batch size

### M5b: Tests + Reranker
- `bge-reranker-v2-m3` cross-encoder reranker (`app/query/reranker.py`) — feature-flagged via `ENABLE_RERANKER`
- Lazy-loaded `CrossEncoder` with MPS/CUDA/CPU auto-detection (follows `EntityExtractor` pattern)
- Rerank node updated: cross-encoder when enabled, score-based sort fallback when disabled or on failure
- DI singleton `get_reranker()` returns `None` when flag is off (no `sentence-transformers` import)
- Config: `reranker_model`, `reranker_top_n` settings added
- Fixed pre-existing failing test (`test_query_stub_returns_not_implemented` → `test_query_requires_body`)
- 8 reranker unit tests, 3 feature-flag node tests
- 17 integration tests: ingest→query pipeline (5), SSE streaming E2E (5), error recovery (7)

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
- 17 tests: privilege CRUD (4), privilege filtering (3), Qdrant must_not filter (1), Neo4j Cypher filter (1), audit middleware (5), admin endpoint (2), helper functions (1)

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

---

## Next Up

### M9: Evaluation Framework (1.5 weeks)
*Measure before you optimize. Must come before retrieval tuning and agentic query.*

- [ ] Ground-truth Q&A dataset (50-100 questions with expected answers + source documents)
- [ ] Retrieval metrics: MRR@10, Recall@10, NDCG@10
- [ ] Answer quality metrics: faithfulness (no hallucination), relevance, citation accuracy
- [ ] `scripts/evaluate.py` CLI — runs full pipeline, reports metrics
- [ ] Baseline numbers documented (regression gate for query pipeline changes)
- [ ] Optional: CI integration for automated evaluation

**Key files:** New `evaluation/` directory, `scripts/evaluate.py`

---

## Future

### M10: Agentic Query Pipeline (2.5 weeks)
*Replace the fixed 8-node chain with an adaptive tool-use agent loop. Depends on M8 (hybrid retrieval) and M9 (evaluation baselines).*

- [ ] Refactor `app/query/graph.py`: classify_and_plan → execute_action → assess_sufficiency → synthesize
- [ ] Structured classification output (Instructor): query_type, complexity, strategy, sub_queries, max_iterations
- [ ] Tool-use dispatch in execute_action: retrieve_text, retrieve_graph_*, rerank, decompose
- [ ] LLM-based sufficiency assessment (replaces avg-score threshold)
- [ ] Structured `SynthesisOutput` with `CitedClaim` objects
- [ ] Query expansion for analytical/exploratory queries (3 reformulations)
- [ ] Max iteration hard cap (1-3 based on complexity classification)
- [ ] Evaluation comparison: agentic vs. baseline linear pipeline
- [ ] ~15 tests

**Key files:** `app/query/graph.py`, `app/query/nodes.py`, `app/query/schemas.py`, `app/query/prompts.py`

---

### M11: Knowledge Graph Enhancement (1.5 weeks)
*Multi-hop traversal, temporal queries, and entity resolution fix. Depends on M10.*

- [ ] New Neo4j node type: `:Event` (id, description, date, location, participants, matter_id)
- [ ] New edges: `PARTICIPATED_IN`, `CO_OCCURS_WITH`, `ALIAS_OF`
- [ ] `GraphService.get_entity_neighborhood(name, hops=2)` — multi-hop BFS
- [ ] `GraphService.find_path(entity_a, entity_b, max_hops=5)` — shortest path
- [ ] `GraphService.get_temporal_connections(name, date_from, date_to)` — time-bounded
- [ ] `GraphService.compute_co_occurrences(matter_id, min_count=3)` — batch edge creation
- [ ] Union-find transitive closure in `app/entities/resolver.py`
- [ ] ~10 tests

**Key files:** `app/entities/graph_service.py`, `app/entities/resolver.py`, `app/entities/extractor.py`

---

### M12: Bulk Import (1.5 weeks)
*Can run in parallel with M10-M11. Depends on M6 (matter scoping) and M8 (sparse embeddings).*

- [ ] Alembic migration: content hash index for dedup
- [ ] `import_text_document` Celery task (skip parse, reuse chunk > embed > extract > index)
- [ ] Dataset adapter interface (generic: load from directory, CSV, JSON, HuggingFace)
- [ ] `scripts/import_dataset.py` CLI (--matter-id, --dry-run, --resume, --limit, --batch-size)
- [ ] At least 1 working adapter (recursive directory import for PDF/text files)
- [ ] ~10 tests

**Key files:** `app/ingestion/bulk_import.py`, `scripts/import_dataset.py`, Alembic migration

See `docs/M6-BULK-IMPORT.md` for full spec.

---

### M13: React Frontend (3 weeks)
*Replace Streamlit prototype. Depends on M6 (auth), M7 (privilege UI), M10 (agentic query).*

- [ ] Vite + React + TypeScript + Tailwind + shadcn/ui
- [ ] Auth flow: login page, JWT management, role-aware navigation
- [ ] Matter selector: users see only their assigned case matters
- [ ] Dashboard: corpus stats, recent activity, pipeline status
- [ ] Document list with filters (type, date range, privilege status, full-text search)
- [ ] Document detail page with PDF viewer (react-pdf)
- [ ] "Ask the Evidence" chat panel: SSE streaming, citations with document links, follow-up buttons
- [ ] Entity browser: search, detail page with connections and document mentions

**Key files:** New `frontend/` directory (React app, replaces Streamlit `frontend/app.py`)

---

### M14: Annotations + Export (2 weeks)
*Features that make it a real litigation support tool. Depends on M13.*

- [ ] Alembic migration: `annotations` table
- [ ] Annotation CRUD endpoints
- [ ] Frontend: highlight/note overlay on PDF viewer
- [ ] Court-ready export: document production packages (PDF bundles, privilege log, citation index)
- [ ] `POST /exports` → Celery task → downloadable ZIP
- [ ] ~8 tests

**Key files:** New `app/annotations/` module, export Celery task

---

### M15: Retrieval Tuning (1 week)
*Data-driven optimization using evaluation framework. Depends on M9, M10, M12.*

- [ ] Enable reranker and measure impact on MRR/Recall
- [ ] Tune RRF alpha parameter using evaluation set
- [ ] Tune chunk size (try 256 and 1024, measure impact)
- [ ] Tune entity extraction threshold
- [ ] Document final parameter choices with benchmark evidence

**Key files:** `app/query/nodes.py`, `app/config.py`, `evaluation/`

---

### M16: Visual Embeddings (2 weeks, conditional)
*Only pursue if evaluation shows text retrieval missing table/figure content. Depends on M15.*

- [ ] ColQwen2.5-v0.2 inference setup (requires GPU)
- [ ] `nexus_visual` Qdrant collection activation
- [ ] Page image extraction during ingestion (stored in MinIO `pages/` prefix)
- [ ] Multi-modal fusion in retrieval pipeline
- [ ] Re-run evaluation: measure lift over text-only
- [ ] **Decision gate: if lift < 5% on legal docs, deprioritize**

**Key files:** `app/ingestion/embedder.py`, `app/query/retriever.py`, `app/config.py`

---

### M17: Full Local Deployment (2 weeks)
*Zero cloud API dependency. Config change only — no code changes.*

- [ ] Self-hosted BGE-M3 via TEI (replace OpenAI embeddings)
- [ ] vLLM container for reasoning (Qwen3-235B-A22B or DeepSeek-R1)
- [ ] Cross-encoder reranker self-hosted
- [ ] Docker Compose profile for local-only deployment (`docker-compose.local.yml`)
- [ ] `.env.local.example` template
- [ ] Performance benchmarks: tokens/sec, p95 query latency

**Key files:** `docker-compose.local.yml`, `.env.local.example`

---

## Dependency Graph

```
M5b ─────────────┐
                  │
M6 ───┬── M7 ────┤
      │          │
      │   M8 ───┤──── M9 ───┬── M10 ── M11
      │   │     │           │
      │   └─────┤── M12 ────┤
      │         │           │
      └── M7 ──┤           └── M15 ── M16
               │
      M6+M7+M10 ── M13 ── M14
                                   All ── M17
```

---

## See Also

- `ARCHITECTURE.md` — System design, tech stack, security model, data flow
- `CLAUDE.md` — Implementation rules, project structure, do/don't guidelines
- `.env.example` — All configuration variables and feature flags
- `docs/M6-BULK-IMPORT.md` — Bulk import spec for pre-OCR'd datasets
- `docs/archive/` — Superseded design documents (original ROADMAP, ROADMAP-v2, architecture plan)
