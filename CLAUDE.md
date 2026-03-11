# CLAUDE.md — NEXUS

Multimodal RAG investigation platform for legal document intelligence. Ingests, analyzes, and queries 50,000+ pages of mixed-format legal documents. Surfaces people, relationships, timelines, and patterns across a heterogeneous corpus.

*See `ARCHITECTURE.md` for full system design, tech stack, and data flow diagrams.*

**Status**: All 17 milestones complete (M0–M17). 905 backend + 35 frontend tests passing.
16 domain modules, 20 DI factories, 16 feature flags, 6 autonomous LangGraph agents.
Full local deployment with zero cloud API dependency.

---

## Session Rules

**These rules govern every interaction.** Read them first. Follow them exactly.

### Process

1. **Always start in plan mode** for any non-trivial task. Read the relevant code, understand the context, present an approach, and get approval before writing a single line. Trivial = single-line fix, typo, or a change the user has fully specified.
2. **Ask when uncertain — never assume.** If a requirement is ambiguous, an interface is unclear, or there are multiple valid approaches, stop and ask. A wrong assumption costs more than a question.
3. **Read before you write.** Always read the files you intend to modify. Understand the existing patterns, imports, and conventions in that specific file before making changes.
4. **Check `ROADMAP.md` for context.** Know which milestone is current, what's done, and what's planned. Don't build something that's already scoped for a later milestone, and don't break assumptions from completed milestones.
5. **Plans include tests.** Every plan/todo must include writing tests as an explicit step — not an afterthought.
6. **Finish the loop: implement → test → fix → verify → update ROADMAP → commit.** While iterating, run `pytest tests/test_{affected_modules}/ -v` for the modules you changed. Before the final commit, run the full suite using 4 parallel agents (see rule 39) to catch cross-module regressions. If tests fail, fix the issues and re-run until all tests pass. Only then update `ROADMAP.md` to reflect what was completed (check off items, update status, adjust test counts). Finally, commit all changes with a clear message. Work is not done until the roadmap is current and the commit is made.
7. **One concern per change.** Don't refactor adjacent code, add unrelated improvements, or "clean up" things that aren't part of the current task.
8. **When unsure about a library API, look it up.** Do not guess at method signatures, parameter names, or return types from memory. Libraries in this project (LangGraph, Qdrant client, Instructor, Docling, FastEmbed, GLiNER, etc.) evolve rapidly and your training data may be stale. Search the web for current official documentation, read the actual installed source in `.venv/`, or ask. Confidently writing an outdated or incorrect API call wastes more time than checking.
9. **High-blast-radius changes need confirmation.** Docker configs, Alembic migrations that drop/rename columns, dependency version changes, and anything touching auth middleware — always flag these and get explicit approval before applying.

### Code Quality — Library-First, Not Custom Code

**This is an integration project.** We stitch together well-maintained libraries and APIs — FastAPI, LangGraph, Qdrant client, Neo4j driver, Instructor, Docling, GLiNER, etc. We do NOT write custom implementations of things these libraries already do.

10. **Use the library's API as designed.** Don't wrap library calls in unnecessary abstractions. Don't build a "helper" around something that already has a clean API. If Qdrant has a method for it, use it. If Instructor handles it, let it. If LangGraph provides a pattern, follow it.
11. **No spaghetti code.** Every function should have a single clear responsibility. If you're writing a function longer than ~40 lines, it probably needs to be decomposed. If you're passing more than 5 parameters, you probably need a schema.
12. **DRY, but don't over-abstract.** Extract shared logic only when it's used in 3+ places. Two similar blocks of code are fine — a premature abstraction is worse than mild duplication.
13. **Follow existing patterns exactly.** The codebase has established conventions (detailed below). Match them. Don't introduce a new pattern for doing something the codebase already does a different way.
14. **No silent fallbacks.** Do not write `try/except` blocks that swallow errors and return degraded results. Do not write `if service_unavailable: use_fallback()` code. If something fails, it should fail loudly — raise the exception, log the error, return a clear error to the caller. Silent fallbacks mask bugs, make debugging nightmarish at scale, and erode trust in the system. If you believe a specific case genuinely needs graceful degradation, ask first and explain why.

### Type Safety & Schemas

