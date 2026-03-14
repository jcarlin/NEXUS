# NEXUS Feature Flag QA Evaluation Report

**Generated**: 2026-03-14 17:44:32 UTC

## Environment

- **api_url**: http://localhost:8000
- **matter_id**: 00000000-0000-0000-0000-000000000001
- **num_ground_truth**: 22
- **judge_enabled**: False
- **timestamp**: 2026-03-14T17:44:32.342129+00:00
- **llm_provider**: gemini
- **llm_model**: gemini-2.0-flash
- **embedding_provider**: ollama
- **embedding_model**: nomic-embed-text

## Baseline Results

Default configuration (all flags at their default state).

| Metric | Baseline |
|--------|--------|
| Latency p50 | 4461 ms |
| Latency p95 | 14427 ms |
| Latency mean | 5243 ms |
| MRR@10 | 0.3458 |
| Recall@10 | 0.6958 |
| NDCG@10 | 0.0000 |
| Citation Accuracy | 0.6667 |
| Hallucination Rate | 0.0000 |
| Total Claims | 6 |
| Queries | 22 |
| Gates Passed | No |


## Individual Feature Flag Results

Each row shows the delta when the flag is toggled from its default state.

| Flag | MRR Delta | Recall Delta | NDCG Delta | Latency Delta (ms) | Citation Delta | Judge Delta | Recommendation |
|------|-----------|-------------|------------|-------------------|----------------|-------------|----------------|
| `enable_auto_graph_routing` | +0.0292 | -0.3625 | +0.0000 | +5883 | -0.0000 | +0.00 | keep_disabled |
| `enable_hyde` | -0.0942 | -0.2958 | +0.0000 | +829 | -0.0000 | +0.00 | keep_disabled |
| `enable_retrieval_grading` | -0.1489 | -0.2072 | +0.0000 | -214 | -0.0000 | +0.00 | keep_disabled |
| `enable_citation_verification` | +0.1451 | +0.2072 | +0.0000 | +1345 | +0.0000 | +0.00 | keep_enabled |
| `enable_multi_query_expansion` | -0.1442 | -0.2000 | +0.0000 | +3416 | -0.0000 | +0.00 | keep_disabled |
| `enable_prompt_routing` | +0.0962 | +0.2264 | +0.0000 | +3036 | -0.0000 | +0.00 | keep_enabled |
| `enable_text_to_sql` | -0.1038 | -0.1363 | +0.0000 | -441 | -0.0000 | +0.00 | keep_disabled |
| `enable_hallugraph_alignment` | +0.0769 | +0.1466 | +0.0000 | +7 | -0.0000 | +0.00 | keep_enabled |
| `enable_adaptive_retrieval_depth` | -0.0542 | +0.1167 | +0.0000 | -226 | -0.0000 | +0.00 | keep_enabled |
| `enable_production_quality_monitoring` | -0.0792 | -0.0917 | +0.0000 | +215 | -0.0000 | +0.00 | keep_disabled |
| `enable_self_reflection` | -0.0087 | -0.1269 | +0.0000 | +795 | -0.0000 | +0.00 | keep_disabled |
| `enable_question_decomposition` | -0.0403 | -0.0728 | +0.0000 | -356 | -0.0000 | +0.00 | keep_disabled |
| `enable_reranker` | +0.0042 | -0.0500 | +0.0000 | -72 | -0.0000 | +0.00 | keep_disabled |
| `enable_text_to_cypher` | -0.0204 | +0.0145 | +0.0000 | +59 | -0.0000 | +0.00 | negligible_impact |

### enable_auto_graph_routing

**Errors**: 18/22 queries failed
  - `gt-001`: HTTP 500: Internal Server Error
  - `gt-002`: HTTP 500: Internal Server Error
  - `gt-003`: HTTP 500: Internal Server Error

### enable_hyde

**Errors**: 2/22 queries failed
  - `gt-009`: HTTP 500: Internal Server Error
  - `gt-018`: HTTP 500: Internal Server Error

### enable_retrieval_grading


### enable_citation_verification


### enable_multi_query_expansion

**Errors**: 2/22 queries failed
  - `gt-009`: HTTP 500: Internal Server Error
  - `gt-019`: HTTP 500: Internal Server Error

### enable_prompt_routing

**Errors**: 1/22 queries failed
  - `gt-009`: HTTP 500: Internal Server Error

### enable_text_to_sql

**Errors**: 1/22 queries failed
  - `gt-009`: HTTP 500: Internal Server Error

### enable_hallugraph_alignment


### enable_adaptive_retrieval_depth

**Errors**: 2/22 queries failed
  - `gt-009`: HTTP 500: Internal Server Error
  - `gt-019`: HTTP 500: Internal Server Error

### enable_production_quality_monitoring

**Errors**: 2/22 queries failed
  - `gt-009`: HTTP 500: Internal Server Error
  - `gt-018`: HTTP 500: Internal Server Error

### enable_self_reflection


