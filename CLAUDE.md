# CLAUDE.md — NEXUS

Multimodal RAG investigation platform for legal document intelligence. Ingests, analyzes, and queries 50,000+ pages of mixed-format legal documents. Surfaces people, relationships, timelines, and patterns across a heterogeneous corpus.

*See `ARCHITECTURE.md` for full system design, tech stack, and data flow diagrams.*

**Status**: All 22 milestones complete (M0–M21) + Tier 2 Maturity + Tier 3 (all 15 items). ~1528 backend + 77 frontend tests passing.
20 domain modules, 23 DI factories, 48 feature flags (45 runtime-toggleable), 6 autonomous LangGraph agents, 17 agent tools.
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

### Concurrent Sessions & Git Safety

**Multiple Claude sessions often run in parallel on this repo.** A session committing its work must not destroy uncommitted changes from other sessions. Before any git operation that affects the working tree, **check `git status` first** and verify which files are yours.

- **Check before you act.** Run `git status` before committing, stashing, or restoring. If every dirty/untracked file is one you created or modified, blanket commands (`git stash`, `git add .`, `git restore .`) are safe. If you see files you didn't touch, another session is working on them — use targeted commands instead.
- **Stage by name when others are active.** If `git status` shows files you don't recognize, use `git add path/to/file1 path/to/file2` for only your files. Don't `git add -A` or `git add .` when the working tree contains other sessions' uncommitted work.
- **Never stash or restore when the tree has others' changes.** `git stash` and `git restore .` revert the entire working tree — including other sessions' files. Only use these when you've confirmed all dirty files are yours.
- **Destructive commands need extra care.** `git reset --hard`, `git clean -f`, and `git checkout .` are high-blast-radius. Even if you believe you're the only session, prefer targeted alternatives (`git restore <specific-file>`) or ask the user first.
- **Don't auto-resolve conflicts on others' files.** If a merge/rebase conflict involves files you didn't edit, stop and ask the user which version to keep.

### Versioning & Releases

