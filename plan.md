# Feature Flag Evaluation Harness — Implementation Plan

## Goal
Build a harness that toggles feature flags (individually and in combinations), runs the query pipeline against a ground-truth dataset, measures retrieval/generation/citation metrics, and reports deltas vs baseline — answering "what is the measurable impact of each flag?"

## Architecture Decision

**Extend the existing `evaluation/` framework** rather than building a new system. The schemas, metrics, tuning comparison infrastructure, and CLI are already in place. We need to:
1. Implement the real evaluation runner (currently `NotImplementedError`)
2. Add flag sweep orchestration on top

## Implementation Steps

### Step 1: Flag Sweep Schemas (`evaluation/schemas.py`)
Add new schemas for flag sweep results:

- `FlagSweepConfig` — which flags to test, individually or in combinations
  - `flags: list[str]` — flag names to sweep
  - `combinations: bool` — test pairwise combinations (default: False, exponential)
  - `baseline_overrides: dict[str, str]` — baseline config (default: all flags at env defaults)
- `FlagSweepResult` — per-flag-state evaluation result
  - `flag_states: dict[str, bool]` — which flags were on/off for this run
  - `retrieval: list[RetrievalMetrics]`
  - `generation: GenerationMetrics | None`
  - `citation: CitationMetrics | None`
  - `quality_gates_passed: bool`
  - `gate_failures: list[str]`
  - `latency_p50_ms: float`
  - `latency_p95_ms: float`
- `FlagSweepReport` — full experiment report
  - `timestamp, baseline: FlagSweepResult`
  - `experiments: list[FlagSweepResult]`
  - `flag_impact_summary: list[FlagImpactSummary]` — per-flag delta analysis
- `FlagImpactSummary` — single flag's measured impact
  - `flag_name: str`
  - `delta_mrr, delta_recall, delta_ndcg, delta_faithfulness, delta_citation_accuracy: float`
  - `delta_latency_p50_ms: float`
  - `quality_gates_pass_with: bool` (gates pass when flag is ON)
  - `quality_gates_pass_without: bool` (gates pass when flag is OFF)
  - `recommendation: str` (keep_enabled / keep_disabled / negligible_impact)

### Step 2: Flag Sweep Runner (`evaluation/flag_sweep.py`)
New module — the core orchestration logic.

**Key function**: `async run_flag_sweep(config: FlagSweepConfig, dataset: EvaluationDataset, verbose: bool) -> FlagSweepReport`

Logic:
1. Record current flag states as baseline
2. Run evaluation with baseline flags → `baseline_result`
3. For each flag in `config.flags`:
   a. Toggle flag OFF (if currently ON) or ON (if currently OFF)
   b. Clear affected DI caches (using `FLAG_REGISTRY[flag].di_caches`)
   c. Run evaluation → `experiment_result`
   d. Restore flag to original state, clear caches again
4. If `config.combinations`: run pairwise combos (flag_a + flag_b toggled together)
5. Compute deltas and `FlagImpactSummary` for each flag
6. Generate recommendation per flag based on metric deltas + gate pass/fail

**Evaluation per run**: calls into a new `_evaluate_once()` that:
- Hits the query pipeline for each ground-truth question (via HTTP or direct service call)
- Collects retrieved doc IDs + generated answer + citations
- Computes retrieval metrics (existing `evaluation/metrics/retrieval.py`)
- Computes citation metrics (existing `evaluation/metrics/citation.py`)
- Optionally computes RAGAS generation metrics
- Measures latency (wall-clock per query)

**Two modes**:
- `--dry-run-sweep`: Uses synthetic data with flag-aware quality bias (extends existing tuning approach). No infrastructure needed. Useful for CI/testing the harness itself.
- `--live-sweep`: Hits real running NEXUS instance via HTTP. Requires `make dev` running.

### Step 3: Dry-Run Flag Sweep (`evaluation/flag_sweep.py`)
For the dry-run mode, extend the existing `_compute_dry_run_metrics()` pattern from `tuning.py`:

- Map each flag to an estimated quality_bias based on what it does:
  - `enable_reranker`: +0.15 (high impact on ranking)
  - `enable_sparse_embeddings`: +0.08 (moderate impact)
  - `enable_hyde`: +0.05 (modest impact)
  - `enable_citation_verification`: 0.0 on retrieval, +0.10 on citation accuracy
  - `enable_multi_query_expansion`: +0.06
  - etc.
- When a flag is OFF, subtract its bias from baseline
- This gives deterministic but directionally-meaningful estimates

### Step 4: Live Flag Sweep (`evaluation/flag_sweep.py`)
For the live mode:

- Use `httpx.AsyncClient` to hit the running API
- Toggle flags via `PUT /api/v1/admin/feature-flags/{flag_name}`
- Run queries via `POST /api/v1/query` (or the evaluation-specific endpoint)
- Collect responses, extract metrics
- Restore flags when done

This requires:
- A running NEXUS instance
- Admin auth token (from env var `EVAL_AUTH_TOKEN` or generated)
- A populated matter with ground-truth data

### Step 5: CLI Integration (`scripts/evaluate.py`)
Add `--flag-sweep` mode to existing CLI:

```bash
# Dry-run: synthetic metrics, no infrastructure
python scripts/evaluate.py --flag-sweep --dry-run

# Dry-run specific flags only
python scripts/evaluate.py --flag-sweep --dry-run --flags enable_reranker enable_hyde enable_sparse_embeddings

# Live: real queries against running instance
python scripts/evaluate.py --flag-sweep --api-url http://localhost:8000 --auth-token $TOKEN

# With pairwise combinations
python scripts/evaluate.py --flag-sweep --dry-run --combinations

# Output to file
python scripts/evaluate.py --flag-sweep --dry-run --output flag-report.json
```

### Step 6: Tests (`tests/test_evaluation/`)
- `test_flag_sweep_schemas.py` — schema validation, serialization
- `test_flag_sweep_runner.py` — dry-run sweep logic, delta computation, recommendations
- `test_flag_sweep_cli.py` — CLI argument parsing, output formatting

Tests use the existing `conftest.py` patterns. Mock the query pipeline for unit tests.

### Step 7: Report Formatting
Add a `format_flag_sweep_report(report: FlagSweepReport) -> str` function that produces:
- Summary table: flag | MRR delta | Recall delta | NDCG delta | latency delta | gates | recommendation
- Detailed per-flag breakdown
- Overall recommendation

## Scope / What We're NOT Building
- No UI (admin UI integration is a separate task)
- No automated CI integration (just exit codes for now)
- No exhaustive combinatorial search (pairwise only, opt-in)
- Not implementing `run_full()` in `evaluation/runner.py` — the flag sweep has its own evaluation path

## File Changes Summary
| File | Action |
|------|--------|
| `evaluation/schemas.py` | Add FlagSweep* schemas |
| `evaluation/flag_sweep.py` | **New** — core sweep runner |
| `scripts/evaluate.py` | Add --flag-sweep CLI mode |
| `tests/test_evaluation/test_flag_sweep.py` | **New** — tests |

## Order of Implementation
1. Schemas (Step 1)
2. Dry-run sweep runner (Steps 2-3)
3. CLI integration (Step 5)
4. Tests (Step 6)
5. Report formatting (Step 7)
6. Live sweep (Step 4) — can be deferred, depends on full eval infra
