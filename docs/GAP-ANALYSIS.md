# NEXUS Fullstack Feature Gap Analysis

Living document tracking features that don't work end-to-end despite all 17 milestones being marked complete. Updated as items are resolved.

---

## CRITICAL — UI Features That Were Broken E2E

### - [x] C1: Case Setup Wizard Never Triggers Case Setup Agent
- **Symptom**: User completes the 5-step wizard; nothing happens on the backend
- **Root cause**: `StepUpload` used the generic `UploadWidget` which calls `POST /ingest/presigned-upload` + `POST /ingest/process-uploaded` (normal ingestion). The backend case setup requires `POST /cases/{matter_id}/setup` (direct file upload -> creates `case_contexts` row -> dispatches `run_case_setup` Celery task). The frontend never called this endpoint.
- **Secondary**: `StepProcessing` polls `GET /cases/{matter_id}/context` — returned 404 because no case context record was created
- **Tertiary**: `enable_case_setup_agent` defaults to `False` in config
- **Fix applied**: Replaced `UploadWidget` with a dedicated file upload that POSTs directly to `/api/v1/cases/{matterId}/setup` as multipart form data. On success, passes `case_context_id` to parent. `StepProcessing` now handles 404 gracefully with retry and shows failed state.
- **Files changed**: `step-upload.tsx`, `step-processing.tsx`, `case-setup.tsx`

### - [x] C2: Case Setup PATCH Body Schema Mismatch -> 422 on Save
- **Symptom**: User edits claims/parties in wizard, clicks Confirm -> HTTP 422 error
- **Root cause**: Frontend sent `{ claims: ["plain text string", ...] }` but backend `CaseContextUpdateRequest` expects `{ claims: [{ claim_number: 1, claim_label: "Fraud", claim_text: "..." }] }`. `ClaimInput` requires `claim_number: int`, `claim_label: str`, `claim_text: str`. `PartyInput` requires `role: PartyRole` (StrEnum), not a freeform string.
- **Fix applied**: Updated `Claim` interface to include `claim_number`, `claim_label`, `claim_text` fields. Updated `StepClaims` to render label + text inputs per claim with auto-numbered claim_number. Updated `StepPartiesTerms` to use `<Select>` with the 5 `PartyRole` enum values instead of freeform text. Updated `saveMutation` body to construct proper `ClaimInput` and `PartyInput` objects. Mutation now also sends `status: "confirmed"`.
- **Files changed**: `case-setup.tsx`, `step-claims.tsx`, `step-parties-terms.tsx`, `step-confirm.tsx`

### - [x] C3: Document Detail Missing 13 Sentiment/Scoring/Bates Fields
- **Symptom**: Document detail page shows empty Sentiment Analysis card; Scoring card never appears; Bates numbers not shown
- **Root cause**: Backend `DocumentDetail` schema did not declare sentiment, scoring, or bates fields. `_row_to_detail()` mapper never mapped these columns. The SQL query fetches them (columns exist via migration 009) but they were discarded. Frontend `DocumentDetail` type declares all 13 fields and `MetadataPanel` renders them.
- **Fix applied**: Added 12 fields to `DocumentDetail` schema (7 sentiment, `context_gap_score`, `context_gaps`, `anomaly_score`, `bates_begin`, `bates_end`). Added `hot_doc_score` mapping to `_row_to_detail()` (was on parent `DocumentResponse` but never passed through in detail mapper). Added all 12 new field mappings. Added test `test_get_document_includes_sentiment_scoring_bates`.
- **Files changed**: `app/documents/schemas.py`, `app/documents/router.py`, `tests/test_documents/test_router.py`

---

## HIGH — Backend Modules With No Frontend

### - [ ] H1: Exports Module — 11 Endpoints, No Frontend Page
- **Backend**: Complete production set CRUD, Bates numbering, export job lifecycle (create -> Celery task -> downloadable ZIP), privilege log preview
- **Frontend**: Result-set page says "export to CSV" but only has client-side blob creation — no integration with backend exports module
- **Files**: `app/exports/` (router, service, schemas, tasks, generators)
- **Fix**: Build `/exports` or `/review/exports` page; wire result-set export to backend

### - [ ] H2: EDRM Module — 4 Endpoints, No Frontend Page
- **Backend**: Load file import (DAT/OPT/EDRM XML), EDRM XML export, email thread listing, duplicate cluster listing
- **Files**: `app/edrm/` (router, service, schemas)
- **Fix**: Could integrate threads into analytics/comms page; duplicates into result-set

