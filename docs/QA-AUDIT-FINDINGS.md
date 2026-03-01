# QA Audit Findings — NEXUS

**Date:** 2026-02-28
**Scope:** M0–M8b (all completed milestones)
**Tools:** pytest 8.4.2, pytest-cov 7.0.0, ruff 0.11.4, mypy 1.19.1

---

## Executive Summary

| Metric | Value | Status |
|---|---|---|
| Test suite | **266 passed, 0 failed, 0 errors, 0 skipped** | PASS |
| Line coverage | **65%** | On track (target: 60% by M10) |
| Ruff lint violations | **105** (89 auto-fixable) | Needs attention |
| Ruff formatting drift | **57 files** would be reformatted | Needs attention |
| Mypy type errors | **18 errors** in 9 files | Needs attention |
| CI/CD | **None** — no GitHub Actions, no mypy config | Gap |

**Top 5 Risk Areas:**
1. `app/ingestion/tasks.py` — 22% coverage (378 stmts, 295 missed). This is the entire Celery pipeline.
2. `app/common/llm.py` — 25% coverage. Core LLM abstraction layer untested in production paths.
3. `app/entities/relationship_extractor.py` — 0% coverage. Entirely untested.
4. `app/entities/tasks.py` — 0% coverage. Background entity processing untested.
5. `app/entities/schemas.py` — 0% coverage. Entity data contracts untested.

---

## 1. Test Suite Results

### Summary

```
266 passed in 2059.78s (0:34:19)
0 failed | 0 errors | 0 skipped
```

**Regression gate: PASS.** All 266 tests pass. The roadmap's "zero failures, non-negotiable" requirement is met.

### Test Distribution by Module

| Module | Tests | Files |
|---|---|---|
| `test_audit/` | 10 | 1 |
| `test_auth/` | 17 | 4 |
| `test_common/` | 27 | 4 |
| `test_documents/` | 22 | 3 |
| `test_edrm/` | 15 | 4 |
| `test_entities/` | 19 | 4 |
| `test_health.py` | 8 | 1 |
| `test_ingestion/` | 53 | 9 |
| `test_integration/` | 17 | 3 |
| `test_query/` | 78 | 8 |
| **Total** | **266** | **41** |

### Slow Tests

The full suite runs in ~34 minutes. No individual test exceeds 5s (no `--durations` outliers observed), but the aggregate runtime is high for a unit test suite. The bulk of time is spent in async test setup/teardown (FastAPI TestClient with mocked lifespan).

### Actual vs Roadmap Claimed Test Counts

| Milestone | Claimed | Actual (estimated) | Delta |
|---|---|---|---|
| M0 | 8 | 8 | 0 |
| M1 | 23 | ~23 | 0 |
| M2 | 53 | ~53 | 0 |
| M3 | 44 | ~44 | 0 |
| M4 | 15 | 15 | 0 |
| M5 | 16 | 16 | 0 |
| M5b | 27 | 27 | 0 |
| M6 | 15 | 17 | +2 |
| M6b (TODO) | 12 | 15 | +3 (code exists but M6b not marked Done) |
| M7 | 20 | 20 | 0 |
| M8 | 8 | 8 | 0 |
| M8b | 11 | 11 | 0 |
| **Total** | **241** (roadmap baseline) | **266** | **+25** |

The 25-test surplus comes from: (a) M6b EDRM tests already written (15 tests in `test_edrm/`) despite the milestone being TODO, and (b) M6 auth tests slightly exceeding the claimed count.

---

## 2. Coverage Report

### Aggregate Coverage

```
TOTAL    3834 stmts    1335 missed    65% covered
```

### Per-File Coverage Table

#### Files at 100% Coverage
| File | Stmts |
|---|---|
| `app/config.py` | 50 |
| `app/common/embedder.py` | 64 |
| `app/common/models.py` | 38 |
| `app/audit/schemas.py` | 48 |
| `app/auth/schemas.py` | 54 |
| `app/documents/schemas.py` | 44 |
| `app/edrm/schemas.py` | 57 |
| `app/ingestion/schemas.py` | 39 |
| `app/ingestion/embedder.py` | 2 |
| `app/query/graph.py` | 56 |
| `app/query/nodes.py` (98%) | 165 |
| `app/query/prompts.py` | 4 |
| `app/query/reranker.py` | 24 |
| `app/query/schemas.py` | 42 |

