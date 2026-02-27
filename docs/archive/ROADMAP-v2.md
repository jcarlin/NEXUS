# NEXUS Roadmap v2

> Multimodal RAG Investigation Platform for Legal Document Intelligence

---

## Part 1: Honest Evaluation

### What You're Building

NEXUS sits squarely in the **eDiscovery / litigation support** vertical — a $15B+ legal tech market dominated by Relativity, Everlaw, Reveal, and Logikcull. The core value proposition is: **ingest massive heterogeneous document collections, extract structured intelligence (entities, relationships, timelines), and let investigators/attorneys query the corpus with cited, auditable answers.**

This is a real, validated market need. Law firms and investigative teams spend thousands of billable hours on manual document review. A well-built RAG system that can surface "show me all communications between Person X and Person Y about Topic Z between 2005-2010" with citations is genuinely valuable.

### The Two-Vision Problem

The project has **two competing architecture documents** describing fundamentally different systems:

| Dimension | Current Implementation (CLAUDE.md) | Architecture Plan (NEXUS-architecture-plan.md) |
|---|---|---|
| **Vector DB** | Qdrant (multi-vector, RRF fusion) | pgvector (simpler, fewer moving parts) |
| **Graph DB** | Neo4j + Graphiti | PostgreSQL relational (persons/connections tables) |
| **Auth** | None | JWT + RBAC (4 roles) |
| **Multi-tenancy** | None | Case matters with user assignment |
| **Privilege** | None | Full privilege tagging workflow |
| **Audit** | None | audit_log table + middleware |
| **Document parsing** | Docling (MIT, multi-format) | PyMuPDF + pytesseract |
| **NER** | GLiNER (zero-shot, 50ms/chunk) | DeepSeek two-tier extraction |
| **Frontend** | Streamlit (prototype) | React + TypeScript + shadcn/ui |
| **Entity model** | Neo4j nodes (12 types) | PostgreSQL persons table (person-centric) |
| **Orchestration** | LangGraph state graph (8 nodes) | Simple retrieval + LLM call |

**This is the core tension.** The current implementation has better technology choices but no enterprise features. The architecture plan has the right enterprise features but proposes weaker technology.

### What's Right (Keep These)

1. **Qdrant over pgvector** — Correct call. Qdrant's native RRF fusion, multi-vector support (for future ColQwen2.5), and metadata filtering outperform pgvector at scale. pgvector struggles past ~1M vectors and can't do sparse+dense fusion natively.

2. **LangGraph for query orchestration** — The 8-node state graph with conditional relevance routing is well-designed. The PostgresCheckpointer gives multi-turn state for free. Significantly more capable than a simple retrieve→generate pipeline.

3. **Docling over PyMuPDF** — Docling extracts document structure (headings, tables, lists) not just raw text. This makes semantic chunking dramatically better. PyMuPDF gives flat text. For legal documents with complex formatting, Docling wins.

4. **GLiNER for NER** — Running zero-shot NER at 50ms/chunk on CPU is the right call for entity extraction at scale. The architecture plan's DeepSeek extraction at $0.003/doc is fine for batch but can't run at query time.

5. **Semantic chunking** — Respecting paragraph/table boundaries instead of fixed-size splits is critical for legal documents. The current chunker implementation is solid.

6. **LLM abstraction layer** — The Anthropic/OpenAI/vLLM switcher via config is well-implemented and makes the cloud→local migration path real.

7. **Event-driven ingestion** — MinIO webhook → Celery pipeline is clean and scalable.

8. **Code quality** — structlog, tenacity retries, async patterns, TYPE_CHECKING imports, raw SQL over ORM for performance-sensitive paths. Well-engineered code.

### What Needs to Change

1. **No auth = no enterprise deployment.** Legal documents are the most sensitive data a firm handles. Zero authentication means this can't leave a development machine. RBAC with matter-level isolation is table stakes.

2. **No privilege tagging = legal non-starter.** Attorney-client privilege is THE critical workflow in document review. Every legal tech platform gates access to privileged documents. The architecture plan gets this right.

3. **No audit trail = compliance failure.** Law firms must demonstrate chain of custody and access logging for litigation. Who queried what, when, and what documents were returned.

