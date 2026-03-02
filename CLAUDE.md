# CLAUDE.md — NEXUS

Multimodal RAG investigation platform for legal document intelligence. Ingests, analyzes, and queries 50,000+ pages of mixed-format legal documents. Surfaces people, relationships, timelines, and patterns across a heterogeneous corpus.

---

## Session Rules

**These rules govern every interaction.** Read them first. Follow them exactly.

### Process

1. **Always start in plan mode** for any non-trivial task. Read the relevant code, understand the context, present an approach, and get approval before writing a single line. Trivial = single-line fix, typo, or a change the user has fully specified.
2. **Ask when uncertain — never assume.** If a requirement is ambiguous, an interface is unclear, or there are multiple valid approaches, stop and ask. A wrong assumption costs more than a question.
3. **Read before you write.** Always read the files you intend to modify. Understand the existing patterns, imports, and conventions in that specific file before making changes.
4. **Check `ROADMAP.md` for context.** Know which milestone is current, what's done, and what's planned. Don't build something that's already scoped for a later milestone, and don't break assumptions from completed milestones.
5. **Plans include tests.** Every plan/todo must include writing tests as an explicit step — not an afterthought.
6. **Finish the loop: implement → test → fix → verify → update ROADMAP → commit.** After completing a plan, run `pytest tests/ -v`. If tests fail, fix the issues and re-run until all tests pass. Only then update `ROADMAP.md` to reflect what was completed (check off items, update status, adjust test counts). Finally, commit all changes with a clear message. Work is not done until the roadmap is current and the commit is made.
7. **One concern per change.** Don't refactor adjacent code, add unrelated improvements, or "clean up" things that aren't part of the current task.
8. **When unsure about a library API, look it up.** Do not guess at method signatures, parameter names, or return types from memory. Libraries in this project (LangGraph, Qdrant client, Instructor, Docling, FastEmbed, GLiNER, etc.) evolve rapidly and your training data may be stale. Search the web for current official documentation, read the actual installed source in `.venv/`, or ask. Confidently writing an outdated or incorrect API call wastes more time than checking.
9. **High-blast-radius changes need confirmation.** Docker configs, Alembic migrations that drop/rename columns, dependency version changes, and anything touching auth middleware — always flag these and get explicit approval before applying.

### Code Quality — Library-First, Not Custom Code

**This is an integration project.** We stitch together well-maintained libraries and APIs — FastAPI, LangGraph, Qdrant client, Neo4j driver, Instructor, Docling, GLiNER, etc. We do NOT write custom implementations of things these libraries already do.

7. **Use the library's API as designed.** Don't wrap library calls in unnecessary abstractions. Don't build a "helper" around something that already has a clean API. If Qdrant has a method for it, use it. If Instructor handles it, let it. If LangGraph provides a pattern, follow it.
8. **No spaghetti code.** Every function should have a single clear responsibility. If you're writing a function longer than ~40 lines, it probably needs to be decomposed. If you're passing more than 5 parameters, you probably need a schema.
9. **DRY, but don't over-abstract.** Extract shared logic only when it's used in 3+ places. Two similar blocks of code are fine — a premature abstraction is worse than mild duplication.
10. **Follow existing patterns exactly.** The codebase has established conventions (detailed below). Match them. Don't introduce a new pattern for doing something the codebase already does a different way.
11. **No silent fallbacks.** Do not write `try/except` blocks that swallow errors and return degraded results. Do not write `if service_unavailable: use_fallback()` code. If something fails, it should fail loudly — raise the exception, log the error, return a clear error to the caller. Silent fallbacks mask bugs, make debugging nightmarish at scale, and erode trust in the system. If you believe a specific case genuinely needs graceful degradation, ask first and explain why.

### Type Safety & Schemas

11. **Type everything.** Every function signature, every return type, every variable where the type isn't obvious. Use Python 3.12+ syntax: `str | None`, `list[dict]`, not `Optional[str]`, not `List[Dict]`.
12. **Pydantic v2 for all data structures.** Request/response schemas, configuration, structured LLM output — all Pydantic `BaseModel`. Use `Field(...)` for validation constraints. No raw dicts crossing module boundaries.
13. **Schemas live in `schemas.py`.** Each domain module (`ingestion/`, `query/`, `entities/`, etc.) has its own `schemas.py`. Shared base models go in `app/common/models.py`. Don't define inline schemas in routers or services.
14. **Follow the naming convention:**
    - Request schemas: `{Domain}Request` (e.g., `QueryRequest`, `IngestRequest`)
    - Response schemas: `{Domain}Response`, `{Domain}ListResponse`, `{Domain}DetailResponse`
    - Enums: `StrEnum` for string enumerations (e.g., `JobStatus`, `DocumentType`)

### Module Organization

15. **Respect the module structure.** Each domain is `app/{domain}/` with:
    - `router.py` — FastAPI endpoints (thin: validation, DI, delegate to service)
    - `service.py` — Business logic, DB operations (`@staticmethod` methods, raw SQL via `sqlalchemy.text()`)
    - `schemas.py` — Pydantic models for that domain
    - `tasks.py` — Celery tasks (if the domain has background work)