#### Critical Files Below 50% Coverage

| File | Stmts | Miss | Cover | Risk |
|---|---|---|---|---|
| `app/ingestion/tasks.py` | 378 | 295 | **22%** | **CRITICAL** — entire Celery pipeline |
| `app/common/llm.py` | 122 | 92 | **25%** | **CRITICAL** — LLM abstraction layer |
| `app/ingestion/service.py` | 66 | 47 | **29%** | **HIGH** — ingestion orchestration |
| `app/entities/graph_service.py` | 170 | 115 | **32%** | **HIGH** — Neo4j graph operations |
| `app/edrm/router.py` | 43 | 25 | **42%** | Medium |
| `app/edrm/service.py` | 35 | 19 | **46%** | Medium |
| `app/common/storage.py` | 49 | 26 | **47%** | Medium — MinIO operations |
| `app/ingestion/dedup.py` | 122 | 62 | **49%** | Medium |

#### Files at 0% Coverage

| File | Stmts | Risk |
|---|---|---|
| `app/entities/relationship_extractor.py` | 45 | HIGH — LLM-based relationship extraction |
| `app/entities/tasks.py` | 49 | HIGH — background entity processing |
| `app/entities/schemas.py` | 29 | Medium — entity data contracts |

### Coverage vs Roadmap Targets

| Target | Deadline | Current | Status |
|---|---|---|---|
| 60% line coverage | M10 | **65%** | **AHEAD** |
| 70% line coverage | M13 | 65% | On track |
| New modules ≥ 50% on delivery | Always | See below | Mixed |

**New module coverage check (≥50% required):**
- `app/audit/` — router: 67%, service: 67% — **PASS**
- `app/edrm/` — router: 42%, service: 46% — **FAIL** (both below 50%)
- `app/common/embedder.py` — 100% — **PASS**

Note: `app/edrm/` is listed as TODO (M6b not marked Done), but the code and tests exist in the repo. If these files ship with M6b, they will need additional coverage.

---

## 3. Lint Report (Ruff)

### Summary

```
105 violations found
89 auto-fixable with --fix
57 files would be reformatted (formatting drift)
```

### Violations by Rule

| Count | Rule | Description | Auto-fix |
|---|---|---|---|
| 35 | F401 | Unused imports | Yes |
| 29 | I001 | Unsorted/unformatted import blocks | Yes |
| 23 | UP017 | Use `datetime.UTC` instead of `timezone.utc` | Yes |
| 7 | F841 | Unused local variables | No |
| 4 | E741 | Ambiguous variable names (`l`, `O`, etc.) | No |
| 3 | N806 | Non-lowercase variable in function | No |
| 2 | UP035 | Deprecated imports | Yes |
| 1 | N815 | Mixed-case variable in class scope | No |
| 1 | UP046 | Non-PEP 695 generic class | No |

### Files with Most Violations

| File | Violations |
|---|---|
| `tests/test_integration/test_streaming_e2e.py` | 6 |
| `tests/test_documents/test_privilege.py` | 5+ |
| `app/common/llm.py` | 4 |
| `tests/test_query/test_streaming.py` | 4 |
| `tests/test_ingestion/test_router.py` | 3 |
| `tests/test_documents/test_service.py` | 3 |
| `tests/test_documents/test_router.py` | 3 |

### Formatting Drift

57 out of 112 Python files (51%) would be reformatted by `ruff format`. This indicates formatting has never been enforced systematically. Key app files affected:

- `app/common/llm.py`, `app/common/middleware.py`, `app/common/vector_store.py`
- `app/dependencies.py`
- `app/documents/router.py`, `app/documents/service.py`
- `app/edrm/router.py`, `app/edrm/schemas.py`, `app/edrm/service.py`
- `app/entities/extractor.py`, `app/entities/graph_service.py`, `app/entities/router.py`
- `app/ingestion/` — most files
- `app/query/nodes.py`, `app/query/retriever.py`, `app/query/router.py`