4. **Neo4j adds operational complexity for marginal value.** For a corpus of 50K-100K documents, a well-indexed PostgreSQL `persons` + `connections` + `person_documents` table handles entity queries efficiently. Neo4j becomes valuable at millions of entities with deep graph traversals, but that's not the current scale. Consider making Neo4j optional.

5. **The Epstein dataset focus limits commercial applicability.** The system should be domain-agnostic. The architecture plan's "case matters" concept is the right abstraction — each investigation/case is a matter with its own document set, entity dictionary, and access controls.

6. **No evaluation = flying blind.** Retrieval quality can't be optimized without measuring it. Evaluation should come before any optimization work.

7. **Streamlit is a demo, not a product.** Legal professionals need: PDF viewer with annotation, privilege tagging UI, entity graph visualization, timeline view, export workflows. This requires a real frontend.

8. **Visual embeddings (ColQwen2.5) are premature.** For text-heavy legal documents, good OCR + text embeddings cover 95%+ of retrieval needs. ColQwen2.5 is interesting for handwritten annotations but shouldn't block the path to production.

### Should You Start Over?

**No.** The core pipeline (ingest → parse → chunk → embed → extract → index → query) is solid and well-tested. The technology choices are sound. What's missing is the enterprise wrapper — and that's additive, not a rewrite.

The path forward: **keep the engine, add the chassis.**

---

## Part 2: Design Principles

1. **Enterprise features earlier** — Auth, multi-tenancy, and audit before bulk import
2. **Evaluation before optimization** — Measure retrieval quality before adding ColQwen2.5 or rerankers
3. **Neo4j as optional** — Relational entity model as default, Neo4j as an enhancement
4. **Domain-agnostic** — "Case matters" instead of dataset-specific focus
5. **React frontend in parallel** — Start building the real UI alongside backend milestones
6. **Ship incrementally** — Each milestone delivers user-facing value

---

## Milestone Summary

| Milestone | Status | Tests | Description |
|-----------|--------|-------|-------------|
| M0: Skeleton + Infrastructure | Done | 8 | Docker Compose (5 infra services), FastAPI app factory, Alembic migrations, Celery worker, health checks, stub routers |
| M1: Single Doc Ingestion | Done | 23 | POST /ingest, 6-stage Celery pipeline, Docling parser, semantic chunker, OpenAI embeddings, GLiNER NER, Qdrant + Neo4j indexing |
| M2: Query Pipeline (LangGraph) | Done | 53 | POST /query + /query/stream (SSE), LangGraph 8-node state graph, HybridRetriever, chat persistence |
| M3: Multi-Format + Entity Resolution | Done | 44 | EML/MSG/CSV/RTF parsers, ZIP extraction, batch upload, email-aware chunking, entity resolution, relationship extraction |
| M4: Chat + Streamlit + Doc Browsing | Done | 15 | DocumentService CRUD, 4 document endpoints, Streamlit 3-page dashboard |
| M5: Production Hardening (Core) | Done | 16 | PostgresCheckpointer, streaming refactor, MinIO webhooks, Redis rate limiting, structlog contextvars |
| M5b: Tests + Reranker | TODO | — | Fix failing test, cross-encoder reranker, integration tests, 180+ test target |
| M6: Auth + Multi-Tenancy | TODO | — | JWT + RBAC (4 roles), case matters, matter-scoped queries, API key auth |
| M7: Audit + Privilege Tagging | TODO | — | Audit log middleware, privilege tagging workflow, privilege-filtered retrieval |
| M8: Evaluation Framework | TODO | — | Ground-truth Q&A, retrieval metrics (MRR/Recall/NDCG), answer quality scoring |
| M9: Bulk Import | TODO | — | Content hash dedup, skip-parse task, dataset adapters, CLI orchestrator |
| M10: React Frontend | TODO | — | Vite + React + shadcn/ui, auth flow, doc viewer, chat, entity browser |
| M11: Annotations + Export | TODO | — | Document annotations, privilege log, court-ready export packages |
| M12: Retrieval Tuning | TODO | — | Cross-encoder benchmarking, RRF alpha tuning, chunk size optimization |
| M13: Visual Embeddings | TODO | — | ColQwen2.5 page-level retrieval (optional, gated on evaluation lift) |
| M14: Full Local Deployment | TODO | — | Self-hosted BGE-M3, vLLM for reasoning, zero cloud API dependency |

