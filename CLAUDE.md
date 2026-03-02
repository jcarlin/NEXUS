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

---

## Architecture

```
MinIO (S3)  ──>  Celery Workers  ──>  Parse ──> Chunk ──> Embed ──> Extract ──> Index
  (upload)        (background)       Docling    Semantic   Dense+     GLiNER     Qdrant
                                     stdlib*    (512 tok)  Sparse     Instructor  Neo4j

FastAPI  ──>  Auth (JWT/RBAC)  ──>  LangGraph Agentic Pipeline  ──>  Hybrid Retrieval
  /query       matter scoping       classify_and_plan                 Qdrant native RRF
  /stream      privilege filter     > execute_action (tool-use)       + Neo4j multi-hop
               audit logging        > assess_sufficiency              + cross-encoder rerank
                                    > synthesize (structured output)  + privilege filtering
```

*stdlib = `email` + `extract-msg` + `striprtf` for EML/MSG/RTF/CSV/TXT
*See `ARCHITECTURE.md` for full system design*

---

## Tech Stack

### Infrastructure
| Component | Technology | Notes |
|---|---|---|
| API | FastAPI 0.115+ | Async, OpenAPI docs, DI, JWT auth middleware |
| Task Queue | Celery 5.5+ / Redis | Background ingestion pipeline |
| Object Storage | MinIO (S3-compat) | Bucket webhook triggers ingestion |
| Metadata DB | PostgreSQL 16 | Users, matters, jobs, documents, chat, audit, LangGraph checkpointer |
| Vector DB | Qdrant v1.13.2 | Named dense+sparse vectors, native RRF fusion |
| Knowledge Graph | Neo4j 5.x | Entity graph, multi-hop traversal, path-finding, temporal queries |
| Cache/Broker | Redis 7+ | Celery broker, rate limiting, response cache |

### AI Models
| Role | Current Implementation |
|---|---|
| LLM (reasoning) | Claude Sonnet 4.5 via Anthropic API |
| Text Embeddings | OpenAI `text-embedding-3-large` (1024d) |
| Sparse Embeddings | FastEmbed `Qdrant/bm42-all-minilm-l6-v2-attentions` (feature-flagged: `ENABLE_SPARSE_EMBEDDINGS`) |
| Zero-shot NER | GLiNER (`gliner_multi_pii-v1`, CPU) |
| Structured Extract | Instructor + Claude (feature-flagged: `ENABLE_RELATIONSHIP_EXTRACTION`) |
| Reranker | `bge-reranker-v2-m3` on MPS (feature-flagged: `ENABLE_RERANKER`) |
| Visual Embeddings | **Not yet** — planned: ColQwen2.5 (`ENABLE_VISUAL_EMBEDDINGS=false`) |

### Document Processing
| File Types | Parser |
|---|---|
| PDF, DOCX, XLSX, PPTX, HTML, images | Docling 2.70+ |
| EML | Python `email` stdlib |
| MSG | `extract-msg` |
| RTF | `striprtf` |
| CSV, TXT | Python stdlib |
| ZIP | `zipfile` stdlib → route contents by extension |

### Orchestration
| Component | Technology |
|---|---|
| Query orchestration | LangGraph (agentic tool-use loop with PostgresCheckpointer) |
| Retrieval primitives | LlamaIndex (core only) |
| Structured output | Instructor 1.14+ |

---

## Project Structure