15. **Type everything.** Every function signature, every return type, every variable where the type isn't obvious. Use Python 3.12+ syntax: `str | None`, `list[dict]`, not `Optional[str]`, not `List[Dict]`.
16. **Pydantic v2 for all data structures.** Request/response schemas, configuration, structured LLM output — all Pydantic `BaseModel`. Use `Field(...)` for validation constraints. No raw dicts crossing module boundaries.
17. **Schemas live in `schemas.py`.** Each domain module (`ingestion/`, `query/`, `entities/`, etc.) has its own `schemas.py`. Shared base models go in `app/common/models.py`. Don't define inline schemas in routers or services.
18. **Follow the naming convention:**
    - Request schemas: `{Domain}Request` (e.g., `QueryRequest`, `IngestRequest`)
    - Response schemas: `{Domain}Response`, `{Domain}ListResponse`, `{Domain}DetailResponse`
    - Enums: `StrEnum` for string enumerations (e.g., `JobStatus`, `DocumentType`)

### Module Organization

19. **Respect the module structure.** Each domain is `app/{domain}/` with:
    - `router.py` — FastAPI endpoints (thin: validation, DI, delegate to service)
    - `service.py` — Business logic, DB operations (`@staticmethod` methods, raw SQL via `sqlalchemy.text()`)
    - `schemas.py` — Pydantic models for that domain
    - `tasks.py` — Celery tasks (if the domain has background work)
20. **Routers are thin.** Routers validate input, call services, return responses. Business logic belongs in services, not routers.
21. **Services own data access.** All SQL lives in service methods. Services take `AsyncSession` as a parameter — the caller (router or DI) manages the transaction.
22. **New features may need a new module.** If a feature doesn't fit cleanly into an existing domain, create `app/{new_domain}/` following the same `router.py` / `service.py` / `schemas.py` pattern.
23. **Shared utilities go in `app/common/`.** Cross-cutting concerns: storage, LLM client, vector store wrapper, rate limiting, middleware.

### Database & Data Layer

24. **Raw SQL via `sqlalchemy.text()`.** No ORM. This is intentional — known query patterns, full control, minimal overhead. Always use named parameters (`:param`) to prevent SQL injection.
25. **Alembic for all schema changes.** Never modify the database schema without an Alembic migration. Run `alembic revision --autogenerate -m "description"` and review before applying.
26. **Every query must be matter-scoped.** All data endpoints filter by `matter_id`. This applies to SQL WHERE clauses, Qdrant payload filters, and Neo4j Cypher WHERE clauses. No exceptions.
27. **Privilege enforcement at the data layer.** Qdrant filter + SQL WHERE + Neo4j Cypher. Never rely on API-layer filtering alone.

### Async & Concurrency

28. **Async everywhere in the API.** All FastAPI routes, all service methods, all DB calls use `async`/`await`. No blocking I/O in the request path.
29. **Celery tasks are the exception.** Celery workers run synchronously. Use `asyncio.run()` wrappers when tasks need to call async code. Tasks create their own sync DB engine via `_get_sync_engine()`.

### Dependencies & Configuration

30. **All config from environment variables.** `app/config.py` (Pydantic Settings) is the single source. No hardcoded connection strings, API keys, or model names in code. New config → add to `Settings` class AND `.env.example`.
31. **DI via `app/dependencies.py`.** All service clients (LLM, Qdrant, Neo4j, MinIO, Redis) are singletons created through factory functions. Register new dependencies here, not in routers or services.
32. **Feature flags for new capabilities.** Anything experimental or optional gets an `ENABLE_*` flag in config, defaulting to `false`. Check the flag before initializing expensive resources.

### Error Handling & Logging

33. **Use `structlog` for all logging.** Bind context (`request_id`, `task_id`, `job_id`) via contextvars. Log at appropriate levels: `info` for operations, `warning` for degraded behavior, `error` for failures with stack traces.
34. **Retry with backoff on external calls.** All LLM API calls, embedding calls, and external service calls get `tenacity` retry with exponential backoff (3 attempts). Don't silently swallow failures.
35. **Raise `HTTPException` with clear detail messages.** Status codes must be accurate (400 for bad input, 401/403 for auth, 404 for not found, 422 for validation, 500 for server errors). Always use `raise HTTPException(...)` instead of `return JSONResponse(status_code=4xx/5xx)` — JSONResponse bypasses OpenAPI spec and response model validation.
36. **No bare `except: pass`.** Shutdown handlers and cleanup code must log failures at `warning` level. Silent exception swallowing masks resource leaks and makes debugging impossible.
37. **Redaction failures must raise.** Never silently skip pages that fail to parse during redaction. A privileged document silently skipping redaction is a legal liability. Fail loudly.
38. **Health endpoints: 503 for unhealthy.** Return HTTP 503 when any required service is down. Load balancers rely on status codes, not response body parsing.
39. **Run ruff before considering work done.** After writing Python code, run `ruff check --fix` and `ruff format` on changed files. The PostToolUse hook handles this automatically, but the rule documents the expectation.