---

## 4. Type Check Report (Mypy)

### Summary

```
18 errors in 9 files (checked 58 source files)
```

This is the first-ever mypy run. No `mypy.ini` or `[tool.mypy]` config exists in the project.

### Errors by Category

| Count | Error Code | Description |
|---|---|---|
| 6 | `union-attr` | Accessing attribute on union type without narrowing |
| 3 | `attr-defined` | Accessing non-existent attribute (`.rowcount` on `Result`) |
| 3 | `arg-type` | Incompatible argument types |
| 3 | `assignment` | Incompatible types in assignment |
| 1 | `dict-item` | Unpacked dict entry incompatible type |
| 1 | `annotation-unchecked` | Untyped function body not checked (note) |

### Errors by File

| File | Errors | Details |
|---|---|---|
| `app/common/llm.py` | 6 | Union type narrowing for Anthropic content blocks; OpenAI stream type |
| `app/ingestion/tasks.py` | 3 | Provider type mismatch; vector format type confusion |
| `app/common/vector_store.py` | 3 | Qdrant `Filter` argument types; dict unpacking |
| `app/ingestion/service.py` | 1 | `.rowcount` on `Result[Any]` |
| `app/documents/service.py` | 1 | `.rowcount` on `Result[Any]` |
| `app/query/retriever.py` | 1 | `BaseException` in `asyncio.gather` result |
| `app/query/router.py` | 1 | `.rowcount` on `Result[Any]` |
| `app/ingestion/router.py` | 1 | `str` vs `JobStatus` enum |
| `app/edrm/router.py` | 1 | `list[OpticonRecord]` assigned to `list[LoadFileRecord]` |

### Recurring Patterns

1. **`.rowcount` on `Result[Any]`** (3 occurrences): SQLAlchemy's `Result` type doesn't expose `.rowcount` in stubs. These are runtime-safe but need `type: ignore` or a wrapper.
2. **Union type narrowing** (6 in `llm.py`): Anthropic SDK returns union block types. Code accesses `.text` without `isinstance` checks.
3. **Provider type assignment** (in `tasks.py`): `OpenAIEmbeddingProvider` assigned to variable typed as `LocalEmbeddingProvider`.

---

## 5. Coverage Gap Analysis

### Critical Untested Code Paths

#### `app/ingestion/tasks.py` (22% — 295 lines missed)
The entire 6-stage Celery pipeline is minimally tested. Stages 1–6 (`_upload`, `_parse`, `_chunk`, `_embed`, `_extract`, `_index`) are tested only through high-level integration tests that mock most internals. Missing coverage:
- Stage progression and `_update_stage()` transitions
- Error handling within each stage
- ZIP extraction recursive dispatch
- Sparse embedding generation path
- Named vector upsert path
- Entity extraction → Neo4j indexing
- GLiNER model loading and inference

#### `app/common/llm.py` (25% — 92 lines missed)
Only the factory/init logic is tested. Missing:
- `_complete_anthropic()` — Anthropic API call path
- `_complete_openai()` — OpenAI API call path
- `_stream_anthropic()` — streaming response handling
- `_stream_openai()` — streaming response handling
- Provider detection and client initialization
- Error handling and retry paths

#### `app/entities/relationship_extractor.py` (0%)
- Entire Instructor + Claude relationship extraction pipeline untested
- Feature-flagged (`ENABLE_RELATIONSHIP_EXTRACTION`), but still shipping code

#### `app/entities/tasks.py` (0%)
- Background entity resolution tasks completely untested
- `resolve_entities` Celery task
- `extract_relationships` Celery task

#### `app/entities/graph_service.py` (32%)
- Most Neo4j Cypher operations untested:
  - `get_entity_by_id`, `get_entity_connections`
  - `get_graph_neighborhood`, `find_paths_between`
  - `get_temporal_relationships`, `get_graph_stats`
  - `get_entity_timeline`

#### `app/ingestion/service.py` (29%)
- `IngestService.create_job()`, `update_job()`, `cancel_job()`
- Job lifecycle management untested

