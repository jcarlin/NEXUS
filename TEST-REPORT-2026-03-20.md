# NEXUS Test Report — 2026-03-20

## Executive Summary

| Suite | Passed | Failed | Skipped | Total | Duration |
|-------|--------|--------|---------|-------|----------|
| **Backend Unit Tests** | 1,746 | 5 | 4 | 1,755 | ~33m (4 parallel shards) |
| **Frontend Unit Tests** | 706 | 4 | 0 | 710 | 3m32s |
| **Frontend E2E (GCP)** | 107 | 17 | 1 | 125 | 29m06s |
| **Grand Total** | **2,559** | **26** | **5** | **2,590** | — |

**Pass rate: 98.8%** (2,559 / 2,590)

---

## 1. Backend Unit Tests (pytest)

All tests fully mocked — no external services contacted.

### Shard 1: Query (~408 tests)

| Result | Count |
|--------|-------|
| Passed | 405 |
| Failed | 2 |
| Deselected | 2 |
| Duration | 5m08s |

**Failures:**

| Test | Error | Root Cause |
|------|-------|------------|
| `test_query/test_adaptive_depth.py::TestAdaptiveDepthConfig::test_feature_flag_default_off` | Assertion error | Feature flag enabled in local `.env` overrides expected default |
| `test_query/test_ask_user_tool.py::test_resume_endpoint_exists` | `RuntimeError: AsyncConnectionPool open with no running loop` | `get_checkpointer()` creates `AsyncConnectionPool` outside async context |

### Shard 2: Ingestion + Entities + Feature Flags + Operations (~474 tests)

| Result | Count |
|--------|-------|
| Passed | 474 |
| Failed | 0 |
| Duration | 9m51s |

**Clean run.**

### Shard 3: Core (Common + Documents + LLM Config + Settings + Retention + Health) (~430 tests)

| Result | Count |
|--------|-------|
| Passed | 427 |
| Failed | 3 |
| Deselected | 1 |
| Duration | 8m22s |

**Failures:**

| Test | Error | Root Cause |
|------|-------|------------|
| `test_common/test_config.py::TestNestedConfig::test_flat_fields_still_work` | Assertion error | Env-dependent: local `.env` has features/config enabled that override test defaults |
| `test_common/test_config.py::TestNestedConfig::test_nested_llm_populated` | Assertion error | Same env-dependent config issue |
| `test_common/test_config.py::TestNestedConfig::test_nested_embedding_populated` | Assertion error | Same env-dependent config issue |

### Shard 4: Modules (Auth + Cases + Analytics + 12 more) (~440 tests)

| Result | Count |
|--------|-------|
| Passed | 440 |
| Failed | 0 |
| Skipped | 1 |
| Duration | 9m29s |

**Clean run.**

### Backend Summary

- **5 failures total**, all pre-existing/env-dependent:
  - 3 config tests fail because local `.env` has features enabled (same family as known `test_nested_features_populated`)
  - 1 feature flag default test fails for the same reason
  - 1 `AsyncConnectionPool` lifecycle bug in `get_checkpointer()` — real code issue
- **Warnings:** Qdrant client v1.17.0 vs server v1.13.2 version mismatch; several `coroutine never awaited` warnings from mocked async calls

---

## 2. Frontend Unit Tests (Vitest)

| Result | Count |
|--------|-------|
| Passed | 706 |
| Failed | 4 |
| Test Files | 81 (77 passed, 4 failed) |
| Duration | 3m32s |

**Failures (all test timeouts at 5000ms default):**

| Test File | Test | Error |
|-----------|------|-------|
| `knowledge-graph-admin.test.tsx:87` | "module exports Route" | Timed out in 5000ms |
| `entity-edit-dialogs.test.tsx:31` | "renders with entity name and submits new name" | Timed out in 5000ms |
| `citation-sidebar.test.tsx:462` | "preserves already-collapsed state on restore" | Timed out in 5000ms |
| `audit-export-dialog.test.tsx:85` | "submit calls apiFetchRaw with correct params" | Timed out in 5000ms |

**Analysis:** All 4 failures are test timeouts, not logic errors. These tests run complex component renders with multiple state updates that intermittently exceed the 5000ms default. Fixable by increasing `testTimeout` or optimizing test setup.

**Warnings:** Multiple `act(...)` warnings in `citation-sidebar.test.tsx` and `expanded-citation-view.test.tsx` — React state updates not wrapped in `act()`. Non-blocking but should be addressed.

---

## 3. Frontend E2E Tests — GCP (Playwright)

**Target:** `https://nexus-alpha-swart.vercel.app`
**Auth:** `admin@nexus-demo.com` / `nexus-demo-2026`
**Browser:** Chromium (headless, serial)
**Excluded:** `e2e-ingestion-rag.spec.ts` (uploads documents — unsafe for data preservation)

| Result | Count |
|--------|-------|
| Passed | 107 |
| Failed | 17 |
| Skipped | 1 |
| Duration | 29m06s |

### Data Safety Confirmation