### Testing

40. **Every new feature or bug fix needs tests.** Tests mirror the module structure: `tests/test_{domain}/`. Use the existing `conftest.py` fixtures (mock services, AsyncClient, patched lifespan).
41. **Mock external services, test your logic.** Tests should not require running infrastructure. Mock Qdrant, Neo4j, MinIO, Redis, LLM APIs. Test that your code calls them correctly with the right parameters.
42. **Celery task `.delay()` is sync.** Mock it with `MagicMock`, not `AsyncMock`.
43. **Parallel test execution.** When running the full test suite, use the Agent tool to split across 4 parallel agents by module group. Each agent runs in a worktree for isolation. This cuts wall-clock time from ~2min to ~30s. Use this grouping (balanced by test count):
    - **Agent 1** (~177 tests): `tests/test_query/`
    - **Agent 2** (~183 tests): `tests/test_ingestion/ tests/test_entities/`
    - **Agent 3** (~166 tests): `tests/test_common/ tests/test_documents/ tests/test_datasets/`
    - **Agent 4** (~218 tests): `tests/test_auth/ tests/test_cases/ tests/test_analytics/ tests/test_edrm/ tests/test_analysis/ tests/test_annotations/ tests/test_audit/ tests/test_evaluation/ tests/test_exports/ tests/test_redaction/ tests/test_scripts/ tests/test_gdrive/`

    Each agent runs: `.venv/bin/python3 -m pytest <dirs> -v -x --tb=short`
    Exclude `tests/test_e2e/` and `tests/test_integration/` from parallel runs (they need the full stack).
    Known pre-existing failures to exclude: `test_rerank_takes_top_10`, `test_v1_generator_exit`, `test_nested_features_populated`.

### Enterprise & Security

44. **No secrets in code.** API keys, passwords, JWT secrets — all from environment variables. Never commit `.env`. Update `.env.example` with placeholder values for any new secrets.
45. **Audit trail for every API call.** The audit logging middleware captures user, action, resource, matter, IP. Don't bypass it.
46. **CORS restricted.** Only configured origins. Never `allow_origins=["*"]` in production.
47. **Rate limiting on public endpoints.** Use the existing Redis sliding-window limiter via `Depends()`.

### Legal Domain Sensitivity

48. **Never leak document content in errors or logs.** This platform handles privileged legal documents. Error messages, tracebacks, and log entries must never contain raw document text, PII, or privileged material. Log document IDs and chunk IDs — not content. API error responses get clean detail messages, not `repr()` of internal state.
49. **All prompt templates in `prompts.py`.** Each domain module that uses LLM calls should centralize its prompt templates (see `app/query/prompts.py`). No prompt strings scattered across nodes, services, or extractors. This is critical for auditability, tuning, and legal review.

### Scale Awareness

50. **This is a 50k+ page corpus.** Always paginate DB queries, batch operations (embeddings, indexing, NER), and stream large results. Never load an entire collection or table into memory. A query that works with 100 docs will OOM or timeout at production scale.

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
- **Frontend (React)**: TanStack Router (type-safe). TanStack Query for server state. Zustand for client state. orval generates API hooks from OpenAPI spec (`npm run generate-api`). shadcn/ui components. Vitest + RTL for unit tests, Playwright for E2E.
- **Frontend styling**: Tailwind v4 + shadcn/ui + CVA only. No inline `style={}` for static values — use Tailwind classes. Inline styles are only acceptable for truly dynamic/computed values (data-driven positions, runtime transforms, D3 bindings). CSS custom properties use `--color-*` prefix (Tailwind v4 convention — e.g. `var(--color-muted)`, not `var(--muted)`).
- **Entity colors**: Centralized in `frontend/src/lib/colors.ts` (`ENTITY_COLORS` map + `entityColor()` helper) backed by CSS vars in `index.css`. Never duplicate color maps in graph components — import from `@/lib/colors`.

