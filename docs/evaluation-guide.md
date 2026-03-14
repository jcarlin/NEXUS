# Feature Flag QA Evaluation Guide

How to run the NEXUS feature flag evaluation framework to measure the impact of feature flags on retrieval quality, answer quality, latency, and correctness.

## Quick Start

```bash
# Prerequisite: running NEXUS instance (make dev)
make dev

# Baseline only (~2 min, no flag toggling)
python scripts/evaluate.py --flag-sweep --baseline-only --output reports/baseline.md

# Individual flag ablation (~30 min)
python scripts/evaluate.py --flag-sweep --skip-judge --output reports/qa-report.md

# Full sweep: individual + curated combos + standalone + ingestion (~1 hour)
python scripts/evaluate.py --flag-sweep --full --skip-judge --output reports/full-report.md

# With LLM-as-judge scoring (uses API credits, adds answer quality dimension)
python scripts/evaluate.py --flag-sweep --output reports/with-judge.md

# Single flag test
python scripts/evaluate.py --flag-sweep --flags enable_hyde --output reports/hyde.md
```

## Architecture

```
evaluation/
  judge.py          # LLM-as-judge 5-dimension quality scorer
  prompts.py        # Judge prompt templates
  report.py         # Markdown report generator
  runner.py         # Core evaluation engine (run_full, evaluate_queries)
  flag_sweep.py     # Flag toggle orchestrator + curated combos
  schemas.py        # Pydantic schemas for all evaluation data
  data/
    ground_truth.json  # 22 corpus-specific Q&A pairs + 3 adversarial
scripts/
  evaluate.py       # CLI entry point
tests/
  test_evaluation/
    test_judge.py        # 19 tests
    test_report.py       # 17 tests
    test_runner_full.py  # 14 tests
    test_flag_sweep.py   # 29 tests (from PR #10)
```

## What It Measures

For each flag configuration, the framework measures:

| Metric | Source | Description |
|--------|--------|-------------|
| Functional | HTTP status | 200 OK with valid response structure |
| Latency p50/p95 | Timer | Query duration percentiles |
| Answer Quality | LLM-as-judge | 1-5 composite (relevance, completeness, accuracy, citation support, conciseness) |
| MRR@10 | Retrieval | First relevant doc rank vs ground-truth |
| Recall@10 | Retrieval | Fraction of expected docs in top 10 |
| Citation Count | `cited_claims` | Number of cited claims |
| Citation Verified % | `cited_claims` | % with `verification_status=verified` |
| Source Relevance | `source_documents` | Average `relevance_score` |
| Error Rate | HTTP errors | % of queries returning non-200 |

## Feature Flag Groups

### Group A: Query-Time (14 flags)
Toggle at runtime via admin API. No restart needed.

`enable_reranker`, `enable_retrieval_grading`, `enable_citation_verification`, `enable_multi_query_expansion`, `enable_text_to_cypher`, `enable_prompt_routing`, `enable_question_decomposition`, `enable_hyde`, `enable_self_reflection`, `enable_text_to_sql`, `enable_production_quality_monitoring`, `enable_adaptive_retrieval_depth`, `enable_auto_graph_routing`, `enable_hallugraph_alignment`

### Group B: Ingestion-Time (5 flags)
Require re-ingesting documents to take effect.

`enable_contextual_chunks`, `enable_chunk_quality_scoring`, `enable_document_summarization`, `enable_ocr_correction`, `enable_near_duplicate_detection`

### Group C: Standalone (4 flags)
Test via dedicated endpoints, not the query pipeline.

`enable_deposition_prep`, `enable_document_comparison`, `enable_graphrag_communities`, `enable_data_retention`

### Group D: Skip
Not testable via evaluation (require restart, no quality signal).

`enable_sso`, `enable_saml`, `enable_google_drive`, `enable_prometheus_metrics`, `enable_memo_drafting`, `enable_batch_embeddings`

## Curated Combinations

Beyond individual ablation, the framework tests meaningful stacks:

| Combo | Flags | Rationale |
|-------|-------|-----------|
| Quality Stack | HyDE + self-reflection + retrieval grading + prompt routing | Max quality |
| Speed Stack | auto graph routing + adaptive depth | Fast path |
| Full RAG | All quality flags | Everything on |
| Ablation: No Reranker | reranker=false | Measure reranker value |
| Ablation: No Citation | citation_verification=false | Measure citation value |
| Kitchen Sink | ALL Group A flags | Stress test |