16. **Routers are thin.** Routers validate input, call services, return responses. Business logic belongs in services, not routers.
17. **Services own data access.** All SQL lives in service methods. Services take `AsyncSession` as a parameter — the caller (router or DI) manages the transaction.
18. **New features may need a new module.** If a feature doesn't fit cleanly into an existing domain, create `app/{new_domain}/` following the same `router.py` / `service.py` / `schemas.py` pattern.
19. **Shared utilities go in `app/common/`.** Cross-cutting concerns: storage, LLM client, vector store wrapper, rate limiting, middleware.

### Database & Data Layer

20. **Raw SQL via `sqlalchemy.text()`.** No ORM. This is intentional — known query patterns, full control, minimal overhead. Always use named parameters (`:param`) to prevent SQL injection.
21. **Alembic for all schema changes.** Never modify the database schema without an Alembic migration. Run `alembic revision --autogenerate -m "description"` and review before applying.
22. **Every query must be matter-scoped.** All data endpoints filter by `matter_id`. This applies to SQL WHERE clauses, Qdrant payload filters, and Neo4j Cypher WHERE clauses. No exceptions.
23. **Privilege enforcement at the data layer.** Qdrant filter + SQL WHERE + Neo4j Cypher. Never rely on API-layer filtering alone.

### Async & Concurrency

24. **Async everywhere in the API.** All FastAPI routes, all service methods, all DB calls use `async`/`await`. No blocking I/O in the request path.
25. **Celery tasks are the exception.** Celery workers run synchronously. Use `asyncio.run()` wrappers when tasks need to call async code. Tasks create their own sync DB engine via `_get_sync_engine()`.

### Dependencies & Configuration

26. **All config from environment variables.** `app/config.py` (Pydantic Settings) is the single source. No hardcoded connection strings, API keys, or model names in code. New config → add to `Settings` class AND `.env.example`.
27. **DI via `app/dependencies.py`.** All service clients (LLM, Qdrant, Neo4j, MinIO, Redis) are singletons created through factory functions. Register new dependencies here, not in routers or services.
28. **Feature flags for new capabilities.** Anything experimental or optional gets an `ENABLE_*` flag in config, defaulting to `false`. Check the flag before initializing expensive resources.

### Error Handling & Logging

29. **Use `structlog` for all logging.** Bind context (`request_id`, `task_id`, `job_id`) via contextvars. Log at appropriate levels: `info` for operations, `warning` for degraded behavior, `error` for failures with stack traces.
30. **Retry with backoff on external calls.** All LLM API calls, embedding calls, and external service calls get `tenacity` retry with exponential backoff (3 attempts). Don't silently swallow failures.
31. **Raise `HTTPException` with clear detail messages.** Status codes must be accurate (400 for bad input, 401/403 for auth, 404 for not found, 422 for validation, 500 for server errors).

### Testing

32. **Every new feature or bug fix needs tests.** Tests mirror the module structure: `tests/test_{domain}/`. Use the existing `conftest.py` fixtures (mock services, AsyncClient, patched lifespan).
33. **Mock external services, test your logic.** Tests should not require running infrastructure. Mock Qdrant, Neo4j, MinIO, Redis, LLM APIs. Test that your code calls them correctly with the right parameters.
34. **Celery task `.delay()` is sync.** Mock it with `MagicMock`, not `AsyncMock`.

### Enterprise & Security

35. **No secrets in code.** API keys, passwords, JWT secrets — all from environment variables. Never commit `.env`. Update `.env.example` with placeholder values for any new secrets.
36. **Audit trail for every API call.** The audit logging middleware captures user, action, resource, matter, IP. Don't bypass it.
37. **CORS restricted.** Only configured origins. Never `allow_origins=["*"]` in production.
38. **Rate limiting on public endpoints.** Use the existing Redis sliding-window limiter via `Depends()`.

### Legal Domain Sensitivity

39. **Never leak document content in errors or logs.** This platform handles privileged legal documents. Error messages, tracebacks, and log entries must never contain raw document text, PII, or privileged material. Log document IDs and chunk IDs — not content. API error responses get clean detail messages, not `repr()` of internal state.
40. **All prompt templates in `prompts.py`.** Each domain module that uses LLM calls should centralize its prompt templates (see `app/query/prompts.py`). No prompt strings scattered across nodes, services, or extractors. This is critical for auditability, tuning, and legal review.

### Scale Awareness

41. **This is a 50k+ page corpus.** Always paginate DB queries, batch operations (embeddings, indexing, NER), and stream large results. Never load an entire collection or table into memory. A query that works with 100 docs will OOM or timeout at production scale.

### Technology-Specific Rules

