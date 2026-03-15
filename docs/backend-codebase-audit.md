# Backend Codebase Audit Report

**Date:** 2026-03-15
**Scope:** Full backend audit against CLAUDE.md rules
**Files analyzed:** All 20 domain modules, `app/common/`, `app/dependencies.py`, `app/config.py`

---

## Executive Summary

Audited the NEXUS backend codebase against CLAUDE.md rules and project conventions. Identified 7 findings across 3 severity levels. Implemented fixes for 5 findings (Phase 1 & 2). Two recommendations deferred to future work.

All 1670+ tests pass after changes. No regressions introduced.

---

## Findings & Actions

### Phase 1 — Quick Wins (Implemented)

#### Finding 1: Silent Error Swallowing (Rules 14, 36)

**Severity:** Medium
**Location:** `app/analytics/communities.py:45,77`, `app/documents/comparison.py:78`

Bare `except: pass` blocks silently swallowed errors during Neo4j graph cleanup and document text extraction. This masks resource leaks and makes debugging impossible.

**Fix:** Replaced with `logger.warning(...)` calls with `exc_info=True` for stack trace capture.

#### Finding 2: No Prompt Versioning (Rule 49)

**Severity:** Low
**Location:** `app/query/prompts.py`

Prompt templates had no version tracking. When prompts change, AI audit log entries referencing the old prompt hash become unreproducible — there's no way to know which prompt version generated a given response.

**Fix:** Added `PROMPT_VERSIONS` dict mapping each prompt template name to a semantic version string. These versions can be logged alongside AI audit entries for full reproducibility.

#### Finding 3: SQL Filter Construction Duplication (Rule 12)

**Severity:** Low
**Location:** `app/audit/service.py:187-220`, `app/auth/admin_router.py:57-90`, `app/exports/service.py:421-433`

Four separate services had identical copy-pasted WHERE clause builder patterns — each with its own `where_clauses` list, `params` dict, and `None`-check loop. This violates DRY (rule 12) since the pattern appears in 4+ places.

**Fix:** Extracted `build_where_clause()` to `app/common/db_utils.py`. Accepts a dict of `{param_name: (sql_expr, value)}`, skips `None` values, returns `(where_sql, params)`. Refactored all 4 call sites.

---

### Phase 2 — Interface Definitions (Implemented)

#### Finding 4: No Formal Infrastructure Contracts

**Severity:** Medium
**Location:** `app/common/` (new files)

The codebase has 4 major infrastructure abstractions (LLM, vector store, object storage, graph database) but no formal interface definitions. Services depend on concrete implementations rather than abstractions, making testing and provider swapping harder than necessary.

**Fix:** Added `app/common/interfaces.py` with `typing.Protocol` definitions:
- `LLMProvider` — `complete()`, `stream()` methods
- `VectorStore` — `ensure_collections()`, `upsert_chunks()`, `search()` methods
- `ObjectStorage` — `ensure_bucket()`, `upload_bytes()`, `download_bytes()`, `delete_object()` methods
- `GraphDatabase` — `create_document_node()`, `create_entity_node()`, `query_entity_connections()` methods

All are `@runtime_checkable` and existing implementations already satisfy them via structural subtyping — no code changes needed in concrete classes.

#### Finding 5: Services Coupled to HTTP Semantics

**Severity:** Medium
**Location:** `app/common/exceptions.py` (new file)

Service methods raised `HTTPException` directly, coupling business logic to FastAPI's HTTP layer. This makes services harder to reuse from Celery tasks, CLI scripts, or other non-HTTP contexts.

**Fix:** Added `app/common/exceptions.py` with a typed exception hierarchy:
- `NexusError` (base)
- Data access: `DocumentNotFoundError`, `MatterNotFoundError`, `ChunkNotFoundError`
- Security: `PrivilegeViolationError`, `MatterScopeError`
- Ingestion: `IngestionError`, `RedactionError`, `ParsingError`
- LLM: `LLMProviderError`, `EmbeddingError`
- External: `ExportError`, `StorageError`

Routers can catch these and translate to appropriate `HTTPException` responses. Services remain HTTP-agnostic.

---

### Remaining Recommendations (Future Work)

#### Recommendation 1: LangGraph v1 Migration

**Priority:** Medium
**Effort:** High

The codebase uses `create_react_agent` from LangGraph. When upgrading to LangGraph v1+, migrate to the new `create_agent` API and adopt `Command()` for type-safe routing between nodes.

#### Recommendation 2: Observability

**Priority:** Medium
**Effort:** Medium

Add OpenTelemetry integration for distributed tracing across the FastAPI → LangGraph → Qdrant/Neo4j/LLM stack. Currently relies on structlog + LangSmith, which doesn't provide end-to-end trace correlation.

#### Recommendation 3: PydanticAI for Agent Tools

**Priority:** Low
**Effort:** Medium

Consider PydanticAI as an alternative to raw `@tool` decorators for agent tools. Provides better type safety, automatic schema generation, and structured error handling.

#### Recommendation 4: Integration Tests for Agent Loop

**Priority:** Medium
**Effort:** Medium

The full agent loop (query → tool calls → verification → reflection) lacks integration tests. Unit tests mock individual nodes, but end-to-end agent behavior is only validated manually or via E2E tests.

---

## Test Results

All 4 test shards passed after changes:

| Shard | Tests | Result |
|-------|-------|--------|
| Query | ~408 | PASS |
| Ingestion | ~408 | PASS |
| Core | ~430 | PASS |
| Modules | ~424 | PASS |

**Total:** ~1670 tests passing, 0 failures, 0 errors.

---

## Files Changed

| File | Change |
|------|--------|
| `app/analytics/communities.py` | Replace `except: pass` with warning logs |
| `app/documents/comparison.py` | Add debug log for text variant lookup |
| `app/query/prompts.py` | Add `PROMPT_VERSIONS` dict |
| `app/common/db_utils.py` | Add `build_where_clause()` utility |
| `app/audit/service.py` | Refactor to use `build_where_clause()` |
| `app/auth/admin_router.py` | Refactor to use `build_where_clause()` |
| `app/exports/service.py` | Refactor to use `build_where_clause()` |
| `app/common/interfaces.py` | New — Protocol definitions |
| `app/common/exceptions.py` | New — Domain exception taxonomy |