**Total tests: 159 passing** (as of M5 completion)

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
- Qdrant `nexus_text` collection (dense 1024d + sparse)
- Neo4j entity/relationship graph indexing
- Job status tracking with stage progression

### M2: Query Pipeline (LangGraph)
- `POST /query` — synchronous query with full response
- `POST /query/stream` — SSE streaming (sources before generation, token-by-token)
- LangGraph 8-node state graph: classify > rewrite > retrieve > rerank > check_relevance > graph_lookup > synthesize > follow_ups
- HybridRetriever: Qdrant dense + sparse with native RRF fusion + Neo4j graph traversal
- Chat persistence in PostgreSQL (JSONB for source_docs/entities)
- `GET /chats`, `GET /chats/{thread_id}`, `DELETE /chats/{thread_id}`

### M3: Multi-Format + Entity Resolution
- Parsers for EML, MSG, CSV, RTF, TXT, DOC
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

---

## Next Up

### M5b: Tests + Reranker (1 week)
*Finish what's started before changing direction.*

- [ ] Fix the 1 failing test (outdated stub assertion for query endpoint)
- [ ] `bge-reranker-v2-m3` cross-encoder integration in rerank node (feature-flagged)
- [ ] Integration test: ingest PDF → query → verify cited answer
- [ ] Integration test: SSE streaming end-to-end
- [ ] Error recovery tests: partial pipeline failure scenarios
- [ ] Target: 180+ tests

**Files:** `app/query/nodes.py` (rerank node), `tests/`

---

### M6: Auth + Multi-Tenancy (2 weeks)
*The single most important missing piece for any real deployment.*

- [ ] Alembic migration `002_auth_multitenant`: `users`, `roles`, `case_matters`, `user_case_matters` tables
- [ ] JWT authentication endpoints (login, refresh, me)
- [ ] RBAC middleware: admin, attorney, paralegal, reviewer roles
- [ ] `matter_id` foreign key on `jobs`, `documents`, `chat_messages`
- [ ] All API queries scoped to user's assigned matters
- [ ] Qdrant metadata filtering includes `matter_id`
- [ ] API key auth option (for programmatic access / CI pipelines)
- [ ] ~15 tests (auth, role enforcement, matter scoping)

**Files:** New `app/auth/` module, migration `002_auth_multitenant.py`, modify all routers for auth dependency

---

### M7: Audit + Privilege Tagging (1.5 weeks)
*Legal compliance requirements — non-negotiable for enterprise.*

- [ ] Alembic migration `003_audit_privilege`: `audit_log` table, `privilege_status` + `privilege_reviewed_by` columns on `documents`
- [ ] Audit logging middleware: every API call → audit_log (user, action, resource, IP, timestamp)
- [ ] `PATCH /documents/{id}/privilege` — tag as privileged/work-product/confidential/under-review
- [ ] Privilege filtering in retrieval: unauthorized users never see privileged docs (SQL-level enforcement)
- [ ] `GET /admin/audit-log` — filterable audit log viewer endpoint
- [ ] ~10 tests (privilege enforcement at retrieval level, audit logging)

**Files:** `app/common/middleware.py` (audit), `app/documents/router.py` (privilege endpoints), migration `003_audit_privilege.py`

---

### M8: Evaluation Framework (1.5 weeks)
*Measure before you optimize. Must come before any retrieval tuning.*

- [ ] Ground-truth Q&A dataset (50-100 questions with expected answers + source documents)
- [ ] Retrieval metrics: MRR@10, Recall@10, NDCG@10
- [ ] Answer quality metrics: faithfulness (no hallucination), relevance, citation accuracy
- [ ] `scripts/evaluate.py` CLI — runs full pipeline, reports metrics
- [ ] Baseline numbers documented (regression gate for query pipeline changes)
- [ ] Optional: CI integration for automated evaluation