- **FastAPI**: Use `Depends()` for injection. Use `response_model=` on endpoints. Use `APIRouter` with `tags=`. Async handlers only.
- **LangGraph**: Use for query orchestration. State graph with typed state. PostgresCheckpointer for persistence. Don't use LangChain.
- **Qdrant**: Use native Python client. Named vectors for dense+sparse. Native RRF fusion via `prefetch` + `FusionQuery`. Don't implement fusion in Python.
- **Neo4j**: Use the official Python driver. Parameterized Cypher queries (never string interpolation). Close sessions properly.
- **Instructor**: Use for structured LLM output. Pydantic response models. Let Instructor handle retries and validation.
- **Docling**: Use for PDF/DOCX/XLSX/PPTX/HTML parsing. Leverage document structure for semantic chunking. Don't use Marker (GPL).
- **GLiNER**: Use for NER at ingestion time. CPU inference, lazy-loaded model. Don't call LLM for entity extraction.
- **Celery**: `@shared_task` decorator. Update job progress in DB via `_update_stage()`. Handle failures by writing error to job record.
- **Alembic**: All migrations in `migrations/versions/`. Always review autogenerated migrations. Test both upgrade and downgrade.
- **LangGraph agents**: `create_react_agent` for autonomous agents, `@tool` decorator with `InjectedState` for security context, prebuilt `ToolNode`. See `app/query/graph.py` and `app/cases/agent.py`. Details in `docs/agents.md`.
- **BERTopic**: Topic clustering (feature-flagged: `ENABLE_TOPIC_CLUSTERING`). CPU inference, lazy-loaded. See `app/analytics/clustering.py`.

---

## Architecture

```
┌─ INGESTION PIPELINE (Celery background workers) ──────────────────────────────┐
│                                                                               │
│  MinIO (S3)  ──>  Parse ──> Chunk ──> Embed ──> Extract ──> Analyze ──> Index │
│   upload         Docling   Semantic   Dense+     GLiNER      Sentiment   Qdrant│
│   webhook        stdlib*   (512 tok)  Sparse     Instructor  Hot-doc     Neo4j │
│   EDRM load                Visual     Dedup      Coref       Anomaly          │
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘

┌─ QUERY PIPELINE (FastAPI async) ──────────────────────────────────────────────┐
│                                                                               │
│  React UI  ──>  Auth (JWT/RBAC)  ──>  Case Context  ──>  Investigation Agent  │
│   /chat          matter scoping       auto-inject        create_react_agent   │
│   /documents     privilege filter     from case DB       12 @tool functions   │
│   /entities      audit logging                           (InjectedState)      │
│   /analytics                                                                  │
│                                                                               │
│  Investigation Agent loop:                    Hybrid Retrieval:               │
│    case_context_resolve                         Qdrant native RRF            │
│    > agent (tool-use loop, 12 tools)            + Neo4j multi-hop            │
│    > verify_citations (CoVe)                    + cross-encoder rerank       │
│    > generate_follow_ups                        + visual rerank (ColQwen2.5) │
│                                                 + privilege filtering        │
└───────────────────────────────────────────────────────────────────────────────┘

┌─ AUTONOMOUS AGENTS (6 total — see docs/agents.md) ────────────────────────────┐
│  Investigation Orchestrator · Citation Verifier · Case Setup Agent            │
│  Hot Doc Scanner · Contextual Completeness · Entity Resolution Agent          │
└───────────────────────────────────────────────────────────────────────────────┘

┌─ EXPORT & REDACTION ──────────────────────────────────────────────────────────┐
│  Production Sets · Bates Numbering · PDF/CSV/EDRM Export · PII Redaction     │
└───────────────────────────────────────────────────────────────────────────────┘
```

*stdlib = `email` + `extract-msg` + `striprtf` for EML/MSG/RTF/CSV/TXT
*See `ARCHITECTURE.md` for full system design*

---

## Tech Stack

### Infrastructure
| Component | Technology | Notes |
|---|---|---|
| API | FastAPI 0.115+ | Async, OpenAPI docs, DI, JWT auth middleware |
| Frontend | React 19 + Vite + TypeScript | TanStack Router/Query, shadcn/ui, Vercel deploy |
| Task Queue | Celery 5.5+ / Redis | Background ingestion + analysis pipeline |
| Object Storage | MinIO (S3-compat) | Bucket webhook triggers ingestion |
| Metadata DB | PostgreSQL 16 | 27 tables, 13 migrations (see `docs/database-schema.md`) |
| Vector DB | Qdrant v1.13.2 | Named dense+sparse+visual vectors, native RRF fusion |
| Knowledge Graph | Neo4j 5.x | Entity graph, multi-hop traversal, path-finding, temporal queries |
| Cache/Broker | Redis 7+ | Celery broker, rate limiting, response cache |

### AI Models
| Role | Current Implementation |
|---|---|
| LLM (reasoning) | 4 providers: Anthropic, OpenAI, vLLM, Ollama (`LLM_PROVIDER` config) |
| Text Embeddings | 4 providers: OpenAI, local (sentence-transformers), TEI, Gemini (`EMBEDDING_PROVIDER` config) |
| Sparse Embeddings | FastEmbed `Qdrant/bm42-all-minilm-l6-v2-attentions` (feature-flagged: `ENABLE_SPARSE_EMBEDDINGS`) |
| Visual Embeddings | ColQwen2.5 via `colpali-engine` (feature-flagged: `ENABLE_VISUAL_EMBEDDINGS`) |
| Zero-shot NER | GLiNER (`gliner_multi_pii-v1`, CPU) |
| Structured Extract | Instructor + LLM (feature-flagged: `ENABLE_RELATIONSHIP_EXTRACTION`) |
| Reranker | Local `bge-reranker-v2-m3` or TEI server (feature-flagged: `ENABLE_RERANKER`) |
| Topic Clustering | BERTopic + sentence-transformers (feature-flagged: `ENABLE_TOPIC_CLUSTERING`) |
| Sentiment Analysis | LLM-based 7-dimension scoring (`app/analysis/sentiment.py`) |