---

## Key Patterns

- **LLM abstraction** (`app/common/llm.py`): Unified client for Anthropic/OpenAI/vLLM/Ollama. Cloud→local migration = change `LLM_PROVIDER` + base URL in `.env`
- **Multi-provider embeddings** (`app/common/embedder.py`): `EmbeddingProvider` protocol with 5 implementations (OpenAI, Ollama, local, TEI, Gemini). Switch via `EMBEDDING_PROVIDER`
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
- **Frontend** (`frontend/`): React 19 + TanStack Router + orval (OpenAPI → TanStack Query hooks) + shadcn/ui + Zustand. Types generated from FastAPI OpenAPI spec
- **Evaluation** (`app/evaluation/`, `scripts/evaluate.py`): Ground-truth Q&A dataset, retrieval metrics (MRR/Recall/NDCG), faithfulness scoring, citation accuracy

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

## Dev Server Monitoring

### Log Monitor Agent (`.claude/agents/log-monitor.md`)

A reusable background agent that starts `make dev`, watches output for errors, queries LangSmith for pipeline-internal issues (errored traces, high-latency runs, tool failures), and maintains a persistent findings report. **Spawn it whenever the user starts a dev session or asks to run the server.**

**How to use:**
- Create a team (`TeamCreate`), then spawn the agent: `Agent(name="log-monitor", team_name="...", run_in_background=true)`
- The agent starts `make dev`, runs health checks, queries LangSmith (`nexus` project) for errored/slow traces, and alerts on critical issues via `SendMessage`
- Other agents (and you) can read findings at any time from the report file

**Findings report location:**
```
~/.claude/projects/-Users-julian-dev-NEXUS/memory/dev-server-findings.md
```

The report has four sections:
- **OPEN** — Actionable issues from server logs (severity, location, impact, fix). Any agent can pick these up.
- **WONTFIX** — Known upstream issues. Don't re-investigate.
- **LangSmith Traces** — Pipeline-internal issues from LangSmith (errored nodes, tool failures, high latency, token anomalies). Includes trace IDs for cross-referencing in the LangSmith UI.
- **FIXED** — Resolved issues with commit references.

**When to spawn the log monitor:**
- User says "start the server", "run make dev", "let's start developing"
- You need to verify code changes work at runtime (not just tests)
- Debugging a runtime error that only manifests in the running server
- Running E2E or integration tests that need the full stack

**When NOT to spawn it:**
- Pure code review or planning tasks
- Running unit tests only (`pytest`)
- Reading/exploring code without running it

---

## See Also

### Start Here (read for any task)
- `ARCHITECTURE.md` — System design, tech stack, security model, data flow
- `ROADMAP.md` — Milestones M0–M17, build status, test counts

### Module & API Reference (read when working on specific modules)
- `docs/modules.md` — All 16 domain modules with files, schemas, endpoints, and full API reference
- `docs/database-schema.md` — 27 tables, 13 migrations, full column reference
- `docs/agents.md` — 6 LangGraph agents with state schemas, tools, flows

### System Configuration (read when adding features or debugging)
- `docs/feature-flags.md` — All 16 `ENABLE_*` flags with defaults and resource impact
- `.env.example` — All configuration variables and feature flags
- `docs/testing-guide.md` — Test infrastructure, fixtures, CI/CD, patterns

### Deployment & Operations
- `docs/CLOUD-DEPLOY.md` — GCP + Vercel deployment guide (includes CI/CD setup, operations, backups)
- `docs/epstein-ingestion.md` — Dataset ingestion guide
- `docker-compose.yml` / `docker-compose.prod.yml` / `docker-compose.cloud.yml` / `docker-compose.local.yml`
- `deploy/nexus.service` — Systemd unit for auto-start on GCP VM
- `.github/workflows/` — CI/CD (backend tests, frontend tests, evaluation, GCP deploy)

### Historical Reference (completed milestone specs)
- `docs/M13-FRONTEND-SPEC.md` — React frontend specification
- `docs/M6-BULK-IMPORT.md` — Bulk import spec for pre-OCR'd datasets
- `docs/QA-AUDIT-FINDINGS.md` — QA audit findings
- `docs/NEXUS-Features-Overview.md` — Features overview