This project uses [Semantic Versioning](https://semver.org/) with `v`-prefixed git tags (`v1.11.0`).

**Version bumping rules:**
- **Patch** (`v1.10.0` → `v1.10.1`): Bug fixes, typo corrections, test-only changes — no new behavior.
- **Minor** (`v1.10.0` → `v1.11.0`): New features, new endpoints, new flags, behavioral changes, performance improvements — anything that adds or changes capability.
- **Major** (`v1.x` → `v2.0.0`): Breaking API changes, schema migrations that drop data, or fundamental architecture shifts. Requires explicit user approval before tagging.

**When to tag:**
- Tag after every logical unit of work is committed — don't let multiple unrelated features pile up under one tag.
- A single commit can be a tag (e.g., a perf improvement). Multiple related commits can share a tag (e.g., a feature + its tests + a follow-up fix).
- Never tag uncommitted or untested work.

**How to tag:**
1. Update `CHANGELOG.md`: move items from `[Unreleased]` into a new version section with the current date. Group entries under `Added`, `Changed`, `Fixed`, `Performance`, or `Removed`.
2. Commit the changelog update: `git add CHANGELOG.md && git commit -m "chore: update changelog for vX.Y.Z"`
3. Create the annotated tag: `git tag -a vX.Y.Z -m "short description of what this release contains"`
4. Optionally push: `git push origin main --tags` (only when the user asks to push).

**Changelog format (`CHANGELOG.md`):**
- Follows [Keep a Changelog](https://keepachangelog.com/).
- Each version gets a `## [X.Y.Z] - YYYY-MM-DD` heading.
- Entries are grouped: `Added`, `Changed`, `Fixed`, `Performance`, `Removed`.
- Each entry is one line: `- Description (commit_hash)`.
- The `[Unreleased]` section at the top collects changes that haven't been tagged yet.

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
   Adding a new flag:
   1. `app/config.py` → add `enable_foo: bool = False` to `Settings`
   2. `.env.example` → add `ENABLE_FOO=false`
   3. `app/feature_flags/registry.py` → add `FlagMeta` entry (display name, description, category, risk level, DI caches to clear). The admin UI auto-discovers from this registry — no frontend changes needed.
   4. Gate the feature in the relevant module (check `settings.enable_foo`)
   5. If DI-gated: add a factory in `app/dependencies.py` returning `None` when disabled
   6. `docs/feature-flags.md` → document the flag

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
43. **Parallel test execution.** When running the full test suite, use the Agent tool to split across 4 parallel agents by module group (mirrors CI matrix shards in `.github/workflows/ci.yml`). Each agent runs in a worktree for isolation. This cuts wall-clock time from ~2min to ~30s. Use this grouping (balanced by test count):
    - **Agent 1 — query** (~408 tests): `tests/test_query/`
    - **Agent 2 — ingestion** (~408 tests): `tests/test_ingestion/ tests/test_entities/ tests/test_feature_flags/ tests/test_operations/`
    - **Agent 3 — core** (~430 tests): `tests/test_common/ tests/test_documents/ tests/test_llm_config/ tests/test_settings_registry/ tests/test_retention/ tests/test_health.py`
    - **Agent 4 — modules** (~424 tests): `tests/test_auth/ tests/test_cases/ tests/test_analytics/ tests/test_edrm/ tests/test_analysis/ tests/test_annotations/ tests/test_audit/ tests/test_evaluation/ tests/test_exports/ tests/test_redaction/ tests/test_scripts/ tests/test_gdrive/ tests/test_datasets/ tests/test_depositions/ tests/test_memos/`

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
- **Multi-provider embeddings** (`app/common/embedder.py`): `EmbeddingProvider` protocol with 6 implementations (OpenAI, Ollama, local, TEI, Gemini, BGE-M3). Switch via `EMBEDDING_PROVIDER`. BGE-M3 (`bgem3`) produces dense+sparse in a single forward pass
- **DI singletons** (`app/dependencies.py`): All clients via `@functools.cache` factory functions (23 factories, see `_ALL_CACHED_FACTORIES`)
- **Hybrid retrieval** (`app/query/retriever.py`): Qdrant dense+sparse with native RRF fusion + Neo4j multi-hop graph traversal + optional visual rerank
- **Agentic query** (`app/query/graph.py`): `create_react_agent` with 16 tools (+1 `ask_user` when clarification enabled) → `case_context_resolve` → `investigation_agent` → `verify_citations` → optional `reflect` → `generate_follow_ups`
- **Agentic tools** (`app/query/tools.py`): 17 `@tool` functions with `InjectedState` for security-scoped matter_id and privilege filters
- **6 autonomous agents**: Investigation Orchestrator, Citation Verifier, Case Setup Agent, Hot Doc Scanner, Contextual Completeness, Entity Resolution Agent (see `docs/agents.md`)
- **Case context** (`app/cases/`): Case Setup Agent extracts claims/parties/timeline from anchor doc, auto-injected into query graph via `context_resolver.py`
- **SSE streaming** (`app/query/router.py`): Sources sent before generation starts, then token-by-token LLM streaming via `graph.astream` + `get_stream_writer`
- **Auth + RBAC** (`app/auth/`): JWT access/refresh tokens, 4 roles, matter-scoped queries, privilege enforcement at data layer
- **Audit logging** (`app/common/middleware.py`): Every API call → `audit_log` table (user, action, resource, matter, IP)
- **AI audit logging** (`app/common/llm.py`): Every LLM call logged with prompt hash, tokens, latency → `ai_audit_log` table
- **Structured logging**: `structlog` with contextvars (`request_id`, `task_id`, `job_id`)
- **Feature flags**: 36 `ENABLE_*` flags, 34 runtime-toggleable via admin UI (see `docs/feature-flags.md` for full reference)
- **Runtime feature flags** (`app/feature_flags/`): Admin UI toggle, DB override persistence, DI cache clearing, risk-level gating
- **LLM config management** (`app/llm_config/`): Runtime provider CRUD, tier assignment, auto-registration from env vars, model discovery, cost estimation
- **RAG quality pipeline**: Chunk quality scoring → contextual enrichment → CRAG grading (heuristic + conditional LLM) → reranking (enabled by default)
- **HyDE** (`app/query/hyde.py`): Hypothetical Document Embeddings — embed hypothetical answer for dense retrieval, raw query for sparse
- **Self-reflection** (`app/query/graph.py`): Conditional retry loop after citation verification when faithfulness < threshold
- **Multi-representation** (`app/ingestion/chunk_summarizer.py`, `app/common/vector_store.py`): Triple RRF fusion (dense + sparse + summary vectors)
- **Document summarization** (`app/ingestion/summarizer.py`): LLM-generated 2-3 sentence summaries at ingestion
- **Text-to-SQL** (`app/query/sql_generator.py`): Matter-scoped read-only SQL from natural language with safety validation
- **Production quality monitoring** (`app/query/quality_monitor.py`): Sampled scoring of retrieval relevance + faithfulness + alerting
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
- **Don't store chat history in Redis**: PostgreSQL only (LangGraph PostgresCheckpointer). Redis = cache + result backend. RabbitMQ = Celery broker (via `CELERY_BROKER_URL`, falls back to Redis if unset)
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

### LangSmith MCP (`nexus` project)

Use the LangSmith MCP tools to debug pipeline internals. The `nexus` project logs all LangGraph runs.

**When to use:**
- Investigating HTTP 500s or unexpected query results — find errored traces with `fetch_runs`
- QA evaluation analysis — cross-reference evaluation failures with actual trace errors
- Performance debugging — find high-latency runs and identify slow nodes/tools
- After E2E or integration tests — verify the pipeline executed the expected path
- Monitoring production quality — spot tool failures, token anomalies, or unexpected agent behavior

**Key operations:**
- `mcp__langsmith__fetch_runs(project_name="nexus", limit=20, error="true")` — find errors
- `mcp__langsmith__fetch_runs(project_name="nexus", limit=10, filter='gt(latency, "10s")')` — find slow runs
- `mcp__langsmith__get_thread_history(project_name="nexus", thread_id="...")` — trace a conversation
- `mcp__langsmith__list_projects()` — verify project exists

**When NOT to use:** Unit tests (mocked, no LangSmith traces), code review, planning.

---

## See Also

### Start Here (read for any task)
- `ARCHITECTURE.md` — System design, tech stack, security model, data flow
- `ROADMAP.md` — Milestones M0–M21, build status, test counts
- `CHANGELOG.md` — Version history with grouped changes per release

### Module & API Reference (read when working on specific modules)
- `docs/modules.md` — All 19 domain modules with files, schemas, endpoints, and full API reference
- `docs/database-schema.md` — 36 tables, 24 migrations, full column reference
- `docs/agents.md` — 6 LangGraph agents with state schemas, tools, flows

### System Configuration (read when adding features or debugging)
- `docs/feature-flags.md` — All 29 `ENABLE_*` flags with defaults and resource impact
- `.env.example` — All configuration variables and feature flags
- `docs/testing-guide.md` — Test infrastructure, fixtures, CI/CD, patterns

### Deployment & Operations
- `docs/CLOUD-DEPLOY.md` — GCP + Vercel deployment guide (includes CI/CD setup, operations, backups)
- `docs/epstein-ingestion.md` — Dataset ingestion guide
- `docker-compose.yml` / `docker-compose.prod.yml` / `docker-compose.cloud.yml` / `docker-compose.local.yml`
- `deploy/nexus.service` — Systemd unit for auto-start on GCP VM
- `.github/workflows/` — CI/CD (backend tests, frontend tests, evaluation, GCP deploy)

### Evaluation & Quality
- `docs/evaluation-guide.md` — Feature flag QA evaluation framework (how to run, architecture, ground-truth)
- `docs/qa-evaluation-report.md` — Latest feature flag evaluation results and recommendations

### Historical Reference (completed milestone specs)
- `docs/M13-FRONTEND-SPEC.md` — React frontend specification
- `docs/M6-BULK-IMPORT.md` — Bulk import spec for pre-OCR'd datasets
- `docs/QA-AUDIT-FINDINGS.md` — QA audit findings
- `docs/NEXUS-Features-Overview.md` — Features overview