## Ground-Truth Dataset

`evaluation/data/ground_truth.json` contains 22 Q&A pairs mapped to the actual corpus:

- **8 easy** (single-doc factual): entity lookups, dates, roles
- **8 medium** (multi-doc analytical): timelines, due diligence issues, communication patterns
- **4 hard** (cross-document reasoning): legal risk analysis, financial summaries
- **2 negative** (out-of-scope): should return "not in corpus"
- **3 adversarial**: privilege tricks, false premises, entity confusion

Each item has `expected_documents` mapped to real filenames in Qdrant (e.g., `email_chen_to_kim.eml`, `board_minutes_jan25.txt`).

## LLM-as-Judge

The judge scorer (`evaluation/judge.py`) auto-detects the best available LLM provider:

1. **Anthropic** (preferred) — Claude Sonnet via Instructor
2. **OpenAI** — GPT-4o via Instructor
3. **Gemini** — Gemini Flash via google-genai

It reads API keys from `.env` (including commented-out keys) and uses Instructor for structured extraction of 5-dimension scores. Skip with `--skip-judge` for faster runs.

## Recommendations Engine

The framework auto-generates per-flag recommendations:

| Recommendation | Criteria |
|---------------|----------|
| **ENABLE** | judge_delta > +0.2 OR (retrieval_delta > +0.02 AND latency < 5s) |
| **FIX_FIRST** | >50% queries fail OR error_rate > 20% |
| **SKIP** | Quality regression OR (no improvement AND latency > 3s) |
| **NEUTRAL** | Everything else |

## Token Refresh

The sweep automatically refreshes JWT tokens every 25 minutes to prevent auth failures during long runs. No manual intervention needed.

## Running Tests

```bash
# All evaluation tests (104 tests, ~10s)
pytest tests/test_evaluation/ -v

# Just the new QA framework tests (50 tests)
pytest tests/test_evaluation/test_judge.py tests/test_evaluation/test_report.py tests/test_evaluation/test_runner_full.py -v
```

## LangSmith Trace Inspection

Use the LangSmith MCP tools to inspect pipeline-internal issues during and after evaluation runs. The `nexus` project logs all LangGraph runs.

### Finding Errored Traces

After a flag sweep, fetch errored runs to find pipeline-internal failures that the eval script can't detect (e.g., nodes that swallow errors and return degraded results):

```
mcp__langsmith__fetch_runs(project_name="nexus", limit=20, error="true")
```

### Finding Slow Runs

Identify nodes causing p95 latency spikes:

```
mcp__langsmith__fetch_runs(project_name="nexus", limit=10, filter='gt(latency, "10s")')
```

### Correlating Traces with Eval Results

Match eval failures to specific LangSmith traces using timestamps:

1. Note the timestamp range of your eval run
2. Fetch runs from that window: `mcp__langsmith__fetch_runs(project_name="nexus", limit=50)`
3. Cross-reference `query_id` from the eval report with trace inputs to identify the failing query's full execution path

### Tracing a Conversation

For thread-level debugging (e.g., tracing a multi-turn query through the graph):

```
mcp__langsmith__get_thread_history(project_name="nexus", thread_id="...")
```

### Example Workflow: Post-Flag-Sweep Debugging

1. Run a flag sweep: `python scripts/evaluate.py --flag-sweep --flags enable_hyde --output reports/hyde.md`
2. Check the report for regressions or errors
3. Fetch errored runs from the last hour in the `nexus` project
4. For each errored run, inspect the trace to see which node raised, what the LLM input/output was, and whether the issue is in retrieval, generation, or post-processing
5. Compare baseline traces vs flag-enabled traces for the same query to pinpoint where the regression occurs

### Verifying Project Exists

```
mcp__langsmith__list_projects()
```

## Updating Ground-Truth

When the corpus changes (new documents ingested), update `evaluation/data/ground_truth.json`:

1. Query Qdrant for current `source_file` values
2. Update `expected_documents` arrays to match actual filenames
3. Verify with `--baseline-only` run

The dataset supports both flat list format and versioned dict format:
```json
{
  "version": "2.0",
  "ground_truth": [...],
  "adversarial": [...]
}
```

## CI Integration

Add to `.github/workflows/`:
```yaml
- name: Feature flag evaluation (dry-run)
  run: python scripts/evaluate.py --dry-run --verbose
```

For live evaluation in CI, the server must be running with populated data.