### Document Processing
| File Types | Parser |
|---|---|
| PDF, DOCX, XLSX, PPTX, HTML, images | Docling 2.70+ |
| EML | Python `email` stdlib |
| MSG | `extract-msg` |
| RTF | `striprtf` |
| CSV, TXT | Python stdlib |
| ZIP | `zipfile` stdlib → route contents by extension |
| EDRM/Concordance loadfiles | Custom parser (`app/edrm/loadfile_parser.py`) |

### Orchestration
| Component | Technology |
|---|---|
| Query orchestration | LangGraph (`create_react_agent` + `StateGraph`, PostgresCheckpointer) |
| Retrieval primitives | LlamaIndex (core only) |
| Structured output | Instructor 1.14+ |

---

## Project Structure

*Full module details: `docs/modules.md` · Database tables: `docs/database-schema.md`*

```
nexus/
├── CLAUDE.md                              # This file
├── ARCHITECTURE.md                        # System design, tech stack, security model
├── ROADMAP.md                             # Milestones, build status, dependencies
├── docker-compose.yml                     # Infra services (Redis, PG, Qdrant, Neo4j, MinIO)
├── docker-compose.prod.yml                # Full stack (API, worker, Flower)
├── docker-compose.cloud.yml               # Cloud overlay (Caddy reverse proxy + TLS)
├── docker-compose.local.yml               # Local LLM stack (vLLM/Ollama, TEI)
├── Dockerfile
├── .env.example                           # All configuration variables
├── pyproject.toml                         # Python 3.12+, uv/pip
├── alembic.ini
│
├── app/
│   ├── main.py                            # FastAPI app factory + lifespan
│   ├── config.py                          # Pydantic Settings (all config from env)
│   ├── dependencies.py                    # DI: 20 @functools.cache factory functions
│   │
│   ├── ingestion/                         # Document ingestion pipeline
│   │   ├── router.py                      # /ingest, /ingest/batch, /ingest/webhook, /jobs/*
│   │   ├── service.py                     # Orchestrates parse → chunk → embed → extract → index
│   │   ├── tasks.py                       # Celery tasks (6-stage pipeline)
│   │   ├── parser.py                      # Routes files to Docling / stdlib parsers
│   │   ├── chunker.py                     # Semantic chunking (512 tok, 64 overlap)
│   │   ├── embedder.py                    # Ingestion embedding adapter
│   │   ├── sparse_embedder.py             # BM42 sparse vectors (feature-flagged)
│   │   ├── visual_embedder.py             # ColQwen2.5 visual embedding (feature-flagged)
│   │   ├── dedup.py                       # MinHash near-duplicate detection (feature-flagged)
│   │   ├── threading.py                   # Email thread reconstruction
│   │   ├── bulk_import.py                 # Pre-OCR'd dataset import
│   │   └── schemas.py                     # IngestRequest, JobStatus, DocumentMeta
│   │
│   ├── query/                             # Investigation query pipeline
│   │   ├── router.py                      # /query, /query/stream (SSE), /chats/*
│   │   ├── graph.py                       # LangGraph agentic + v1 graph builders
│   │   ├── nodes.py                       # Graph nodes: classify, rewrite, verify_citations
│   │   ├── tools.py                       # 12 @tool functions with InjectedState
│   │   ├── retriever.py                   # HybridRetriever: Qdrant RRF + Neo4j
│   │   ├── reranker.py                    # Cross-encoder + TEI reranker (feature-flagged)
│   │   ├── service.py                     # Query service helpers
│   │   ├── prompts.py                     # All prompt templates
│   │   └── schemas.py                     # QueryRequest, QueryResponse, ChatMessage
│   │
│   ├── entities/                          # Entity extraction & knowledge graph
│   │   ├── router.py                      # /entities/*, /graph/*
│   │   ├── extractor.py                   # GLiNER NER pipeline
│   │   ├── relationship_extractor.py      # Instructor + LLM (feature-flagged)
│   │   ├── resolver.py                    # Entity resolution (rapidfuzz + union-find)
│   │   ├── resolution_agent.py            # LangGraph entity resolution agent
│   │   ├── coreference.py                 # spaCy coreferee (feature-flagged)
│   │   ├── graph_service.py               # Neo4j operations (multi-hop, path-finding)
│   │   ├── tasks.py                       # Background entity tasks
│   │   └── schemas.py                     # Entity, Relationship, GraphExploreResponse
│   │
│   ├── documents/                         # Document metadata & file access
│   │   ├── router.py                      # /documents/*, preview, download, privilege
│   │   ├── service.py                     # MinIO operations, metadata CRUD
│   │   └── schemas.py                     # Document, DocumentList, DocumentDetail
│   │
│   ├── auth/                              # JWT auth, RBAC, API keys, matter scoping
│   │   ├── router.py                      # /auth/login, /auth/refresh, /auth/me
│   │   ├── admin_router.py                # /admin/audit-log, /admin/users CRUD
│   │   ├── service.py                     # JWT creation, password hashing, role checks
│   │   ├── middleware.py                  # Auth + RBAC + matter scoping middleware
│   │   └── schemas.py                     # User, Token, Role schemas
│   │
│   ├── analysis/                          # Document analysis (M10b)
│   │   ├── sentiment.py                   # 7-dimension LLM sentiment scoring
│   │   ├── anomaly.py                     # Communication anomaly detection
│   │   ├── completeness.py                # Context gap analysis (5 gap types)
│   │   ├── tasks.py                       # Hot Doc Scanner + analysis pipeline tasks
│   │   ├── prompts.py                     # Analysis prompt templates
│   │   └── schemas.py                     # SentimentResult, AnomalyResult
│   │
│   ├── analytics/                         # Communication analytics (M10c)
│   │   ├── router.py                      # /analytics/communication-matrix, /network-centrality
│   │   ├── service.py                     # Matrix computation, centrality queries
│   │   ├── clustering.py                  # BERTopic topic clustering (feature-flagged)
│   │   └── schemas.py                     # CommunicationMatrixResponse, CentralityMetric
│   │
│   ├── annotations/                       # Document annotations (M14)
│   │   ├── router.py                      # /annotations CRUD
│   │   ├── service.py                     # Annotation storage
│   │   └── schemas.py                     # AnnotationCreate, AnnotationResponse
│   │
│   ├── audit/                             # SOC 2 audit (M7b)
│   │   ├── router.py                      # /admin/audit/ai, /export, /retention
│   │   ├── service.py                     # AI audit log queries, retention policy
│   │   └── schemas.py                     # AIAuditLogListResponse, RetentionConfig
│   │
│   ├── cases/                             # Case intelligence (M9b)
│   │   ├── router.py                      # /cases/{matter_id}/setup, /context, /org-chart
│   │   ├── agent.py                       # Case Setup Agent (LangGraph StateGraph)
│   │   ├── context_resolver.py            # Auto-inject case context into queries
│   │   ├── service.py                     # Case context CRUD
│   │   ├── tasks.py                       # Background case setup
│   │   ├── prompts.py                     # Case extraction prompts
│   │   └── schemas.py                     # CaseContextResponse, CaseSetupResponse
│   │
│   ├── datasets/                          # Dataset & tag management (M13b)
│   │   ├── router.py                      # /datasets/*, /tags/*, /documents/*/tags
│   │   ├── service.py                     # Hierarchical folders, doc-tag CRUD
│   │   └── schemas.py                     # DatasetResponse, TagResponse
│   │
│   ├── edrm/                              # EDRM/Concordance import (M6b)
│   │   ├── router.py                      # /edrm/import, /export, /threads, /duplicates
│   │   ├── loadfile_parser.py             # DAT/OPT/LST loadfile parser
│   │   ├── service.py                     # EDRM import orchestration
│   │   └── schemas.py                     # EDRMImportResponse, ThreadListResponse
│   │
│   ├── evaluation/                        # Evaluation framework (M9)
│   │   ├── router.py                      # /evaluation/datasets/*, /runs/*
│   │   ├── service.py                     # Ground-truth eval execution
│   │   └── schemas.py                     # EvalRunResponse, DatasetItemResponse
│   │
│   ├── exports/                           # Production sets & export (M14)
│   │   ├── router.py                      # /exports/production-sets/*, /jobs/*, /privilege-log/*
│   │   ├── service.py                     # Bates numbering, export job management
│   │   ├── generators.py                  # PDF/CSV/EDRM export generators
│   │   ├── tasks.py                       # Background export processing
│   │   └── schemas.py                     # ProductionSetResponse, ExportJobResponse
│   │
│   ├── redaction/                         # PII redaction (M14b)
│   │   ├── router.py                      # /documents/{id}/redact, /redaction-log, /pii-detections
│   │   ├── pii_detector.py                # GLiNER-based PII detection
│   │   ├── engine.py                      # PDF redaction engine
│   │   ├── service.py                     # Redaction orchestration
│   │   └── schemas.py                     # RedactRequest, PIIDetection
│   │
│   └── common/                            # Shared infrastructure
│       ├── middleware.py                   # CORS, request logging, error handling, audit
│       ├── storage.py                     # MinIO/S3 client wrapper
│       ├── llm.py                         # LLM client (Anthropic/OpenAI/vLLM/Ollama)
│       ├── embedder.py                    # Protocol + 4 embedding providers
│       ├── vector_store.py                # Qdrant client wrapper
│       ├── db_utils.py                    # JSONB parsing helpers
│       ├── rate_limit.py                  # Redis sliding-window rate limiter
│       └── models.py                      # Shared base models
│
├── workers/
│   └── celery_app.py                      # Celery config, task autodiscovery
│
├── migrations/
│   └── versions/                          # 13 Alembic migrations (see docs/database-schema.md)
│
├── frontend/                              # React 19 + Vite + TypeScript
│   ├── src/
│   │   ├── routes/                        # TanStack Router pages
│   │   ├── components/                    # shadcn/ui components
│   │   ├── api/                           # Orval-generated API client
│   │   ├── hooks/                         # TanStack Query hooks
│   │   └── stores/                        # Zustand state stores
│   ├── e2e/                               # Playwright E2E tests
│   └── __tests__/                         # Vitest unit tests
│
├── scripts/                               # Operational scripts
│   ├── cloud-deploy.sh                    # GCP deployment automation
│   ├── cloud-teardown.sh                  # GCP resource cleanup
│   ├── seed_admin.py                      # Initial admin user creation
│   ├── import_dataset.py                  # Bulk dataset import
│   ├── reembed.py                         # Re-embed existing documents
│   └── evaluate.py                        # Run evaluation framework
│
├── .github/workflows/                     # CI/CD
│   ├── test-backend.yml                   # Backend pytest
│   ├── test-frontend.yml                  # Frontend Vitest + Playwright
│   └── evaluate.yml                       # Evaluation dry run
│
├── evaluation/                            # Ground-truth Q&A, metrics
│
├── docs/                                  # Reference documentation
│   ├── modules.md                         # Module reference guide
│   ├── database-schema.md                 # Database tables & migrations
│   ├── feature-flags.md                   # All 16 feature flags
│   ├── testing-guide.md                   # Test infrastructure & patterns
│   ├── agents.md                          # LangGraph agent reference
│   ├── CLOUD-DEPLOY.md                    # GCP + Vercel deployment
│   ├── M6-BULK-IMPORT.md                  # Bulk import spec
│   └── M13-FRONTEND-SPEC.md              # React frontend specification
│
└── tests/                                 # 502 backend tests (see docs/testing-guide.md)
    ├── conftest.py                        # Root fixtures: mock services, AsyncClient
    ├── test_analysis/
    ├── test_analytics/
    ├── test_annotations/
    ├── test_audit/
    ├── test_auth/
    ├── test_cases/
    ├── test_common/
    ├── test_datasets/
    ├── test_documents/
    ├── test_e2e/                          # Full-stack E2E with Docker
    ├── test_edrm/
    ├── test_entities/
    ├── test_evaluation/
    ├── test_exports/
    ├── test_ingestion/
    ├── test_integration/
    ├── test_query/
    └── test_redaction/
```

