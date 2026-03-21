# NEXUS Security, Agentic RAG & Enterprise Audit

**Date**: 2026-03-21
**Scope**: Full codebase audit across security, agentic RAG architecture, and enterprise readiness
**Status**: Report only — no code changes applied

---

## Executive Summary

This audit examines NEXUS — a multimodal RAG investigation platform for legal document intelligence — across three dimensions: **security**, **agentic RAG architecture**, and **enterprise readiness**. The platform handles 50,000+ pages of privileged legal documents, making security and data isolation critical.

The codebase demonstrates **strong foundational security** with well-designed patterns for privilege enforcement, parameterized queries, and structured audit logging. The agentic RAG pipeline is architecturally sophisticated with proper tool budgets, citation verification, and self-reflection. However, **3 critical**, **8 high-risk**, and **12 moderate** findings require attention.

**Finding Summary:**

| Severity | Count | Categories |
|----------|-------|------------|
| Critical | 3 | Privilege bypass, webhook auth, JWT default |
| High | 8 | Privilege gaps, prompt injection, error leakage, rate limiting |
| Moderate | 12 | Audit logging, tier classification, dead code, pool sizing |

---

## CRITICAL FINDINGS (Fix Immediately)

### CRIT-1: Neo4j Privilege Filter Logic Flaw

- **File**: `app/entities/graph_service.py:382-388`
- **Issue**: The privilege exclusion condition in `get_entity_connections()`:
  ```cypher
  (NOT connected:Document
   OR connected.privilege_status IS NULL
   OR NOT connected.privilege_status IN $excluded_statuses)
  ```
  This allows Entity nodes (which lack `privilege_status`) to leak privileged document connections. A non-admin user can enumerate privileged document metadata via entity graph traversal.
- **Impact**: Privilege information disclosure — non-admin users can discover document connections that should be filtered.
- **Fix**: Add deeper traversal check that filters out entity connections sourced exclusively from privileged documents, or explicitly check the label before applying privilege logic.
- **Test**: Verify non-admin cannot enumerate privileged doc content via entity neighbors.

### CRIT-2: Webhook Endpoint Accepts Unchecked matter_id

- **File**: `app/ingestion/router.py:482-535`
- **Issue**: The `ingest_webhook` endpoint takes `matter_id` from the JSON payload (`payload.matter_id`, line 508) without validating via the `get_matter_id` dependency or checking matter existence. A webhook sender could inject documents into any matter.
- **Impact**: Data integrity — unauthorized document injection into arbitrary matters.
- **Fix**: Add matter_id validation: either use `Depends(get_matter_id)` in the endpoint signature, or validate `payload.matter_id` against existing matters via `AuthService.check_matter_access()`.
- **Test**: Send webhook with arbitrary/nonexistent matter_id, verify rejection.

### CRIT-3: JWT Secret Key Default Is Insecure

- **File**: `app/config.py:444`
- **Issue**: `jwt_secret_key: str = "change-me-to-a-random-64-char-string"` — if `.env` doesn't override this default, production runs with a predictable secret enabling JWT token forgery.
- **Impact**: Authentication bypass — any attacker can forge JWT tokens.
- **Fix**: Add a `@model_validator` that rejects secrets containing "change-me" or shorter than 32 characters. Fail fast at boot.
- **Test**: Start app without JWT_SECRET_KEY set, verify startup failure with clear error.

---

## HIGH-RISK FINDINGS

### HIGH-1: Missing Privilege Filters on Graph Operations

- **File**: `app/entities/graph_service.py:422-445`
- **Issue**: `get_all_entities_by_type()` has `matter_id` filter but NO `exclude_privilege_statuses` parameter. Non-admin users could enumerate entity mentions originating from privileged documents.
- **Fix**: Add `exclude_privilege_statuses` parameter matching the pattern in `get_entity_connections()`.

### HIGH-2: Inconsistent Privilege Passing Across Agent Tools