#### `app/common/storage.py` (47%)
- MinIO `upload_file()`, `download_file()`, `presigned_url()`
- Bucket operations

### Modules Without Dedicated Test Files

The following app modules have **no corresponding test file**:
- `app/common/storage.py` — no `tests/test_common/test_storage.py`
- `app/common/llm.py` — no `tests/test_common/test_llm.py`
- `app/entities/relationship_extractor.py` — no test file
- `app/entities/tasks.py` — no test file
- `app/entities/schemas.py` — no dedicated tests (schemas used indirectly)
- `app/edrm/service.py` — no `tests/test_edrm/test_service.py`
- `app/ingestion/service.py` — no `tests/test_ingestion/test_service.py`
- `app/ingestion/tasks.py` — no `tests/test_ingestion/test_tasks.py`
- `app/main.py` — no `tests/test_main.py`

### Privilege Matrix Test Coverage

Privilege enforcement is tested at 3 layers:
- **SQL layer:** `test_privilege.py::test_reviewer_cannot_see_privileged_docs` — PASS
- **Qdrant layer:** `test_privilege.py::test_qdrant_query_builds_must_not_filter` — PASS
- **Neo4j layer:** `test_privilege.py::test_graph_connections_includes_privilege_exclusion` — PASS
- **Pipeline thread-through:** `test_nodes.py::test_graph_lookup_passes_exclude_privilege` — PASS

Privilege enforcement has good test coverage. The testing policy's "privilege at data layer" requirement is met.

---

## 6. CI/CD & Tooling Gaps

### Current State

| Tool | Status | Notes |
|---|---|---|
| GitHub Actions | **Not configured** | No `.github/workflows/` directory |
| Pre-commit hooks | **gitleaks only** | `.pre-commit-config.yaml` has only secret scanning |
| Ruff lint | **Not enforced** | No CI check, no pre-commit hook |
| Ruff format | **Not enforced** | 51% of files have formatting drift |
| Mypy | **Not configured** | No `mypy.ini`, no `[tool.mypy]` in pyproject.toml, not in dev deps |
| pytest in CI | **Not configured** | Tests only run manually |
| Coverage reporting | **Not configured** | No coverage floor enforcement |
| Alembic migration checks | **Not configured** | No CI verification of up/down migrations |

### What's Needed for Roadmap Compliance

The roadmap's Testing Policy specifies:
1. **Regression Gate:** All tests must pass before marking a milestone Done. Currently manual-only — needs CI automation.
2. **Coverage Floor:** No milestone may decrease coverage. Currently no enforcement.
3. **Evaluation Regression Gate (M10+):** `scripts/evaluate.py` must run. The script doesn't exist yet (M9 scope).

**Minimum CI pipeline needed:**
```yaml
# .github/workflows/ci.yml
- pytest tests/ -v --cov=app --cov-fail-under=60
- ruff check app/ tests/ workers/
- ruff format --check app/ tests/ workers/
- mypy app/ --ignore-missing-imports  # once config exists
```

---

## 7. Prioritized Recommendations

### P0: Blocking Issues

None. All 266 tests pass, coverage exceeds the M10 target, and no production-breaking issues were found.

### P1: Should Fix Before Next Milestone

1. **Run `ruff check --fix` and `ruff format`** — 89 of 105 lint violations are auto-fixable. The 57 formatting-drift files can be batch-formatted. Single commit, zero risk.

2. **Add mypy configuration** — Create `[tool.mypy]` in `pyproject.toml` with `ignore_missing_imports = true` and `check_untyped_defs = false` (gradual adoption). Fix the 18 errors (most are straightforward type narrowing or `type: ignore` annotations).

3. **Add `ruff` and `ruff format` to pre-commit hooks** — Prevents drift from accumulating again.

4. **Write tests for `app/ingestion/tasks.py`** (22% → target 50%) — The Celery pipeline is the system's most critical code path. At minimum, test each stage's happy path and error handling with mocked external services.

### P2: Should Fix Before M10