---

## API Endpoints

```
# Authentication
POST   /api/v1/auth/login                    # JWT token issuance
POST   /api/v1/auth/refresh                  # Token refresh
GET    /api/v1/auth/me                       # Current user profile
GET    /api/v1/auth/me/matters               # User's assigned matters

# Ingestion
POST   /api/v1/ingest                         # Single file upload
POST   /api/v1/ingest/batch                   # Multi-file upload (accepts ZIP)
POST   /api/v1/ingest/presigned-upload        # Get presigned upload URL
POST   /api/v1/ingest/import/dry-run          # Bulk import dry run
POST   /api/v1/ingest/webhook                 # MinIO bucket notification handler
GET    /api/v1/jobs/{job_id}                  # Job status + progress
GET    /api/v1/jobs                           # List all jobs (paginated)
DELETE /api/v1/jobs/{job_id}                  # Cancel/delete job
GET    /api/v1/bulk-imports/{import_id}       # Bulk import status

# Query & Chat
POST   /api/v1/query                          # Synchronous query (full response)
POST   /api/v1/query/stream                   # SSE streaming query
GET    /api/v1/chats                          # List chat threads
GET    /api/v1/chats/{thread_id}              # Full chat history
DELETE /api/v1/chats/{thread_id}              # Delete chat thread

# Documents
GET    /api/v1/documents                      # List documents (filterable)
GET    /api/v1/documents/{id}                 # Document metadata + chunks
GET    /api/v1/documents/{id}/preview         # Page thumbnail (presigned URL)
GET    /api/v1/documents/{id}/download        # Original file (presigned URL)
PATCH  /api/v1/documents/{id}/privilege       # Privilege tagging (attorney+)

# Knowledge Graph & Entities
GET    /api/v1/entities                       # Search/list entities
GET    /api/v1/entities/{id}                  # Entity details
GET    /api/v1/entities/{id}/connections      # Graph neighborhood
GET    /api/v1/graph/explore                  # Graph exploration (Cypher)
GET    /api/v1/graph/timeline/{entity}        # Entity timeline
GET    /api/v1/graph/stats                    # Graph statistics
GET    /api/v1/graph/communication-pairs      # Communication pairs
GET    /api/v1/graph/reporting-chain/{person} # Org hierarchy chain
GET    /api/v1/graph/path                     # Shortest path between entities

# Cases
POST   /api/v1/cases/{matter_id}/setup        # Upload anchor doc, start case setup
GET    /api/v1/cases/{matter_id}/context       # Get full case context
PATCH  /api/v1/cases/{matter_id}/context       # Edit/confirm extracted context
POST   /api/v1/cases/{matter_id}/org-chart     # Import org chart

# EDRM
POST   /api/v1/edrm/import                    # Import EDRM/Concordance loadfile
GET    /api/v1/edrm/export                     # Export in EDRM format
GET    /api/v1/edrm/threads                    # Email thread listing
GET    /api/v1/edrm/duplicates                 # Near-duplicate clusters

# Analytics
GET    /api/v1/analytics/communication-matrix  # Sender-recipient pairs
GET    /api/v1/analytics/network-centrality     # Entity centrality rankings

# Annotations
POST   /api/v1/annotations                     # Create annotation
GET    /api/v1/annotations                     # List annotations (filterable)
GET    /api/v1/annotations/{id}                # Annotation detail
PATCH  /api/v1/annotations/{id}                # Update annotation
DELETE /api/v1/annotations/{id}                # Delete annotation

# Exports & Production Sets
POST   /api/v1/exports/production-sets         # Create production set
GET    /api/v1/exports/production-sets         # List production sets
GET    /api/v1/exports/production-sets/{id}    # Production set detail
POST   /api/v1/exports/production-sets/{id}/documents  # Add docs to set
GET    /api/v1/exports/production-sets/{id}/documents  # List docs in set
DELETE /api/v1/exports/production-sets/{id}/documents  # Remove docs from set
POST   /api/v1/exports/production-sets/{id}/bates      # Assign Bates numbers
POST   /api/v1/exports                         # Start export job
GET    /api/v1/exports/jobs                    # List export jobs
GET    /api/v1/exports/jobs/{id}               # Export job status
GET    /api/v1/exports/jobs/{id}/download      # Download exported file
GET    /api/v1/exports/privilege-log/preview   # Preview privilege log

# Redaction
POST   /api/v1/documents/{id}/redact           # Apply redactions (attorney+)
GET    /api/v1/documents/{id}/redaction-log    # Redaction audit log
GET    /api/v1/documents/{id}/pii-detections   # Auto-detect PII

# Datasets & Tags
POST   /api/v1/datasets                        # Create dataset/folder
GET    /api/v1/datasets                        # List datasets
GET    /api/v1/datasets/tree                   # Hierarchical folder tree
GET    /api/v1/datasets/{id}                   # Dataset detail
PATCH  /api/v1/datasets/{id}                   # Update dataset
DELETE /api/v1/datasets/{id}                   # Delete dataset
POST   /api/v1/datasets/{id}/documents         # Add docs to dataset
DELETE /api/v1/datasets/{id}/documents         # Remove docs from dataset
POST   /api/v1/datasets/{id}/documents/move    # Move docs between datasets
GET    /api/v1/datasets/{id}/documents         # List docs in dataset
POST   /api/v1/datasets/{id}/access            # Grant dataset access
DELETE /api/v1/datasets/{id}/access/{user_id}  # Revoke dataset access
GET    /api/v1/datasets/{id}/access            # List dataset access
POST   /api/v1/documents/{id}/tags             # Add tag to document
DELETE /api/v1/documents/{id}/tags/{tag}       # Remove tag
GET    /api/v1/documents/{id}/tags             # List document tags
GET    /api/v1/tags                            # List all tags
GET    /api/v1/tags/{tag}/documents            # List docs with tag

# Evaluation
GET    /api/v1/evaluation/latest               # Latest eval results
GET    /api/v1/evaluation/datasets/{type}      # List dataset items
POST   /api/v1/evaluation/datasets/{type}      # Add dataset item
DELETE /api/v1/evaluation/datasets/{type}/{id} # Remove dataset item
GET    /api/v1/evaluation/runs                 # List eval runs
POST   /api/v1/evaluation/runs                 # Trigger eval run

# Admin
GET    /api/v1/admin/audit-log                 # Filterable audit log
GET    /api/v1/admin/users                     # List users
POST   /api/v1/admin/users                     # Create user
PATCH  /api/v1/admin/users/{id}                # Update user
DELETE /api/v1/admin/users/{id}                # Delete user

# Audit (SOC 2)
GET    /api/v1/admin/audit/ai                  # AI audit log (LLM calls)
GET    /api/v1/admin/audit/export              # Export audit data
GET    /api/v1/admin/audit/retention           # Get retention config
POST   /api/v1/admin/audit/retention           # Update retention config

# System
GET    /api/v1/health                          # Health check (all services)
```