- **File**: `app/query/tools.py` (17 tools)
- **Issue**: Not all tools consistently pass `exclude_privilege_statuses` from `state.get("_exclude_privilege")`. Confirmed working: `graph_query` (L204), `temporal_search` (L241), `sentiment_search`, `vector_search`. Need audit of: `entity_lookup`, `case_context`, `communication_matrix`, `network_analysis`, `cypher_query`, `get_community_context`.
- **Fix**: Systematic audit of each tool; add privilege forwarding where missing.

### HIGH-3: Dataset Document ID Filtering Not Privilege-Checked

- **File**: `app/query/router.py:143-146`
- **Issue**: `DatasetService.get_document_ids_for_dataset()` may not filter by `privilege_status`, allowing non-admin users to query privileged documents via `dataset_id`.
- **Fix**: Verify and add privilege filtering in DatasetService.

### HIGH-4: Prompt Injection via Case Context

- **Files**: `app/query/prompts.py:34, 51, 81, 139`
- **Issue**: Case context (claims, parties, defined terms from DB) is interpolated into prompts via `.format()`. While DB-sourced, adversarial document content could contain prompt injection payloads that alter agent behavior. Legal documents may contain terms that resemble prompt instructions.
- **Fix**: Sanitize case context values (escape curly braces, strip control characters) before prompt injection. Consider XML-tag wrapping for clear prompt/data boundaries.

### HIGH-5: Exception Detail Leakage in Routers

- **Files**: `app/annotations/router.py:56,109`, and other routers
- **Issue**: Exception strings (`detail=str(exc)`) may contain internal implementation details, file paths, or SQL fragments. Violates the principle of not leaking document content in errors.
- **Fix**: Replace `detail=str(exc)` with generic error messages; log the actual exception server-side at `error` level.

### HIGH-6: Citation Verification Anchoring Bias

- **File**: `app/query/nodes.py` (verify_citations, `_verify_single_claim`)
- **Issue**: The verification prompt (`VERIFY_JUDGMENT_PROMPT`) shows the originally-cited source alongside independent retrieval evidence. The LLM may anchor to the original citation rather than truly judging independence. If the same chunk appears in the independent top-5 results (likely given semantic similarity), verification becomes circular.
- **Fix**: Either exclude the originally-cited chunk from independent retrieval results, or omit the original citation from the judgment prompt.

### HIGH-7: Empty Response Cascades Silently

- **File**: `app/query/nodes.py` (post_agent_extract)
- **Issue**: If the agent produces no content in messages, `response=""` propagates silently through the pipeline. Downstream nodes see empty string; user receives an empty response with no indication of failure.
- **Fix**: Add explicit check for empty response, log warning, set a fallback message like "I was unable to generate a response for this query. Please try rephrasing."

### HIGH-8: Rate Limiting Fails Open

- **File**: `app/common/rate_limit.py:73-75`
- **Issue**: If Redis is unavailable, all rate limiting is silently disabled (`except Exception: logger.warning(...)`). In production, this removes DoS protection entirely.
- **Fix**: Add configurable `RATE_LIMIT_FAIL_CLOSED` setting. When enabled (production), return HTTP 503 if Redis is down rather than allowing unlimited requests.

---

## MODERATE FINDINGS

### MOD-1: Audit Logging Gaps

- **File**: `app/common/middleware.py:121-178`
- **Issue**: No query payloads or response sizes logged. Fire-and-forget design means audit inserts can silently fail with only a warning log.
- **Recommendation**: Log sanitized query text and result count for legal compliance.

### MOD-2: Tier Classification Edge Cases

- **File**: `app/query/nodes.py` (case_context_resolve)
- **Issue**: Tier classification uses simple word count + keyword matching. A 21-word analytical query may misclassify as "standard" instead of "deep". Fast tier skips citation verification unconditionally — risky if user asks nuanced question in few words.
- **Recommendation**: Consider LLM-based tier classification for ambiguous queries, or allow user override.

### MOD-3: CORS Wildcard Not Prevented

- **File**: `app/config.py:448`
- **Issue**: No validation prevents `CORS_ALLOWED_ORIGINS="*"` in production.
- **Recommendation**: Add model validator rejecting wildcard when `LOG_LEVEL != DEBUG`.

