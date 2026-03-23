# Changelog

All notable changes to NEXUS are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/). Versioning follows [Semantic Versioning](https://semver.org/) — see `CLAUDE.md` "Versioning & Releases" for the project-specific rules.

**How to update:** When tagging a new release, move items from `[Unreleased]` into a new version heading. Group entries under `Added`, `Changed`, `Fixed`, `Performance`, or `Removed`. Each entry is one line: `- Description (commit_hash)`.

---

## [Unreleased]

### Added
- RabbitMQ as Celery message broker — durable queues, publisher confirms, guaranteed redelivery on worker crash (b241664)
- `CELERY_BROKER_URL` config: set to `amqp://...` for RabbitMQ, leave empty for Redis fallback (backwards compatible)
- `docker-compose.gpu.yml` overlay for NVIDIA GPU passthrough (Ollama + TEI embedder)
- TEI embedding server (HuggingFace Text Embeddings Inference) with GPU support in GPU overlay
- `docs/celery-scaling.md` operational runbook for Celery worker scaling (hot-scaling, pool_grow, memory limits)
- GPU VM provisioning guide in `docs/CLOUD-DEPLOY.md` (T4/L4, spot pricing, disk snapshots)
- Weekly disk snapshot schedule for GPU VM backup (30-day retention)

## [1.15.1] - 2026-03-20

### Fixed
- Workers & Queues tab: active task duration showed "NaNm NaNs" — compute elapsed time from `started_at` timestamp instead of missing `runtime_seconds` field
- Workers & Queues tab: queue cards showed blank counts — use correct backend field names (`active_count`, `reserved_count`, `scheduled_count`)
- `formatDuration` guard against NaN/negative inputs

## [1.15.0] - 2026-03-20

### Added
- Epstein emails adapter (`epstein_emails`) for HuggingFace email datasets (aa3dc0c)
  - `to-be/epstein-emails`: 4,272 rows → 3,480 emails (flat schema, HTML body)
  - `notesbymuneeb/epstein-emails`: 5,082 threads → 13,008 messages (threaded JSON schema)
  - Auto-detects schema variant, strips HTML, cleans sender names, extracts email headers
  - Routes as `doc_type="email"` for full pipeline: chunking, Ollama embedding, email threading, communication analytics, email-as-node graph
- 19 adapter unit tests covering both schemas, dedup, malformed JSON, limit enforcement
- GCP: Phase 4 email import — 16,338 emails dispatched to Epstein Files Investigation matter (3,480 to-be + 12,858 muneeb, 150 deduped)

## [1.14.1] - 2026-03-20

### Added
- GCP: 25,791 House Oversight documents (69K chunks) imported with degraded citations
- Combined corpus: 29,969 documents, 305K chunks across FBI + House Oversight datasets

## [1.14.0] - 2026-03-20

### Added
- FBI dataset import pipeline: `import_fbi_dataset.py` with `--concurrency`, `--skip-ner`, `total_pages` support (ca9ab84)
- Deferred NER pass script: `run_ner_pass.py` with `ProcessPoolExecutor` for CPU parallelism (ca9ab84)
- `seed_epstein_matter.py`: FBI-specific defined terms, consolidated matter setup (5eedbef)
- 35 FBI import unit tests (ca9ab84)
- `entity_only` filter on entity connections endpoint (af716eb)
- GCP: 4,178 FBI documents (236K chunks) live with full citation support

### Changed
- GCP embedding config: switched from OpenAI text-embedding-3-large (1024d) to Ollama nomic-embed-text (768d)
- Dockerfile: pin `torch==2.6.0+cpu` + `torchvision==0.21.0+cpu` for GLiNER compatibility (2614384)

### Fixed
- `detect_schema()` FBI JSONL column aliases (`chunk_text`, `source_path`, `source_volume`) (ce31cf0)
- `seed_epstein_matter.py`: SQLAlchemy `::json` cast conflict + missing `anchor_document_id` (ce31cf0)
- `link_document_to_dataset()`: referenced non-existent `id` column in `dataset_documents` (ce31cf0)

## [1.13.3] - 2026-03-15

### Fixed
- Auto-detect Docker socket path on macOS — Operations page no longer 503s when Docker Desktop uses `~/.docker/run/docker.sock` (4f2ab0f)
- Stop frontend container polling on error — `ContainerGrid` no longer spams 10s refetch when Docker is unavailable (4f2ab0f)
- Update Vercel API rewrite to current GCP VM IP (35.223.187.80)
- Remove hardcoded deploy memory limits in `docker-compose.cloud.yml` — let Docker use available host memory instead of OOM-killing services
- Increase cloud API healthcheck `start_period` to 180s with 10 retries for cold boot scenarios

### Changed
- Deploy script handles ephemeral VM IP — fetches IP dynamically instead of hardcoding, prompts for `vercel.json` update when IP changes
- Deploy health check extended to 180s (60 retries x 3s) for cold boots with GLiNER model download
- DRY compose command in deploy script via `$COMPOSE` variable

## [1.13.2] - 2026-03-15

### Fixed
- Fix chat thread citations lost on reload — SSE-streamed sources from subgraph nodes were not persisted to `final_state`, causing empty `source_documents` in DB
- Add defensive JSONB parsing in `GET /chats/{threadId}` — malformed source documents or cited claims now skip gracefully instead of crashing the entire endpoint with a Pydantic `ValidationError`
- Add null guard for `relevance_score` in citation sidebar — prevents `NaN%` when score is missing
- Regenerate orval frontend types — sync `CitedClaim.filename` as optional to match backend schema

## [1.13.1] - 2026-03-14

### Fixed
- Wire up NDCG@10 and Precision@10 in evaluation runner — metrics were computed per-query but dropped before aggregation (`avg_ndcg = 0.0` hardcoded)
- Fix citation accuracy default from `1.0` to `0.0` when `total_claims=0` — perfect score was masking claim extraction failures
- Skip citation quality gates when `total_claims=0` — gates only fire when claims exist to evaluate
- Fix self-reflection false triggers — lower faithfulness threshold from 0.8 to 0.6, add `SELF_REFLECTION_MIN_CLAIMS=3` to skip reflection when too few claims exist
- Fix question decomposition over-classification — tighten prompt to require 2+ distinct sub-questions, add short query bypass (< 15 words)
- Fix multi-query expansion score pollution — weight original query results 1.0x vs variant results 0.7x during merge
- Improve `structured_query` tool description to prevent agent confusion with `vector_search` — explicitly state metadata-only use and add negative examples
- Fix gt-009 cross-cutting HTTP 500 — deep-tier timeline queries exceeded 120s eval timeout when flags enabled; resolved via recursion limit reduction and timeout increase
- Fix header layout overflow on mobile — matter/dataset selectors now use min-w-0/max-w constraints instead of fixed widths
- Move mobile nav trigger into header for proper responsive layout

### Performance
- Reduce `agentic_recursion_limit_deep` default from 60 to 40 — deep-tier timeline queries were exceeding eval timeouts when multiple flags enabled; 40 aligns with standard tier and prevents runaway agent loops
- Increase evaluation client timeout from 120s to 180s (`EVAL_QUERY_TIMEOUT_S` constant) — deep-tier queries with flag overhead legitimately need >120s; extracted hardcoded timeouts into single constant shared by `runner.py` and `flag_sweep.py`

### Changed
- Tune retrieval grading keyword weight from 0.4 to 0.2 (configurable via `RETRIEVAL_GRADING_KEYWORD_WEIGHT`) — legal documents use synonym-rich vocabulary where keyword overlap penalizes semantically correct results
- Add HyDE embedding blending — blend hypothetical doc embedding with original query embedding (configurable via `HYDE_BLEND_RATIO=0.5`) to reduce semantic drift
- Add `claim_extraction_rate` field to `CitationMetrics` — surfaces "claims extracted in N/M queries" instead of silent 100% accuracy
- Add multi-query expansion prompt constraint to preserve original query scope and entities
- Add LangSmith trace inspection section to `docs/evaluation-guide.md`
- Update QA evaluation report with gt-009 root cause analysis and verification results

## [1.13.0] - 2026-03-14

### Added
- Runtime tuning settings admin UI (`/admin/settings`) — 48 numeric/float settings (retrieval limits, thresholds, batch sizes, agent recursion limits, etc.) now configurable at runtime via admin page with DB persistence, same pattern as feature flags
- `setting_overrides` DB table (migration 028) for persisting admin-configured setting values across restarts
- `app/settings_registry/` module: registry (48 settings with type/range/unit metadata), service (CRUD + Settings mutation + DI cache clearing), router (admin-only REST endpoints)
- Settings grouped by category (Retrieval, Adaptive Depth, Query Pipeline, Agent, Ingestion, Visual Reranking, Auth & Limits) with risk level badges (Safe/Cache Clear/Restart)
- Feature flag gating: settings whose parent feature flag is disabled appear muted with "Flag Off" badge
- DB overrides loaded at startup (both early sync load in `create_app()` and async load in lifespan) alongside feature flag overrides
- Sidebar nav entry "Settings" with `SlidersHorizontal` icon in admin section
- 48 tests covering registry validation, service CRUD/load/coerce/range, and router endpoints

## [1.12.2] - 2026-03-14

### Fixed
- Fix `Settings()` → `get_settings()` in 6 agent tools (`topic_cluster`, `network_analysis`, `decompose_query`, `cypher_query`, `structured_query`, `get_community_context`) — runtime feature flag toggles were invisible to these tools because `Settings()` reads env vars only, not DB overrides
- Preserve `messages` field in `case_context_resolve` node — missing field caused LangGraph state merge to lose the user query, triggering `ValueError('contents are required')` on every chat query
- Replace bare `raise` with structured `HTTPException` in query router error handler — graph exceptions now return actionable error detail instead of opaque "Internal Server Error"
- Improve evaluation runner error capture: extract JSON `detail` field from structured error responses, increase error text capture from 200 to 500 chars

### Changed
- Update QA evaluation report with root cause analysis for CRITICAL (resolved in v1.11.0) and HIGH findings (resolved in this release)
- Add LangSmith MCP usage guide to `CLAUDE.md` for pipeline debugging
- Add regression guard tests: AST-based checks ensure `tools.py` never regresses to `Settings()` or `from app.config import Settings`

## [1.12.1] - 2026-03-14

### Fixed
- Fix `ValueError('contents are required')` when using Gemini as LLM provider — `build_system_prompt` now falls back to `HumanMessage(original_query)` when messages list is empty (V1 state routed to agentic graph)
- Translate `max_tokens` → `max_output_tokens` for Gemini provider in `_build_chat_model` (Gemini silently ignored the OpenAI-style parameter)

## [1.12.0] - 2026-03-14

### Added
- Agent clarification (human-in-the-loop): investigation agent can ask one clarifying question per query when it encounters ambiguity (multiple entity matches, unclear time ranges, etc.)
- `ask_user` tool using LangGraph `interrupt()` primitive — graph pauses, streams question via SSE, resumes when user responds
- `POST /query/resume` endpoint to continue a paused investigation after user answers clarification
- `ENABLE_AGENT_CLARIFICATION` feature flag (default off, runtime-toggleable, QUERY category)
- `ClarificationPrompt` frontend component with inline question/answer UI in the chat flow
- `CLARIFICATION_ADDENDUM` system prompt injection guiding when to ask vs. proceed
- 26 new tests (20 backend + 6 frontend) covering tool behavior, schema validation, prompt injection, and component rendering

## [1.11.1] - 2026-03-14

### Fixed
- Always mount OIDC/SAML routers so `/auth/oidc/info` and `/auth/saml/info` return 200 instead of 404 when SSO is disabled, eliminating browser console errors on login page

### Changed
- `enable_sso` and `enable_saml` feature flags downgraded from `RESTART` to `CACHE_CLEAR` risk level, enabling runtime toggling via admin UI without server restart

## [1.11.0] - 2026-03-14

### Added
- Load DB feature flag overrides in all Celery tasks so runtime toggles take effect on background workers (5ce9b5f)

### Fixed
- Auto graph routing selects V1 graph factory for fast-tier queries instead of always using agentic graph (5ce9b5f)

## [1.10.0] - 2026-03-14

### Performance
- Code-split frontend bundle and parallelize backend startup (dbb2e6a)

## [1.9.2] - 2026-03-14

### Added
- Dashboard stat cards are clickable links to their pages (b4ccdb9)

### Fixed
- Load DB feature flag overrides before conditional router mounting (f624a17)
- ServiceHealth import and render on dashboard (83b6a42)
- Remove @theme inline so CSS variable overrides enable theme switching (4c29376)

## [1.9.1] - 2026-03-14

### Added
- Theme toggle dropdown in header (1029345)

### Fixed
- Wire up theme toggle to actually switch dark/light mode (17889f7)

## [1.9.0] - 2026-03-14

### Added
- Service Operations admin page with Docker/Celery management (e6fa516)

## [1.8.0] - 2026-03-14

### Added
- Feature flag QA evaluation framework with LLM-as-judge scoring (2e90d98)
- Feature flag evaluation sweep harness (e6fd2fa)
- Tier 3 Phases 4-5: deposition prep, doc comparison, SPLADE, HalluGraph, GraphRAG, Helm (d0009d5)

### Fixed
- Dashboard health key mismatch, card links, mini graph visualization (9e98edb)
- Repair failing CI workflows (uv cache glob + npm peer deps) (e27f0d2)

## [1.7.0] - 2026-03-13

### Added
- Tier 3 Phase 3: mobile responsive, onboarding flow, interactive graph editing (09d9c4b)

### Fixed
- Patch Tier 3 stage gaps in streaming and ingestion tests (2197a98)
- 7 bugs in BGE-M3 + adaptive depth maturity advancement (926fd45)

## [1.6.0] - 2026-03-13

### Added
- Tier 3 Phase 1 fixes + Phase 2: BGE-M3 unified dense+sparse embedding provider (ab914eb)

## [1.5.0] - 2026-03-13

### Added
- Tier 3 Phase 1: dark mode, auto graph routing, adaptive retrieval, OCR correction, Matryoshka dims (78c3324)
- Complete Tier 2+3 implementation gaps: summarizer, chunk summarizer, sql_schema, metrics (1b4c392)

## [1.4.0] - 2026-03-12

### Added
- Tier 2 Ingestion + Observability: doc summaries, multi-repr indexing, metrics, quality monitoring (2aba874)
- Tier 2 RAG pipeline + query: HyDE, self-reflection, RRF tuning, text-to-SQL (63c9d6a)
- Tier 2 Frontend UX: passage linking, keyboard shortcuts, audit export (4d0aeaf)

## [1.3.0] - 2026-03-12

### Added
- Tier 1 maturity advancement: 10 items, RAG 8.5 to 9.0, Platform 8.5 to 9.2 (f64bfe2)

## [1.1.2] - 2026-03-12

### Added
- Tier 0 maturity advancement: SAML SSO, error redaction, privilege log, data retention, frontend tests (b37afac)

## [1.1.1] - 2026-03-12

### Added
- Auto-register LLM providers from environment on settings page (29d0342)

## [1.1.0] - 2026-03-12

### Added
- Runtime feature flag admin UI, tests, and docs (205d18f)
- M21 RAG quality improvements: contextual retrieval, CRAG grading, chunk scoring, reranking (4093c09)

## [1.0.2] - 2026-03-12

### Fixed
- Timeline co-entities, comms response_model, thread subject ordering (56e9463)
- Bright yellow citation highlight with inherited text color (fb02041)
- Expanded doc viewer height, citation highlight readability, retrieval tuning (6322b13)

## [1.0.1] - 2026-03-12

### Added
- Production-harden Celery with queue routing, time limits, revocation, and retry (2469050)
- Generalized background task visibility across all Celery task types (9972546)
- IngestionStatus component with job completion toasts and HealthBanner coordination (86bfdb0)
- Runtime LLM configuration with Gemini support and admin UI (6cb55ab)
- Google Drive connector with OAuth, encrypted token storage, and incremental sync (2108f67)

### Fixed
- Resolve 4 QA sweep issues: chat 404, dataset dupes, a11y, perf (cae3b0c)
- Entity timeline empty content and duplicate search bars on /entities (d696c67)
- Security audit: close cross-matter data leaks, unbreak redaction, harden auth (6c6f666)
- Production quality audit: close silent exception gaps and enforce HTTPException (8d53335)
- Chat closing after stream completion + get_llm() ignoring admin LLM config (a1c49e7)
- Streaming: clear agent thinking tokens before final answer (5f5fb5c)

## [1.0.0] - 2026-03-08

Initial release. All 22 milestones (M0-M21) complete.

### Added
- Multimodal RAG pipeline with hybrid retrieval (dense + sparse + summary vectors)
- 6 autonomous LangGraph agents with 17 tools
- Knowledge graph (Neo4j) with entity resolution and relationship extraction
- Auth + RBAC with JWT tokens, 4 roles, matter-scoped queries
- React 19 frontend with TanStack Router, citation sidebar, document viewer
- Celery background processing for ingestion, analysis, exports
- EDRM import/export with email intelligence
- Evaluation framework with retrieval metrics and faithfulness scoring
- Full local deployment with zero cloud API dependency