**Files:** New `evaluation/` directory, `scripts/evaluate.py`

---

### M9: Bulk Import (1.5 weeks)
*Now that auth + matters exist, bulk import scopes documents to a matter.*

- [ ] Alembic migration: content hash index for dedup
- [ ] `import_text_document` Celery task (skip parse, reuse chunk > embed > extract > index)
- [ ] Dataset adapter interface (generic: load from directory, CSV, JSON, HuggingFace)
- [ ] `scripts/import_dataset.py` CLI (--matter-id, --dry-run, --resume, --limit, --batch-size)
- [ ] At least 1 working adapter (recursive directory import for PDF/text files)
- [ ] ~10 tests

**Files:** `app/ingestion/bulk_import.py`, `scripts/import_dataset.py`, Alembic migration

---

## Future

### M10: React Frontend — Core (3 weeks)
*Replace Streamlit with a production-grade application.*

- [ ] Vite + React + TypeScript + Tailwind + shadcn/ui
- [ ] Auth flow: login page, JWT management, role-aware navigation
- [ ] Matter selector: users see only their assigned case matters
- [ ] Dashboard: corpus stats, recent activity, pipeline status
- [ ] Document list with filters (type, date range, privilege status, full-text search)
- [ ] Document detail page with PDF viewer (react-pdf)
- [ ] "Ask the Evidence" chat panel: SSE streaming, citations with document links, follow-up buttons
- [ ] Entity browser: search, detail page with connections and document mentions

**Files:** New `frontend/` directory (React app, replaces Streamlit)

---

### M11: Annotations + Export (2 weeks)
*Features that make it a real litigation support tool.*

- [ ] Alembic migration: `annotations` table
- [ ] Annotation CRUD endpoints
- [ ] Frontend: highlight/note overlay on PDF viewer
- [ ] Court-ready export: document production packages (PDF bundles, privilege log, citation index)
- [ ] `POST /exports` → Celery task → downloadable ZIP
- [ ] ~8 tests

**Files:** New `app/annotations/` module, export Celery task

---

### M12: Retrieval Tuning (1 week)
*Data-driven optimization using the evaluation framework from M8.*

- [ ] Enable `bge-reranker-v2-m3` and measure impact on MRR/Recall
- [ ] Tune RRF alpha parameter using evaluation set
- [ ] Tune chunk size (try 256 and 1024, measure impact)
- [ ] Tune entity extraction threshold
- [ ] Document final parameter choices with benchmark evidence

**Files:** `app/query/nodes.py`, `app/config.py`, `evaluation/`

---

### M13: Visual Embeddings (2 weeks, optional)
*Only pursue if evaluation shows text retrieval missing table/figure content.*

- [ ] ColQwen2.5-v0.2 inference setup (requires GPU)
- [ ] `nexus_visual` Qdrant collection activation
- [ ] Page image extraction during ingestion
- [ ] Multi-modal fusion in retrieval pipeline
- [ ] Re-run evaluation: measure lift over text-only
- [ ] Decision gate: if lift < 5% on legal docs, deprioritize

**Files:** `app/ingestion/embedder.py`, `app/query/retriever.py`, `app/config.py`

---

### M14: Full Local Deployment (2 weeks)
*Zero cloud API dependency. Config change only.*

- [ ] Self-hosted BGE-M3 via TEI (replace OpenAI embeddings)
- [ ] vLLM container for reasoning (Qwen3-235B-A22B or DeepSeek-R1)
- [ ] Docker Compose profile for local-only deployment (`docker-compose.local.yml`)
- [ ] `.env.local.example` template
- [ ] Performance benchmarks: tokens/sec, p95 query latency

**Files:** `docker-compose.local.yml`, `.env.local.example`

---

## Timeline Estimate

| Milestone | Duration | Cumulative |
|-----------|----------|------------|
| M5b: Tests + Reranker | 1 week | Week 1 |
| M6: Auth + Multi-Tenancy | 2 weeks | Week 3 |
| M7: Audit + Privilege | 1.5 weeks | Week 4.5 |
| M8: Evaluation Framework | 1.5 weeks | Week 6 |
| M9: Bulk Import | 1.5 weeks | Week 7.5 |
| M10: React Frontend | 3 weeks | Week 10.5 |
| M11: Annotations + Export | 2 weeks | Week 12.5 |
| M12: Retrieval Tuning | 1 week | Week 13.5 |
| M13: Visual Embeddings | 2 weeks (optional) | Week 15.5 |
| M14: Full Local | 2 weeks | Week 17.5 |