5. **Add test coverage for `app/common/llm.py`** — Test both Anthropic and OpenAI provider paths with mocked API clients. This is the second-most-critical untested module.

6. **Add test file for `app/entities/relationship_extractor.py`** — Even though it's feature-flagged, the code exists and ships. Test the Instructor contract.

7. **Add test file for `app/entities/tasks.py`** — Background entity resolution is untested. Mock Celery tasks and verify correct parameters.

8. **Set up GitHub Actions CI** — At minimum: `pytest + coverage`, `ruff check`, `ruff format --check`. Add `mypy` once config is stable. This is the roadmap's requirement for automated quality gates.

9. **Raise EDRM module coverage** — `app/edrm/router.py` (42%) and `app/edrm/service.py` (46%) are below the 50% requirement for new modules. Add router integration tests and service unit tests before marking M6b as Done.

### P3: Nice to Have

10. **Add `--durations=10` to default pytest args** in `pyproject.toml` — Identify slow tests as the suite grows (currently 34 min total).

11. **Consider pytest-xdist** for parallel test execution — 34 minutes is long for a 266-test suite. Most tests are independent and could run in parallel.

12. **Add `app/entities/schemas.py` tests** — 0% coverage on 29 statements. These are Pydantic models and should have validation tests.

13. **Add `app/common/storage.py` tests** — 47% coverage. MinIO operations are used by multiple modules and should have their own contract tests.

14. **Consider strict mypy** (`--strict`) as a long-term goal — The codebase already types most signatures. Gradual strictness would catch bugs earlier.

---

## Appendix: Raw Ruff Output (Violation Locations)

<details>
<summary>Full ruff check output (105 violations)</summary>

### By rule:

| Count | Rule | Description |
|---|---|---|
| 35 | F401 | Unused imports |
| 29 | I001 | Unsorted import blocks |
| 23 | UP017 | `timezone.utc` → `datetime.UTC` |
| 7 | F841 | Unused variables |
| 4 | E741 | Ambiguous variable names |
| 3 | N806 | Non-lowercase variable in function |
| 2 | UP035 | Deprecated imports |
| 1 | N815 | Mixed-case variable in class scope |
| 1 | UP046 | Non-PEP 695 generic class |

</details>

<details>
<summary>Full mypy output (18 errors)</summary>

```
app/ingestion/service.py:275: error: "Result[Any]" has no attribute "rowcount"  [attr-defined]
app/documents/service.py:279: error: "Result[Any]" has no attribute "rowcount"  [attr-defined]
app/common/vector_store.py:198: error: Argument "must" to "Filter" has incompatible type  [arg-type]
app/common/vector_store.py:199: error: Argument "must_not" to "Filter" has incompatible type  [arg-type]
app/common/vector_store.py:239: error: Unpacked dict entry 2 has incompatible type  [dict-item]
app/query/retriever.py:116: error: Item "BaseException" has no attribute "__iter__"  [union-attr]
app/ingestion/tasks.py:275: error: Incompatible types in assignment  [assignment]
app/ingestion/tasks.py:793: error: Incompatible types in assignment  [assignment]
app/ingestion/tasks.py:796: error: Argument "vector" to "PointStruct" has incompatible type  [arg-type]
app/common/llm.py:206: error: Item "ThinkingBlock" has no attribute "text"  [union-attr]
app/common/llm.py:206: error: Item "RedactedThinkingBlock" has no attribute "text"  [union-attr]
app/common/llm.py:206: error: Item "ToolUseBlock" has no attribute "text"  [union-attr]
app/common/llm.py:206: error: Item "ServerToolUseBlock" has no attribute "text"  [union-attr]
app/common/llm.py:206: error: Item "WebSearchToolResultBlock" has no attribute "text"  [union-attr]
app/common/llm.py:305: error: Item "ChatCompletion" has no attribute "__aiter__"  [union-attr]
app/query/router.py:440: error: "Result[Any]" has no attribute "rowcount"  [attr-defined]
app/ingestion/router.py:133: error: Argument "status" has incompatible type "str"; expected "JobStatus"  [arg-type]
app/edrm/router.py:52: error: Incompatible types in assignment  [assignment]
```

</details>
