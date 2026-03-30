# Changelog

All notable changes to NEXUS are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/). Versioning follows [Semantic Versioning](https://semver.org/) — see `CLAUDE.md` "Versioning & Releases" for the project-specific rules.

**How to update:** When tagging a new release, move items from `[Unreleased]` into a new version heading. Group entries under `Added`, `Changed`, `Fixed`, `Performance`, or `Removed`. Each entry is one line: `- Description (commit_hash)`.

---

## [Unreleased]

## [1.20.0] - 2026-03-30

### Added
- OCR auto-detection: `ENABLE_DOCLING_OCR=auto` uses pypdfium2 text-layer sampling to skip OCR model loading on text-based PDFs, with two-converter cache (ocr/no_ocr) (0a7b100)
- MIG horizontal scaling infra: queue metric exporter (RabbitMQ → Cloud Monitoring), satellite worker startup script, MIG creation with queue-depth autoscaler (0-12 spot VMs, scales to zero), image push and teardown scripts (0a7b100)

### Changed
- `ENABLE_DOCLING_OCR` is now a 3-way string (`auto`/`true`/`false`) instead of boolean; default changed from `true` to `auto` (0a7b100)

### Fixed
- NER worker scripts: `nexus-gpu` → `nexus-ingest` VM references, added MinIO port 9000 to firewall rule (0a7b100)

## [1.19.0] - 2026-03-30

### Added
- Dedicated NER worker pool — `docker-compose.ingest.yml` now splits workers into general (default/bulk/background queues) and NER-only pools to prevent queue starvation during bulk ingestion (d19c980)
- Ingestion VM setup section in `docs/CLOUD-DEPLOY.md` — documents worker separation, GCS mount, scaling commands, verification procedures, and recommended `.env` tuning for the `nexus-ingest` VM (6fa9bd8, 89f2d5d)
- 7 comprehensive mermaid diagrams in `ARCHITECTURE.md` — system architecture, ingestion pipeline, query pipeline (LangGraph state graph), hybrid retrieval, worker & queue architecture, knowledge graph schema, data flow across stores, and full PostgreSQL ER diagram with all 36 tables and columns (0493a55)

### Performance
- Tune worker thread limits — `OMP_NUM_THREADS=4` / `MKL_NUM_THREADS=4` for ONNX operations (Docling OCR, FastEmbed BM42 sparse embeddings); recommended `CELERY_CONCURRENCY=2` with 3 general worker replicas for 16-vCPU VMs (a4e5fed, 9c8b386, 8aaec43)

### Fixed
- Pipeline Monitor Processing card now falls back to Celery active task count when PostgreSQL reports zero processing jobs (db5cebc)

### Infrastructure
- `nexus-ingest` VM (e2-standard-16, 16 vCPU / 64GB) actively ingesting EFTA corpus; upgrade to e2-standard-32 (32 vCPU / 128GB) underway to increase worker parallelism

## [1.18.0] - 2026-03-29

### Added
- EFTA corpus retrieval QA evaluation framework with 30 curated ground-truth questions across 3 difficulty levels, covering 16+ retrieval strategies (87e4b8d)
- `scripts/sample_corpus.py` — corpus discovery script that queries the live API to extract entities, document types, graph stats, and relationship clusters (87e4b8d)
- `scripts/build_efta_ground_truth.py` — semi-automated ground-truth builder with template-based question generation and optional API answer proposals (87e4b8d)
- `--dataset` CLI parameter for `scripts/evaluate.py` to target alternate ground-truth files (87e4b8d)

## [1.17.0] - 2026-03-29

### Added
- Wire `record_event()` into ingestion pipeline for Pipeline Monitor Events tab (c026ffa)

### Fixed
- Fix citation extraction: rewrite VERIFY_CLAIMS_PROMPT / VERIFY_JUDGMENT_PROMPT with explicit JSON output framing and one-shot examples; add markdown code fence stripping for Gemini responses (424a8ae)
- Fix HTTP 500 on out-of-scope queries: add scope guard to agent prompt (max 2 search attempts before declaring out-of-scope), change GraphRecursionError from 500 to 422 (424a8ae)
- Fix zero-source answers penalizing retrieval metrics: add `no_sources_returned` flag, exclude from MRR/NDCG aggregation (424a8ae)
- Add "always cite source documents" instruction to prevent case-context-only answers without evidence (424a8ae)
- Fix gt-016 ground truth: update non-existent `test-contract.txt` reference to actual `contract_excerpt_merger.txt` (424a8ae)

## [1.16.2] - 2026-03-29

### Fixed
- Skip deferred NER dispatch for zero-chunk documents — 33% of EFTA scanned PDFs produce no text, wasting worker cycles on guaranteed no-op NER tasks (44c6bfe)
- Fix Neo4j dual-event-loop bug in deferred NER — async driver create, graph write, and close now run within a single `asyncio.run()` call, fixing silent entity write failures (44c6bfe)
- Reduce ingest worker replicas from 8 to 5 to prevent CPU oversubscription on 16-core VM (44c6bfe)

## [1.16.1] - 2026-03-28

### Fixed
- Drop `[redis]` extra from celery to resolve redis>=7.0 vs kombu<6.5 dependency conflict (99d8e68)
- Fix flag count test to account for non-`enable_*` registered flags like `defer_ner_to_queue` (99d8e68)
- Add missing `get_query_graph` mock to `test_resume_endpoint_exists` broken by langgraph-checkpoint-postgres 3.x (99d8e68)
- Regenerate frontend lockfile after package.json version bumps (99d8e68)

## [1.16.0] - 2026-03-28

### Added
- Pipeline monitoring overhaul — error details, health strip, failure analysis, events log, script tracker (1b3ef73)
- TaskTracker for external script visibility in Pipeline Monitor > Scripts tab (97dee42)
- Per-chat retrieval strategy overrides with numeric tuning + inline dev trace panel (185678e, f63b9d4)
- Admin page visibility toggles — toggle sidebar pages on/off (1d1568a)
- Dynamic pipeline architecture diagram admin page with Data tab (PostgreSQL, Qdrant, Neo4j schemas) (93416b8, e8f5d7b, 12db992)
- Redesigned chat empty state — hero input centered on page, moves to bottom on send (70082c5, f532289)
- Persist view state across navigation — filters, sorting, pagination, tabs (956dc62)
- Bulk import drill-down with expandable rows, per-job tracking, bulk retry + dismiss (33a9d1d, a164ec4)
- Live toggle and semantic status badges to Pipeline Monitor (1f5dd87)
- Host system metrics card on dashboard (CPU, memory, disk) + GPU metrics (ba26dd4, 76b9189)
- Document size and page count stats in dashboard, documents table, and pipeline monitor (2fcc29b, 9706292, c71b55d)
- NER memory guard + deferred NER dispatch script with `--force-all` flag (d4664d0, dd4aa32)
- DOJ EFTA ingestion infra — configurable NER batch size, quality threshold, worker VM scripts (9b2263e)
- PDF bulk import and download scripts for Phases 5-6 (977faca)
- `--re-embed` flag for pre-embedded dataset import (24352b7)
- CO_OCCURS edges between entities sharing a document (f9792f7)
- Infinity embedding + reranker providers for GPU inference, replacing TEI (eee5333, c347ee6)
- vLLM service in GPU overlay (profile-gated, opt-in) (78161a5)
- RabbitMQ as Celery message broker — durable queues, publisher confirms, guaranteed redelivery (b241664)
- Celery Beat service for periodic orphan job recovery (117a5db, 9b4b251)
- Celery worker autoscaler based on CPU load (c149f3a)
- Manual VM control workflow (start/stop/status) (530fd44)
- `docker-compose.gpu.yml` overlay for NVIDIA GPU passthrough (Ollama + Infinity)
- GPU VM provisioning guide, celery scaling runbook, local LLM feasibility analysis (docs)

### Changed
- Dashboard moved to admin section (956dc62)
- Vercel API rewrites point to GPU VM (d78181d)
- NER_WORKER_CONCURRENCY default set to 5 (8374a41)

### Fixed
- Use documents.id instead of job_id for Qdrant/Neo4j indexing (03e508a)
- Validate matter_id FK before job INSERT to prevent IntegrityError (493ea58)
- Database hardening — injection allowlists, Qdrant indexes, pool configs, Neo4j scoping (c2bfbfa)
- Always verify citations regardless of query tier (fb80cf0)
- Entity detail graph shows only entity nodes, not documents (2339143)
- Overhaul entity extraction pipeline — OCR normalization, garbage filtering, entity→chunk edges (d9c71c0)
- Filter pronoun/stopword entities from GLiNER extraction (1cb7b2f)
- Pipeline page freeze and infinite re-render loops (db3027d, b61451a, c977894, 4a85a93, 428fe21, 3afb2ba, a6c66b6)
- Chat navigation bugs — New button redirect + history click race (dc7b3fb)
- Bulk import progress: mark complete only when all subtasks finish, counter sync cap, idempotent doc creation (91adade, 940200f, 4f8eb0a, 4be39d9, a67ff6d)
- Architecture page — API key bug fix, CSS polish, inline toggles (5f2de16)
- GPU metrics reading via aiodocker exec (cc834d8, 7f64bba)
- Queue controls cards showing 0 + add NER queue to admin UI (c764ac3)
- Reconcile Qdrant doc_id for bulk-imported documents (74327c9)
- Add libgl1 + libglib2.0 to Docker runtime for Docling OCR (3f77afc)
- Address memory audit findings — blob URL leak, polling dedup, D3 graph stability (abb0734)
- Resolve 4 CI failures (f63b9d4)
- Bump API container memory limit to 3G for GLiNER warmup (35650a7)
- AsyncGraphDatabase driver in deferred NER task (66005ee)
- Infinity GPU image fixes — torch engine, CUDA config, runtime selection (94c8645, 16999cc, 257bf23, c4b9cbbf)
- TEI turing-1.9 image for T4 GPU compute cap 75 (af7b3f1)

### Performance
- NER worker concurrency bump to 8 (94ee88b)
- Jobs status indexes + reduced frontend polling intervals (b0bc073)
- Scale Celery to 3 worker replicas with concurrency 3 (b9a73fb, c172889)

### Removed
- Docker resource limits (except Neo4j heap cap) — let Docker use available host memory (6f4d033)

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