### enable_question_decomposition

**Errors**: 1/22 queries failed
  - `gt-009`: HTTP 500: Internal Server Error

### enable_reranker

**Errors**: 2/22 queries failed
  - `gt-009`: HTTP 500: Internal Server Error
  - `gt-018`: HTTP 500: Internal Server Error

### enable_text_to_cypher

**Errors**: 1/22 queries failed
  - `gt-009`: HTTP 500: Internal Server Error

## Findings & Issues

### CRITICAL

- **enable_auto_graph_routing** (bug): 18/22 queries failed when flag toggled
  - Evidence: HTTP 500: Internal Server Error
  - Root cause: `ValueError('contents are required.')` — Gemini API rejects empty `messages` list when V1 pipeline was selected by auto-routing but fed the agentic state
  - **RESOLVED** in v1.11.0 (commit `1599ee7`): `prevent Gemini ValueError on empty messages in agentic pipeline`

### HIGH

All 9 HIGH findings share the same root cause: **`Settings()` bug in 6 agent tools**.

The tools `topic_cluster`, `network_analysis`, `decompose_query`, `cypher_query`, `structured_query`, and `get_community_context` used `Settings()` (reads env vars only) instead of `get_settings()` (reads runtime DB overrides). When the evaluation framework toggled flags via the runtime admin API, these tools never saw the changes. This caused:
- **Incorrect evaluation metrics**: tools operated with default flag values regardless of what was toggled
- **gt-009 failures (all 9 configs)**: complex timeline query that pushes the LLM close to timeout; any flag that adds overhead (HyDE, multi-query, quality monitoring) tipped it over the 120s eval client timeout
- **gt-018/gt-019 failures (5 configs)**: similar timeout mechanism on hard queries

**RESOLVED** in v1.12.2: all 6 tools now use `get_settings()` for runtime flag visibility. Router error handling also improved — graph exceptions now return structured HTTP 500 with actionable detail messages instead of opaque "Internal Server Error".

Individual flag findings (to be re-evaluated after fix):
- **enable_hyde**: 2/22 failed (gt-009, gt-018)
- **enable_multi_query_expansion**: 2/22 failed (gt-009, gt-019)
- **enable_prompt_routing**: 1/22 failed (gt-009)
- **enable_text_to_sql**: 1/22 failed (gt-009)
- **enable_adaptive_retrieval_depth**: 2/22 failed (gt-009, gt-019)
- **enable_production_quality_monitoring**: 2/22 failed (gt-009, gt-018)
- **enable_question_decomposition**: 1/22 failed (gt-009)
- **enable_reranker**: 2/22 failed (gt-009, gt-018)
- **enable_text_to_cypher**: 1/22 failed (gt-009)

**Action required**: Re-run `python scripts/evaluate.py --flag-sweep --skip-judge --output docs/qa-evaluation-report.md` to generate updated metrics with the fix applied.

### MEDIUM

- **enable_auto_graph_routing** (regression): Retrieval quality regression (total delta: -0.3333)
- **enable_auto_graph_routing** (note): Significant latency increase: +5883ms
- **enable_hyde** (regression): Retrieval quality regression (total delta: -0.3900)
- **enable_retrieval_grading** (regression): Retrieval quality regression (total delta: -0.3561)
- **enable_multi_query_expansion** (regression): Retrieval quality regression (total delta: -0.3442)
- **enable_text_to_sql** (regression): Retrieval quality regression (total delta: -0.2401)
- **enable_production_quality_monitoring** (regression): Retrieval quality regression (total delta: -0.1708)
- **enable_self_reflection** (regression): Retrieval quality regression (total delta: -0.1356)
- **enable_question_decomposition** (regression): Retrieval quality regression (total delta: -0.1131)

### INFO

- **enable_citation_verification** (improvement): Retrieval quality improvement (total delta: +0.3523)
- **enable_prompt_routing** (improvement): Retrieval quality improvement (total delta: +0.3226)
- **enable_hallugraph_alignment** (improvement): Retrieval quality improvement (total delta: +0.2235)
- **enable_adaptive_retrieval_depth** (improvement): Retrieval quality improvement (total delta: +0.0625)

## Recommendations

### ENABLE: Recommended to enable (quality improvement with acceptable cost)

- `enable_citation_verification`
- `enable_prompt_routing`
- `enable_hallugraph_alignment`
- `enable_adaptive_retrieval_depth`

### FIX_FIRST: Has issues that need fixing before enabling

- `enable_auto_graph_routing`

### SKIP: Not recommended (regression or unacceptable latency cost)

- `enable_multi_query_expansion`

### NEUTRAL: No significant impact — enable or disable based on preference

- `enable_hyde`
- `enable_retrieval_grading`
- `enable_text_to_sql`
- `enable_production_quality_monitoring`
- `enable_self_reflection`
- `enable_question_decomposition`
- `enable_reranker`
- `enable_text_to_cypher`


---
*Report generated by NEXUS QA Evaluation Framework*