### - [ ] H3: Redaction Module — 3 Endpoints, No Frontend Page
- **Backend**: PII auto-detection, apply redactions (pikepdf), redaction audit log
- **Note**: `enable_redaction` flag exists but redaction router has NO feature guard — endpoints always active
- **Files**: `app/redaction/` (router, service, schemas, pii_detector, engine)
- **Fix**: Build redaction UI in document detail page; add feature flag guard to router

### - [ ] H4: Graph Exploration — 4 Endpoints Not Wired to Frontend
- **Endpoints**: `GET /graph/explore` (Cypher query), `GET /graph/reporting-chain/{person}`, `GET /graph/path`, `GET /graph/communication-pairs`
- **Frontend**: Entity network page uses `/entities` and `/entities/{id}/connections` but none of the graph-specific endpoints
- **Files**: `app/entities/router.py:85-191`
- **Fix**: Wire path/reporting-chain into entity detail; communication-pairs into comms page

---

## MEDIUM — Config, Contract, and Error Handling Issues

### - [ ] M1: Hot Docs Page Works but Always Empty (Feature Flag OFF)
- `enable_hot_doc_detection=False` -> Hot Doc Scanner agent never runs -> `hot_doc_score` always NULL -> `/review/hot-docs` shows 0 results
- The page code itself is correct; the data pipeline isn't running
- **Fix**: Document required flags; consider UI indicator when feature is disabled

### - [ ] M2: Tool DB Session Management — Connection Leak Risk
- 5 tools (`case_context`, `sentiment_search`, `hot_doc_search`, `context_gap_search`, `communication_matrix`) manually manage async DB sessions with `await db_gen.__anext__()` / `aclose()` pattern
- `finally` blocks have bare `except Exception: pass` that silently swallow cleanup errors
- **Files**: `app/query/tools.py:218-466`
- **Fix**: Refactor to use `contextlib.asynccontextmanager` or inject session via state

### - [ ] M3: Case Context Injection Works, but Agent Dispatch Gated by Flag
- `case_context_resolve` node (`app/query/nodes.py:509-568`) DOES always load context regardless of flags — this is correct
- However, `enable_case_setup_agent=False` means the Celery task (`run_case_setup`) is never dispatched, so no context is ever auto-extracted
- Combined with C1 (now fixed — wizard calls `/setup`), context will only exist if manually created via PATCH when the flag is off
- **Impact**: Lower than initially assessed — context injection works if context exists; the problem is that context is never created automatically when the flag is off

### - [ ] M4: orval Generated API Directory Empty
- `frontend/src/api/generated/` is empty — all API calls use manual `apiClient()` wrappers
- Frontend types in `frontend/src/types/index.ts` are hand-maintained (341 lines)
- Type drift between backend schemas and frontend types is undetected (C3 was a direct consequence)
- **Fix**: Run `npm run generate-api` against running backend; evaluate switching to generated hooks

### - [ ] M5: 8 Feature Flags Default OFF — Silently Degrade UI

| Flag | Impact |
|---|---|
| `enable_hot_doc_detection` | Hot docs page always empty; scoring cards never appear |
| `enable_case_setup_agent` | Case setup agent task not dispatched; case context not auto-extracted |
| `enable_topic_clustering` | `topic_cluster` tool returns info message |
| `enable_graph_centrality` | `network_analysis` tool disabled; `/analytics/network-centrality` returns 501 |
| `enable_sparse_embeddings` | Hybrid search degrades to dense-only |
| `enable_near_duplicate_detection` | Duplicate columns always NULL |
| `enable_reranker` | No cross-encoder reranking |
| `enable_redaction` | Declared but not checked by router |

### - [x] M6: Uncommitted Work In Progress
- Previously uncommitted changes to prompts, tools, stream hook, and tests
- **Status**: Already committed in prior session (commit `3572ab5`)

---

## LOW — Tests and Cleanup

### - [ ] L1: No E2E test for case setup wizard flow
### - [ ] L2: No test for useStreamQuery unmount cleanup
### - [ ] L3: No frontend tests for exports/redaction/EDRM pages (pages don't exist yet)
### - [ ] L4: Tool error handling pattern inconsistently applied
- 5 of 12 tools have try/catch; rest have only session management try/finally

---

## Resolution Log

| Item | Status | Commit | Date |
|------|--------|--------|------|
| C1 | Fixed | (this commit) | 2026-03-07 |
| C2 | Fixed | (this commit) | 2026-03-07 |
| C3 | Fixed | (this commit) | 2026-03-07 |
| M6 | Fixed | `3572ab5` | prior session |