---

## What's Different from v1

1. **Auth + multi-tenancy moved from "never" to M6** — immediately after test cleanup
2. **Evaluation moved from M7 to M8** — still early, before any optimization
3. **Bulk import pushed later** — needs auth/matters first for proper scoping
4. **React frontend gets a dedicated milestone** — not "future/someday"
5. **Annotations + export added** — critical for legal workflows
6. **Visual embeddings made optional** — gated on evaluation results
7. **Retrieval tuning follows evaluation** — data-driven, not gut-driven
8. **Neo4j kept but not expanded** — works for what's built, relational model sufficient for enterprise features

---

## Key Decision: Neo4j

The current Neo4j integration works. It shouldn't be ripped out. But for the new enterprise features (matter-scoped entities, privilege-aware graph queries), the PostgreSQL relational model from the architecture plan is simpler and avoids cross-database consistency issues.

**Recommendation:** Keep Neo4j for the investigation/exploration use case (graph traversal, entity connections). Add the relational entity model (persons, connections tables in PostgreSQL) for the enterprise CRUD workflows (entity browsing, privilege scoping, audit). They can coexist — Neo4j is populated during ingestion as it is today, PostgreSQL entity tables serve the API/frontend.

---

## Verification

After implementing this roadmap:
1. **Auth**: Login as paralegal → privileged docs hidden. Login as attorney → privileged docs visible
2. **Multi-tenancy**: User A (matter 1) cannot see User B (matter 2) documents
3. **Audit**: Every query/view/download logged with user, timestamp, IP
4. **Pipeline**: Upload PDF → parse → chunk → embed → extract → index → query with cited answer
5. **Evaluation**: MRR@10, Recall@10 baselines documented and tracked
6. **Frontend**: End-to-end flow in React — login → select matter → upload → chat → cite → export

---

## Architecture Quick Reference

```
MinIO (S3)  ──>  Celery Workers  ──>  Parse ──> Chunk ──> Embed ──> Extract ──> Index
  (upload)        (background)       Docling    Semantic   BGE-M3    GLiNER     Qdrant
                                     stdlib*    (512 tok)  OpenAI    Instructor  Neo4j

FastAPI  ──>  Auth (JWT/RBAC)  ──>  LangGraph State Graph  ──>  Hybrid Retrieval
  /query       matter scoping        classify > rewrite         Qdrant RRF + Neo4j
  /query/stream  privilege filter      > retrieve > rerank      > graph_lookup
                 audit logging           > synthesize > follow_ups

PostgreSQL: users, roles, case_matters, jobs, documents, chat_messages, audit_log, annotations
Qdrant: nexus_text (1024d dense + sparse), nexus_visual (128d multi-vector, future)
Neo4j: entity graph (persons, organizations, locations, events, relationships)
Redis: Celery broker, rate limiting, response cache
MinIO: raw documents, parsed output, page images, thumbnails
```

*stdlib = `email` + `extract-msg` + `striprtf` for EML/MSG/RTF/CSV/TXT

**Stack:** FastAPI, Celery/Redis, PostgreSQL, Qdrant, Neo4j, MinIO, LangGraph, Docling, GLiNER, Instructor

**Dev mode:** Docker for infra, Python runs natively (Apple Silicon, 16GB RAM, concurrency=1)

---

## See Also

- `CLAUDE.md` — codebase architecture, API endpoints, implementation rules
- `NEXUS-architecture-plan.md` — original enterprise architecture plan (pgvector-based)
- `.env.example` — all configuration variables and feature flags
- `docs/M6-BULK-IMPORT.md` — bulk import spec for pre-OCR'd datasets
- `docker-compose.yml` — infrastructure services (dev: runs natively on Mac)
- `docker-compose.prod.yml` — full containerized stack (API + worker + Flower)