```
nexus/
├── CLAUDE.md                              # This file
├── ARCHITECTURE.md                        # System design, tech stack, security model
├── ROADMAP.md                             # Milestones, build status, dependencies
├── docker-compose.yml                     # Infra services only (Redis, PG, Qdrant, Neo4j, MinIO)
├── docker-compose.prod.yml                # Full stack (adds API, worker, Flower)
├── docker-compose.cloud.yml               # Cloud overlay (adds Caddy reverse proxy + TLS)
├── Dockerfile
├── Caddyfile                              # Caddy reverse proxy config (API + MinIO + TLS)
├── .env.example                           # All configuration variables
├── .env.cloud.example                     # Cloud deployment env template
├── pyproject.toml                         # Python 3.12+, uv/pip
├── alembic.ini
│
├── app/
│   ├── main.py                            # FastAPI app factory + lifespan
│   ├── config.py                          # Pydantic Settings (all config from env)
│   ├── dependencies.py                    # DI: LLM clients, Qdrant, Neo4j, MinIO, Redis
│   │
│   ├── ingestion/
│   │   ├── router.py                      # POST /ingest, /ingest/batch, /ingest/webhook
│   │   ├── service.py                     # Orchestrates parse → chunk → embed → extract → index
│   │   ├── tasks.py                       # Celery tasks (6-stage pipeline)
│   │   ├── parser.py                      # Routes files to Docling / stdlib parsers
│   │   ├── chunker.py                     # Semantic chunking (512 tok, 64 overlap)
│   │   ├── embedder.py                    # OpenAI text-embedding-3-large
│   │   └── schemas.py                     # IngestRequest, JobStatus, DocumentMeta
│   │
│   ├── query/
│   │   ├── router.py                      # POST /query, /query/stream (SSE), chat endpoints
│   │   ├── graph.py                       # LangGraph state graph definition
│   │   ├── nodes.py                       # Graph nodes: classify, rewrite, retrieve, rerank, etc.
│   │   ├── retriever.py                   # HybridRetriever: Qdrant RRF + Neo4j
│   │   ├── prompts.py                     # All prompt templates
│   │   └── schemas.py                     # QueryRequest, QueryResponse, ChatMessage
│   │
│   ├── entities/
│   │   ├── router.py                      # GET /entities, /entities/{id}/connections, /graph/*
│   │   ├── extractor.py                   # GLiNER NER pipeline
│   │   ├── relationship_extractor.py      # Instructor + Claude (feature-flagged)
│   │   ├── resolver.py                    # Entity resolution (rapidfuzz + embedding + union-find)
│   │   ├── graph_service.py               # Neo4j operations (multi-hop, path-finding, temporal)
│   │   ├── tasks.py                       # Background entity tasks
│   │   └── schemas.py                     # Entity, Relationship, GraphExploreResponse
│   │
│   ├── documents/
│   │   ├── router.py                      # GET /documents, /{id}, /{id}/preview, /{id}/download
│   │   ├── service.py                     # MinIO operations, metadata CRUD (raw SQL)
│   │   └── schemas.py                     # Document, DocumentList, DocumentDetail
│   │
│   ├── auth/                              # JWT auth, RBAC, API keys, matter scoping
│   │   ├── router.py                      # POST /auth/login, /auth/refresh, GET /auth/me
│   │   ├── service.py                     # JWT creation, password hashing, role checks
│   │   ├── middleware.py                  # Auth + RBAC + matter scoping middleware
│   │   └── schemas.py                     # User, Token, Role schemas
│   │
│   └── common/
│       ├── middleware.py                   # CORS, request logging, error handling, audit logging
│       ├── storage.py                     # MinIO/S3 client wrapper
│       ├── llm.py                         # LLM client factory (Anthropic/OpenAI/vLLM)
│       ├── vector_store.py                # Qdrant client wrapper
│       ├── rate_limit.py                  # Redis sliding-window rate limiter
│       └── models.py                      # Shared base models
│
├── workers/
│   └── celery_app.py                      # Celery config, task autodiscovery
│
├── migrations/
│   └── versions/                          # Alembic migrations
│
├── frontend/
│   ├── vercel.json                        # Vercel build/routing config
│   └── ...                                # React 19 + Vite dashboard
│
├── scripts/
│   ├── cloud-deploy.sh                    # GCP deployment automation
│   ├── cloud-teardown.sh                  # GCP resource cleanup
│   ├── seed_admin.py                      # Initial admin user creation
│   ├── import_dataset.py                  # Bulk dataset import
│   └── ...
│
├── evaluation/
│   └── ...                                # Ground-truth Q&A, metrics, regression tests
│
├── docs/
│   ├── CLOUD-DEPLOY.md                    # Cloud deployment guide (GCP + Vercel)
│   ├── M6-BULK-IMPORT.md                  # Bulk import spec
│   └── archive/                           # Superseded design documents
│
└── tests/
    ├── conftest.py                        # Fixtures: mock services
    ├── test_ingestion/
    ├── test_query/
    ├── test_entities/
    ├── test_documents/
    └── test_common/
```

---

## API Endpoints