---

## Key Patterns

- **LLM abstraction** (`app/common/llm.py`): Unified client for Anthropic/OpenAI/vLLM/Ollama. Cloud→local migration = change `LLM_PROVIDER` + base URL in `.env`
- **Multi-provider embeddings** (`app/common/embedder.py`): `EmbeddingProvider` protocol with 4 implementations (OpenAI, local, TEI, Gemini). Switch via `EMBEDDING_PROVIDER`
- **DI singletons** (`app/dependencies.py`): All clients via `@functools.cache` factory functions (20 factories, see `_ALL_CACHED_FACTORIES`)
- **Hybrid retrieval** (`app/query/retriever.py`): Qdrant dense+sparse with native RRF fusion + Neo4j multi-hop graph traversal + optional visual rerank
- **Agentic query** (`app/query/graph.py`): `create_react_agent` with 12 tools → `case_context_resolve` → `investigation_agent` → `verify_citations` → `generate_follow_ups`
- **Agentic tools** (`app/query/tools.py`): 12 `@tool` functions with `InjectedState` for security-scoped matter_id and privilege filters
- **6 autonomous agents**: Investigation Orchestrator, Citation Verifier, Case Setup Agent, Hot Doc Scanner, Contextual Completeness, Entity Resolution Agent (see `docs/agents.md`)
- **Case context** (`app/cases/`): Case Setup Agent extracts claims/parties/timeline from anchor doc, auto-injected into query graph via `context_resolver.py`
- **SSE streaming** (`app/query/router.py`): Sources sent before generation starts, then token-by-token LLM streaming via `graph.astream` + `get_stream_writer`
- **Auth + RBAC** (`app/auth/`): JWT access/refresh tokens, 4 roles, matter-scoped queries, privilege enforcement at data layer
- **Audit logging** (`app/common/middleware.py`): Every API call → `audit_log` table (user, action, resource, matter, IP)
- **AI audit logging** (`app/common/llm.py`): Every LLM call logged with prompt hash, tokens, latency → `ai_audit_log` table
- **Structured logging**: `structlog` with contextvars (`request_id`, `task_id`, `job_id`)
- **Feature flags**: 16 `ENABLE_*` flags (see `docs/feature-flags.md` for full reference)
- **Privilege at data layer**: Qdrant filter + SQL WHERE + Neo4j Cypher — never API-layer-only

