# NEXUS Platform Maturity Audit — Agentic RAG for Law Firms

**Date**: 2026-03-08
**Scope**: Full codebase audit assessing production readiness as a legal AI investigation platform
**Evaluator**: Automated deep audit of architecture, code, tests, and documentation

---

## Executive Summary

**Overall Rating: 8.2 / 10 — Production-Capable, Strong Foundation**

NEXUS is one of the most architecturally complete legal RAG platforms available. It goes well beyond a prototype — the agentic pipeline, citation verification, knowledge graph, and security model are genuinely sophisticated. The main gaps are in UX polish and operational hardening, not in core intelligence.

For a law firm looking for intelligent document investigation with cited answers and case building capabilities, NEXUS is production-capable today for small-to-medium matters. For large-scale litigation (millions of pages, hundreds of concurrent users), it needs load testing and operational hardening.

---

## Dimension Ratings

### 1. Query Intelligence (Agentic RAG Pipeline) — 9/10

This is where NEXUS excels and differentiates.

**Strengths:**
- **True agentic loop** via `create_react_agent` with 12 domain-specific tools (`app/query/graph.py`). The agent autonomously decides which tools to call and iterates — this is not a fixed retrieve-then-generate chain.
- **12 specialized tools** (`app/query/tools.py`): vector search, graph query, temporal search, entity lookup, document retrieval, case context, sentiment search, hot doc search, context gaps, communication matrix, topic clustering, network analysis. This toolset covers the investigative workflows lawyers actually do.
- **Citation verification (CoVe)** (`app/query/nodes.py`): Independent chain-of-verification decomposes the response into claims, re-retrieves evidence for each, and judges grounding. This is critical for legal — lawyers need to trust citations.
- **Query tier classification** (fast/standard/deep) with adaptive recursion limits (16/28/50). Simple lookups resolve quickly; complex investigations get more tool iterations.
- **Case context injection** — claims, parties, defined terms, and timeline from the Case Setup Agent are auto-injected into every query, improving alias resolution and relevance.
- **InjectedState security** — `matter_id` and privilege filters are injected from graph state, never exposed to the LLM. This is the correct pattern.

**Minor gaps:**
- No multi-turn conversation memory beyond the current thread (no long-term user preference learning)
- Query expansion is mentioned in architecture but unclear if fully wired in the agentic path
- Follow-up questions are generated but not deeply personalized to the case theory

---

### 2. Retrieval Quality — 8.5/10

**Strengths:**
- **Hybrid dense+sparse search** with Qdrant's native RRF fusion (`app/query/retriever.py`). Server-side fusion, which is faster and more correct than Python-side.
- **Cross-encoder reranking** with BGE-reranker-v2-m3 (`app/query/reranker.py`), feature-flagged
- **Visual reranking** with ColQwen2.5 for PDF-heavy corpora — blend text and visual scores
- **Graph-augmented retrieval** — Neo4j multi-hop traversal runs in parallel with vector search (`retrieve_all` method)
- **Semantic chunking** respecting document structure (paragraphs, tables, email body/quote splits) via Docling — not naive fixed-size windows
- **Query-time NER** with GLiNER to extract entities from the query for graph lookup

**Gaps:**
- No explicit query decomposition for complex multi-part questions (the agent handles this implicitly through tool iteration, but a dedicated decomposition step could help)
- Parent-child chunk retrieval (retrieve small chunk, expand to parent context) is not implemented — this is a common pattern in advanced RAG

---

### 3. Document Processing & Ingestion — 8.5/10

**Strengths:**
- **10+ file formats**: PDF, DOCX, XLSX, PPTX, HTML, EML, MSG, RTF, CSV, TXT, ZIP via Docling + stdlib parsers
- **6-stage Celery pipeline** with retry, progress tracking, and job cancellation: Parse → Chunk → Embed → NER → Resolve → Index
- **Multiple entry paths**: direct upload, MinIO webhook, EDRM load file import (DAT/OPT/CSV), bulk import for pre-OCR'd datasets
- **Entity resolution** with rapidfuzz + embedding cosine + union-find transitive closure — handles "John Smith" / "J. Smith" / "Smith, John" correctly
- **Hot doc scoring** with 7 sentiment dimensions + 3 hot-doc signals
- **Near-duplicate detection** and **email threading**
- **Visual embeddings** with ColQwen2.5 for image-heavy PDFs