### MOD-4: Feature Flag Cascade Visibility

- **File**: `app/feature_flags/service.py:86-100`
- **Issue**: Enabling a flag auto-enables prerequisites (depends_on chain). No preview of cascading changes before the toggle commits.
- **Recommendation**: Add `POST /admin/feature-flags/{flag}/preview-cascade` endpoint.

### MOD-5: Celery Workers Don't See Mid-Flight Flag Toggles

- **File**: documented in `docs/feature-flags.md`
- **Issue**: Workers load DB overrides at startup only. Flags toggled mid-job won't take effect until worker restart. Risk: inconsistent chunk processing within a job.
- **Recommendation**: Add periodic sync task (every 5min) or document clearly as a known limitation.

### MOD-6: No DI Factory Error Handling

- **File**: `app/dependencies.py:57-66`
- **Issue**: If PostgreSQL/Redis/Qdrant/Neo4j unavailable at startup, factories raise immediately with no retry or graceful degradation.
- **Recommendation**: Add retry with backoff on initial connection for critical services.

### MOD-7: Database Pool Size Not Configurable

- **File**: `app/dependencies.py:60-65`
- **Issue**: `pool_size=5, max_overflow=10` hardcoded. For 50k+ page corpus under load, may be insufficient.
- **Recommendation**: Make configurable via `DB_POOL_SIZE` and `DB_MAX_OVERFLOW` env vars.

### MOD-8: Neo4j Password Default

- **File**: `app/config.py:197`
- **Issue**: Default `"changeme"`. Similar to CRIT-3 but lower risk (Neo4j typically not exposed externally).
- **Recommendation**: Add startup warning when default password detected.

### MOD-9: SQL Logging Truncation

- **File**: `app/query/sql_generator.py:83`
- **Issue**: `sql=result.sql[:200]` logged — may truncate important parts of the generated SQL.
- **Recommendation**: Log full SQL at DEBUG level, keep truncated version at INFO.

### MOD-10: MinIO Credentials in Stack Traces

- **Issue**: If MinIO connection fails, stack trace may include endpoint and access key in structured logs.
- **Recommendation**: Apply `redact_error_message()` wrapper to storage/DB errors.

### MOD-11: Text-to-SQL "Last Resort" Parsing

- **File**: `app/query/sql_generator.py:170-171`
- **Issue**: If LLM response isn't valid JSON, the entire raw response is treated as SQL: `SQLQuery(sql=raw.strip())`. While `validate_sql_safety()` catches write operations and forbidden tables, a complex read query could exfiltrate data from allowed tables beyond the user's intent.
- **Recommendation**: Reject raw responses that don't match expected JSON format rather than treating them as SQL.

### MOD-12: HalluGraph Node Unreachable

- **File**: `app/query/graph.py:372`
- **Issue**: `hallugraph_check` node is added to the parent graph (`parent.add_node("hallugraph_check", hallugraph_check)`) but has no incoming or outgoing edges — it's unreachable dead code.
- **Recommendation**: Either wire it into the graph flow (e.g., after `verify_citations`) or remove it.

---

## ARCHITECTURE STRENGTHS

### Security

| Area | Assessment | Details |
|------|-----------|---------|
| SQL Injection | **Safe** | All queries use `sqlalchemy.text()` with `:param` binding. No string interpolation found. |
| Neo4j Injection | **Safe** | All Cypher queries use `$params` parameterization. |
| Qdrant Injection | **Safe** | Uses typed `FieldCondition()` API, not string interpolation. |
| Agent Tool Security | **Strong** | `InjectedState` prevents LLM from controlling `matter_id` or privilege filters. |
| Audit Logging | **Comprehensive** | API-level + AI-level audit logging with request correlation. |
| Password Handling | **Proper** | bcrypt for passwords, SHA-256 for API keys. |
| CORS | **Configured** | Whitelist approach from environment variables. |

### Agentic RAG Pipeline