---

## Implementation Rules

### DO
- **Stream everything**: SSE for queries, progress events for jobs
- **Cite every claim**: LLM responses must reference source documents with page numbers
- **Deduplicate entities aggressively**: Legal docs repeat names in many forms
- **Batch embedding calls**: Configurable batch size via `EMBEDDING_BATCH_SIZE`
- **Use Qdrant's native RRF**: Don't implement fusion in Python
- **Preserve original files**: Never modify uploads in MinIO; parse outputs go to separate prefix
- **Log everything**: Every query, retrieval, and LLM call → structlog
- **Retry with backoff**: All LLM API calls get 3 retries with exponential backoff (tenacity)
- **Inject security context via InjectedState**: Agent tools receive `matter_id` and privilege filters from graph state, never from LLM tool calls
- **Verify citations independently**: Post-agent `verify_citations` node checks each claim against source chunks; don't let LLM self-justify

### DON'T
- **Don't use LangChain**: Use LangGraph for orchestration, LlamaIndex for retrieval, Instructor for structured extraction
- **Don't use pgvector**: Qdrant for vectors (multi-vector support, metadata filtering)
- **Don't use Marker**: GPL-3.0 license
- **Don't use fixed-size chunking**: Use semantic boundaries (Docling document structure)
- **Don't store chat history in Redis**: PostgreSQL only (LangGraph PostgresCheckpointer). Redis = cache + broker
- **Don't call LLM for every NER**: GLiNER handles entity extraction at ~50ms/chunk. LLM only for relationship extraction on entity-rich chunks (feature-flagged)