```
# Authentication
POST   /api/v1/auth/login               # JWT token issuance
POST   /api/v1/auth/refresh             # Token refresh
GET    /api/v1/auth/me                  # Current user profile

# Ingestion
POST   /api/v1/ingest                    # Single file upload
POST   /api/v1/ingest/batch              # Multi-file upload (accepts ZIP)
POST   /api/v1/ingest/webhook            # MinIO bucket notification handler
GET    /api/v1/jobs/{job_id}             # Job status + progress
GET    /api/v1/jobs                      # List all jobs (paginated)

# Query & Chat
POST   /api/v1/query                     # Synchronous query (full response)
POST   /api/v1/query/stream              # SSE streaming query
GET    /api/v1/chats                     # List chat threads
GET    /api/v1/chats/{thread_id}         # Full chat history
DELETE /api/v1/chats/{thread_id}         # Delete chat thread

# Documents
GET    /api/v1/documents                 # List documents (filterable)
GET    /api/v1/documents/{id}            # Document metadata + chunks
GET    /api/v1/documents/{id}/preview    # Page thumbnail (presigned URL)
GET    /api/v1/documents/{id}/download   # Original file (presigned URL)
PATCH  /api/v1/documents/{id}/privilege  # Privilege tagging (attorney+)

# Knowledge Graph
GET    /api/v1/entities                  # Search/list entities
GET    /api/v1/entities/{id}             # Entity details + connections
GET    /api/v1/entities/{id}/connections # Graph neighborhood
GET    /api/v1/graph/explore             # Graph exploration (Cypher)
GET    /api/v1/graph/stats               # Graph statistics

# Admin
GET    /api/v1/admin/audit-log           # Filterable audit log (admin-only)
GET    /api/v1/admin/users               # User management (admin-only)
POST   /api/v1/admin/users              # Create user (admin-only)

# System
GET    /api/v1/health                    # Health check (all services)
```

---

## Key Patterns

- **LLM abstraction** (`app/common/llm.py`): Unified client for Anthropic/OpenAI/vLLM. Cloud→local migration = change `LLM_PROVIDER` + `VLLM_BASE_URL` in `.env`
- **DI singletons** (`app/dependencies.py`): All clients (LLM, Qdrant, Neo4j, MinIO, Redis) via `@lru_cache` factory functions
- **Hybrid retrieval** (`app/query/retriever.py`): Qdrant dense+sparse with native RRF fusion + Neo4j multi-hop graph traversal
- **Agentic query** (`app/query/graph.py`): classify_and_plan → execute_action (tool-use loop) → assess_sufficiency → synthesize (structured `CitedClaim` output)
- **SSE streaming** (`app/query/router.py`): Sources sent before generation starts, then token-by-token LLM streaming via `graph.astream` + `get_stream_writer`
- **Auth + RBAC** (`app/auth/`): JWT access/refresh tokens, 4 roles, matter-scoped queries, privilege enforcement at data layer
- **Audit logging** (`app/common/middleware.py`): Every API call → `audit_log` table (user, action, resource, matter, IP)
- **Structured logging**: `structlog` with contextvars (`request_id`, `task_id`, `job_id`)
- **Feature flags**: `ENABLE_VISUAL_EMBEDDINGS`, `ENABLE_RELATIONSHIP_EXTRACTION`, `ENABLE_RERANKER`, `ENABLE_SPARSE_EMBEDDINGS` (all `false` by default)
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

# Start Streamlit frontend (terminal 3)
uv pip install -e ".[frontend]"
streamlit run frontend/app.py

# Run tests
pytest tests/ -v --cov=app
```

---

## See Also

- `ARCHITECTURE.md` — system design, tech stack, security model, data flow
- `ROADMAP.md` — milestones, build status, dependencies (M5b→M17)
- `.env.example` — all configuration variables and feature flags
- `docs/CLOUD-DEPLOY.md` — cloud deployment guide (GCP + Vercel)
- `docs/M6-BULK-IMPORT.md` — bulk import spec for pre-OCR'd datasets
- `docker-compose.yml` — infrastructure services (dev: runs natively on Mac)
- `docker-compose.prod.yml` — full containerized stack (API + worker + Flower)
- `docker-compose.cloud.yml` — cloud overlay (adds Caddy reverse proxy + TLS)
