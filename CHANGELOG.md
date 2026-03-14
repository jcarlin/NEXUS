# Changelog

All notable changes to NEXUS are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/). Versioning follows [Semantic Versioning](https://semver.org/) — see `CLAUDE.md` "Versioning & Releases" for the project-specific rules.

**How to update:** When tagging a new release, move items from `[Unreleased]` into a new version heading. Group entries under `Added`, `Changed`, `Fixed`, `Performance`, or `Removed`. Each entry is one line: `- Description (commit_hash)`.

---

## [Unreleased]

_Nothing yet._

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