---

## Development Workflow

```bash
# Start infrastructure
docker compose up -d

# Install Python deps
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Run migrations
alembic upgrade head

# Start API (terminal 1)
uvicorn app.main:app --reload --port 8000

# Start Celery worker (terminal 2)
celery -A workers.celery_app worker -l info

# Start React frontend (terminal 3)
cd frontend && npm install && npm run dev

# Run tests
pytest tests/ -v --cov=app
```

---

## See Also

### Architecture & Planning
- `ARCHITECTURE.md` — system design, tech stack, security model, data flow
- `ROADMAP.md` — milestones M0–M17, build status, test counts

### Reference Documentation (in `docs/`)
- `docs/modules.md` — all 16 domain modules with files, schemas, endpoints
- `docs/database-schema.md` — 27 tables, 13 migrations, full column reference
- `docs/feature-flags.md` — all 16 `ENABLE_*` flags with defaults and resource impact
- `docs/testing-guide.md` — test infrastructure, fixtures, CI/CD, patterns
- `docs/agents.md` — 6 LangGraph agents with state schemas, tools, flows
- `docs/CLOUD-DEPLOY.md` — GCP + Vercel deployment guide
- `docs/M13-FRONTEND-SPEC.md` — React frontend specification
- `docs/M6-BULK-IMPORT.md` — bulk import spec for pre-OCR'd datasets

### Configuration & Deployment
- `.env.example` — all configuration variables and feature flags
- `docker-compose.yml` — infrastructure services (dev: runs natively on Mac)
- `docker-compose.prod.yml` — full containerized stack (API + worker + Flower)
- `docker-compose.cloud.yml` — cloud overlay (Caddy reverse proxy + TLS)
- `docker-compose.local.yml` — local LLM stack (vLLM/Ollama, TEI)
- `.github/workflows/` — CI/CD (backend tests, frontend tests, evaluation)