**Gaps:**
- No dedicated OCR pipeline for scanned PDFs (relies on Docling's built-in OCR which may not handle poor-quality scans well)
- No table extraction → structured data pipeline (tables are preserved in chunks but not queryable as structured data)

---

### 4. Knowledge Graph & Entity Intelligence — 8/10

**Strengths:**
- **Neo4j with 4 node types** (Entity, Document, Event, Claim) and 7 edge types
- **Multi-hop traversal**, path-finding, temporal queries, co-occurrence analysis
- **Entity resolution** with transitive closure — crucial for legal where the same person appears under many names
- **Org hierarchy inference** from communication patterns (`REPORTS_TO` edges)
- **Centrality metrics** (degree, PageRank, betweenness) via Neo4j GDS
- **Case terms linked to graph entities** via `ALIAS_OF` edges

**Gaps:**
- No interactive graph editing by users (lawyers can't manually merge entities or add relationships)
- No "investigation workspace" where lawyers can pin entities/documents and see connections evolve

---

### 5. Case Building & Litigation Workflow — 7.5/10

**Strengths:**
- **Case Setup Agent** extracts claims, parties, defined terms, and timeline from an anchor complaint document
- **Annotations** — notes, highlights, tags, issue codes on documents
- **Production sets** with Bates numbering and export (HTML/PDF/JSON + load files)
- **EDRM interop** — import/export of standard load file formats
- **PII detection** via GLiNER + manual/automatic **redaction** with audit trail
- **Privilege tagging** with 5 statuses, enforced at the data layer

**Gaps:**
- No **privilege log generator** — lawyers need to produce privilege logs for court
- No **deposition prep** workflow (pull all docs mentioning a witness, suggest questions)
- No **brief/memo drafting** assistance (generate a summary memo for a specific legal issue with citations)
- No **document comparison** (redline two versions of a contract)
- Case Setup is triggered manually — could auto-detect anchor docs on ingestion

---

### 6. Security & Compliance — 9/10

**Strengths:**
- **Triple-layer privilege enforcement**: Qdrant payload filter + SQL WHERE + Neo4j Cypher — data-layer, not API-layer
- **4-role RBAC** (admin, attorney, paralegal, reviewer) with matter-scoped access
- **JWT auth** with refresh tokens, API key alternative
- **Triple audit logging**: API calls (`audit_log`), LLM calls (`ai_audit_log`), agent tool calls (`agent_audit_log`) — all immutable
- **No document content in logs** — only IDs and metadata
- **CORS restricted**, rate limiting on public endpoints
- **Matter-scoped everything** — `X-Matter-ID` header required on all data endpoints

**Gaps:**
- No SSO/SAML integration (most law firms use Okta/Azure AD)
- No data retention policies / automated purge
- No audit log export (for compliance reporting)

---

### 7. Frontend & UX — 7/10

**Strengths:**
- **Modern stack**: React 19 + TanStack Router + TanStack Query + shadcn/ui + Zustand
- **Type-safe API integration** via orval (OpenAPI → TanStack Query hooks)
- **Rich component set**: chat interface with citation markers/preview/sidebar, entity graph visualization (network-graph, connections-graph, path-finder), document viewer (PDF, text, email, image), analytics (communication matrix, timeline, hot doc table), case setup, document review with annotations
- **35 frontend tests** (Vitest + RTL)
- **SSE streaming** for query responses

**Gaps:**
- **35 frontend tests is thin** for this component count — needs significantly more coverage
- No evidence of **mobile responsiveness** or **accessibility** (WCAG compliance)
- No **onboarding flow** for new users
- No **keyboard shortcuts** for power users (document reviewers live on keyboards)
- No **highlighted passage linking** from citations back to source document pages
- No **dark mode** (law firms often review documents late at night)

---

### 8. Testing & Quality — 8/10

**Strengths:**
- **512 backend tests** across 22 test directories mirroring the module structure
- **130 test files** covering every domain module
- **Comprehensive conftest.py** with mock services, AsyncClient, patched lifespan
- **Evaluation framework** (`app/evaluation/`) with ground-truth Q&A datasets, retrieval metrics (MRR/Recall/NDCG), faithfulness scoring, citation accuracy
- **CI/CD workflows** for backend tests, frontend tests, and evaluation

**Gaps:**
- No load/stress testing evidence (critical at 50K+ page scale)
- No chaos testing for infrastructure failures
- E2E tests exist (`tests/test_e2e/`) but unclear how comprehensive

---

### 9. Deployment & Operations — 8/10

**Strengths:**
- **4 Docker Compose variants**: dev, prod, cloud (Caddy + TLS), local LLM (vLLM/Ollama + TEI)
- **Zero cloud dependency option** — can run entirely local with Ollama/vLLM
- **Multi-provider LLM/embedding abstraction** — switch providers via env vars
- **16 feature flags** for progressive capability rollout
- **Health checks** including deep checks (LLM + embedding connectivity)
- **Alembic migrations** for schema management (13 migrations)
- **GCP + Vercel deployment guide**

**Gaps:**
- No Kubernetes manifests or Helm charts
- No observability stack (Prometheus metrics, Grafana dashboards)
- No backup/restore procedures documented

---

### 10. Architecture & Code Quality — 9/10

**Strengths:**
- **Clean module structure**: 16 domain modules, each with router/service/schemas separation
- **Library-first philosophy** — Docling, GLiNER, Instructor, LangGraph, Qdrant native — minimal custom code
- **20 DI factories** with singleton caching
- **Type-safe throughout** — Pydantic v2 schemas, typed function signatures
- **Raw SQL with named parameters** — known queries, full control, no ORM overhead
- **Structured logging** with structlog + contextvars
- **Prompt centralization** — all prompts in `prompts.py` files (auditable, tunable)
- **Excellent documentation** — ARCHITECTURE.md, CLAUDE.md, ROADMAP.md, modules.md, agents.md, feature-flags.md

The codebase reads like it was built by someone who understands both the legal domain and modern AI engineering.

---

## Competitive Positioning

| Capability | NEXUS | Typical Legal AI Startup | Enterprise (Relativity/Everlaw) |
|---|---|---|---|
| Agentic RAG (multi-tool) | 12-tool agentic loop | Basic retrieve+generate | No |
| Citation verification | CoVe pipeline | Rare | No |
| Knowledge graph | Neo4j multi-hop | Rare | Limited |
| Case intelligence injection | Auto-injected | No | No |
| Hybrid search (dense+sparse+graph) | Native RRF + graph | Dense only | Keyword + some semantic |
| Visual document understanding | ColQwen2.5 | No | OCR only |
| Privilege enforcement at data layer | Triple-layer | API-layer only | Yes |
| EDRM interop | Import + export | No | Yes |
| Production sets + Bates numbering | Yes | No | Yes |
| Fully local deployment | Yes | Cloud only | On-prem option |
| Audit trail (API + AI + Agent) | Triple audit logging | Partial | Yes |

NEXUS is significantly more intelligent than most legal AI startups (which are basic RAG) and has litigation support features that approach enterprise eDiscovery platforms. The main gap vs. enterprise is operational scale and UX maturity.

---

## Priority Improvements for Law Firm Readiness

### P0 — High Priority (do these first)

1. **SSO/SAML integration** — most firms will not adopt without it. Okta and Azure AD are the most common.
2. **Privilege log generation** — required for any privilege review workflow; courts mandate privilege logs.
3. **Load testing at scale** — prove the platform works at 50K+ pages with concurrent users. Use Locust or k6.
4. **Frontend test coverage** — 35 tests is too thin for production confidence. Target 150+ covering all major flows.

### P1 — Medium Priority

5. **Brief/memo drafting** from query results — high-value lawyer workflow. Generate a cited summary memo for a specific legal issue.
6. **Keyboard shortcuts** for document review — reviewers process thousands of documents; keyboard navigation is essential.
7. **Highlighted passage linking** — click a citation in the chat response, jump to the highlighted passage in the source document viewer.
8. **Observability stack** — Prometheus metrics, Grafana dashboards, alerting on error rates and latency.

### P2 — Nice to Have

9. **Dark mode** — quality-of-life for late-night document review.
10. **Mobile responsive design** — partners checking case status from phones.
11. **Deposition prep workflow** — pull all docs mentioning a witness, suggest examination questions.
12. **Document comparison/redline** — compare two versions of a contract or agreement.
13. **Interactive graph editing** — let lawyers manually merge entities, add relationships, correct errors.
14. **Audit log export** — CSV/JSON export for compliance reporting.

---

## Technical Debt Assessment

**Low technical debt overall.** The codebase follows consistent patterns, has comprehensive type safety, and avoids premature abstractions. Notable observations:

- **No ORM** — intentional choice for full SQL control. Correct for this use case but means no automatic schema validation at the query layer.
- **Prompt centralization** — all prompts in `prompts.py` files, which is excellent for legal auditability and tuning.
- **Feature flags** — 16 flags allow progressive rollout without code changes. Well-implemented.
- **DI pattern** — 20 cached factory functions in `dependencies.py`. Clean but could become unwieldy if more services are added.
- **No silent fallbacks** — errors propagate loudly, which is the right choice for legal where silent data loss is unacceptable.

---

## Verdict

NEXUS has the intelligence layer that matters most for legal AI: an agentic pipeline that reasons over documents, verifies its own citations, and understands case context. The 12-tool investigation agent, citation verification, and knowledge graph integration put it ahead of most legal AI products on the market.

The platform is production-ready for small-to-medium matters today. The path to enterprise readiness requires SSO, load testing, and UX hardening — all achievable without architectural changes.

**Rating: 8.2/10** — Strong foundation with a clear path to 9+.