| Feature | Assessment | Details |
|---------|-----------|---------|
| Iteration Control | **Double-locked** | `RemainingStepsManager` + audit hook tool budget prevents runaway agents. |
| Citation Verification | **3-stage CoVe** | Decompose claims → independent retrieval → LLM judgment. |
| Self-Reflection | **Bounded** | Conditional retry when faithfulness < threshold, max retries enforced. |
| Tier Classification | **Heuristic** | Fast/standard/deep with per-tier tool budgets and LLM configs. |
| Retrieval Quality | **Multi-layered** | CRAG grading (heuristic + LLM), reranking, HyDE, multi-representation indexing. |
| Tool Architecture | **17 specialized tools** | Vector search, graph query, temporal, SQL, Cypher, sentiment, topics, network analysis. |
| Context Management | **Proper** | PostgresCheckpointer for persistence, case context injection, term map substitution. |
| Streaming | **Well-implemented** | Sources sent before generation via SSE, token-by-token streaming. |

### Enterprise Features

| Feature | Assessment | Details |
|---------|-----------|---------|
| Feature Flags | **Mature** | 42 flags, runtime toggle, risk gating, dependency cascading, DI cache clearing. |
| DI Framework | **Proper** | 23+ factories, `@functools.cache` singletons, proper lifecycle management. |
| Testing | **Comprehensive** | ~1528 backend tests, 181 test files, 4-shard parallel CI. |
| Configuration | **Well-structured** | 150+ typed settings via Pydantic Settings, nested config groups. |
| Monitoring | **Multi-layer** | Structured logging, health endpoints, quality monitoring, LangSmith integration. |
| Data Isolation | **Multi-store** | Matter-scoped at SQL, Qdrant, and Neo4j layers consistently. |

---

## PRIORITY MATRIX

```
                    High Impact
                        │
    CRIT-1 ─────────────┼──────────── CRIT-2
    (privilege bypass)  │            (webhook auth)
                        │
    HIGH-2 ─────────────┼──────────── CRIT-3
    (tool privilege)    │            (JWT default)
                        │
    HIGH-4 ─────────────┼──────────── HIGH-8
    (prompt injection)  │            (rate limit)
                        │
    HIGH-6 ─────────────┼──────────── HIGH-5
    (citation bias)     │            (error leakage)
                        │
    MOD-11 ─────────────┼──────────── MOD-1
    (SQL parsing)       │            (audit gaps)
                        │
    MOD-12 ─────────────┼──────────── MOD-7
    (dead code)         │            (pool sizing)
                        │
                    Low Impact
    Easy to Fix ────────┴──────────── Hard to Fix
```

---

## RECOMMENDED FIX ORDER

### Phase 1: Critical Security (Est. scope: 3 files)
1. Fix Neo4j privilege filter logic (`graph_service.py`)
2. Secure webhook endpoint (`ingestion/router.py`)
3. Enforce JWT secret at startup (`config.py`)

### Phase 2: High-Risk (Est. scope: 5 files)
4. Audit/fix privilege passing in all agent tools (`tools.py`)
5. Fix exception detail leakage (multiple routers)
6. Fix citation verification anchoring bias (`nodes.py`)
7. Handle empty response gracefully (`nodes.py`)
8. Make rate limiting configurable (`rate_limit.py`)

### Phase 3: Moderate (Est. scope: 8 files)
9. Enhance audit logging
10. Prevent CORS wildcard in production
11. Add feature flag cascade preview
12. Remove or wire `hallugraph_check` node
13. Make pool sizes configurable
14. Harden text-to-SQL fallback parsing
15. Remaining moderate findings

---

## VERIFICATION CHECKLIST

- [ ] Non-admin user cannot see privileged document connections via entity graph
- [ ] Webhook rejects requests with unauthorized matter_id
- [ ] App fails to start with default JWT secret
- [ ] All 17 agent tools pass privilege filters consistently
- [ ] No `detail=str(exc)` patterns in router exception handlers
- [ ] Citation verification uses independent evidence (not original citation)
- [ ] Empty agent responses produce user-visible fallback message
- [ ] Rate limiter returns 503 when Redis down and fail-closed enabled
- [ ] Full test suite passes (4-agent parallel run)