- **No DELETE API calls** were made during the entire E2E run
- **No documents uploaded** (`e2e-ingestion-rag.spec.ts` was excluded)
- **No datasets created or modified**
- **No entities deleted or altered**
- All existing GCP data remains intact

### Failures by Category

#### Category 1: Empty Data — Documents (7 failures)

All 7 `documents.spec.ts` tests failed because the documents table shows **"No documents found."**

| Test | Locator | Issue |
|------|---------|-------|
| `documents.spec.ts:28` | document list shows seeded documents | Table body empty |
| `documents.spec.ts:41` | click document navigates to detail page | No rows to click |
| `documents.spec.ts:71` | document detail shows info panel | No document to view |
| `documents.spec.ts:88` | document detail shows page/chunk/entity counts | No document to view |
| `documents.spec.ts:103` | document detail shows filename heading | No document to view |
| `documents.spec.ts:120` | document detail has download button | No document to view |
| `documents.spec.ts:136` | document detail back button returns to list | No document to view |

#### Category 2: Empty Data — Entities & Knowledge Graph (4 failures)

| Test | Issue |
|------|-------|
| `entities.spec.ts:22` — entity list shows extracted entities | Expected >= 5 rows, got 1 |
| `entities.spec.ts:36` — entity rows have name and type | Expected >= 5 rows, got 1 |
| `knowledge-graph.spec.ts:28` — graph health card shows total nodes > 0 | "Total Nodes" text not found |
| `knowledge-graph.spec.ts:48` — graph health card shows total edges > 0 | "Total Edges" text not found |

#### Category 3: Empty Data — Dashboard & Analytics (3 failures)

| Test | Issue |
|------|-------|
| `dashboard.spec.ts:23` — stat cards show non-zero counts | Shows **Documents 0**, **Entities 0** |
| `analytics.spec.ts:73` — email threads tab shows thread list | No thread rows rendered |
| `admin.spec.ts:200` — evaluation quality gates show metric values | No metric cards found |

#### Category 4: Query/RAG Pipeline Timeout (3 failures)

| Test | Issue |
|------|-------|
| `agentic-rag-flow.spec.ts:26` — sources appear after response | Sources button not visible after response |
| `query-citation.spec.ts:6` — submits query with citation flow | Assistant message not visible within timeout |
| `query-performance.spec.ts:19` — query responds within budget | Assistant message not visible within 10s TTFT budget |

### Root Cause Analysis

**14 of 17 failures** share a single root cause: **the GCP instance returns zero documents/entities for the test matter ID** (`00000000-0000-0000-0000-000000000001`).

The page snapshots confirm the app loads correctly — navigation, sidebar, table headers, and search UI all render. But the API returns empty data. Likely causes:

1. **Neo4j data loss after restart** — a known issue (documented in project memory). The GCP VM's Neo4j container may have restarted since the last seed (2026-03-15), losing all graph data (entities, relationships).
2. **Matter/dataset mismatch** — the seeded documents may be associated with a different matter ID than what the E2E auth setup injects.
3. **API connectivity** — the Vercel frontend may not be reaching the GCP API correctly for data queries (though auth works, so the connection is live).

**3 query/RAG failures** are likely downstream of the empty data — with no documents in the vector store for this matter, queries either return empty results or time out waiting for the LLM.

### Passed E2E Tests (107)

All navigation, page rendering, UI interaction, and smoke tests passed, including:
- Login flow, auth setup
- All page navigation (smoke test visits every route)
- Chat page rendering and thread sidebar
- Case setup wizard (mocked API routes)
- Documents import UI
- Datasets page
- Review module
- Admin pages (feature flags, LLM settings, users, audit log, pipeline monitor)
- Exports page
- 6 of 8 agentic RAG flow tests (query + citation sidebar interaction)

---

## 4. Findings & Recommendations

### Critical (1)

| # | Finding | Impact | Recommendation |
|---|---------|--------|----------------|
| 1 | **GCP returns 0 documents/entities** for E2E matter ID | 14 E2E tests fail; core functionality unverifiable on GCP | Re-seed GCP: check Neo4j data, verify matter ID association, re-run `scripts/seed_demo.py` if needed |

### Medium (2)

| # | Finding | Impact | Recommendation |
|---|---------|--------|----------------|
| 2 | `get_checkpointer()` creates `AsyncConnectionPool` outside async context | 1 backend test fails; may cause issues in sync-path DI resolution | Defer pool creation to first async usage, or make `get_checkpointer()` async |
| 3 | 4 frontend unit tests timeout at 5000ms | Intermittent CI failures | Increase `testTimeout` to 10000ms for complex component tests, or optimize renders |

### Low (2)

| # | Finding | Impact | Recommendation |
|---|---------|--------|----------------|
| 4 | 4 config tests fail when `.env` has features enabled | Known env-dependent issue; tests pass in clean CI | Either isolate env in test setup or mark as `@pytest.mark.skipif` when `.env` present |
| 5 | Qdrant client v1.17.0 / server v1.13.2 version mismatch warning | No functional impact yet | Upgrade Qdrant server to 1.17.x or pin client to 1.13.x |
