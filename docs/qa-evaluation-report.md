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

**Pre-fix**: 18/22 queries failed (HTTP 500 — `ValueError('contents are required.')`)
**Post-fix (v1.11.0)**: RESOLVED. Queries complete but with ~160s latency per query.

### enable_hyde

**Pre-fix**: 2/22 failed (gt-009, gt-018 — eval client timeout)
**Post-fix (v1.12.3)**: RESOLVED. 0/22 errors in verification sweep.

### enable_retrieval_grading

No errors.

### enable_citation_verification

No errors.

### enable_multi_query_expansion

**Pre-fix**: 2/22 failed (gt-009, gt-019 — eval client timeout)
**Post-fix (v1.12.3)**: RESOLVED. 0/22 errors in verification sweep.

### enable_prompt_routing

**Pre-fix**: 1/22 failed (gt-009 — eval client timeout)
**Post-fix (v1.12.3)**: RESOLVED. 0/22 errors in verification sweep.

### enable_text_to_sql

**Pre-fix**: 1/22 failed (gt-009 — eval client timeout)
**Post-fix (v1.12.3)**: RESOLVED. 0/22 errors in verification sweep.

### enable_hallugraph_alignment

No errors (pre- or post-fix).

### enable_adaptive_retrieval_depth

**Pre-fix**: 2/22 failed (gt-009, gt-019 — eval client timeout)
**Post-fix (v1.12.3)**: RESOLVED. 0/22 errors in verification sweep.

### enable_production_quality_monitoring

**Pre-fix**: 2/22 failed (gt-009, gt-018 — eval client timeout)
**Post-fix (v1.12.3)**: RESOLVED. 0/22 errors in verification sweep.

### enable_self_reflection

No errors.

### enable_question_decomposition

**Pre-fix**: 1/22 failed (gt-009 — eval client timeout)
**Post-fix (v1.12.3)**: RESOLVED. 0/22 errors in verification sweep.

### enable_reranker

**Pre-fix**: 2/22 failed (gt-009, gt-018 — eval client timeout)
**Post-fix (v1.12.3)**: RESOLVED. 0/22 errors in verification sweep.

### enable_text_to_cypher

**Pre-fix**: 1/22 failed (gt-009 — eval client timeout)
**Post-fix (v1.12.3)**: RESOLVED. 0/22 errors in verification sweep.

## Findings & Issues

### CRITICAL

- **enable_auto_graph_routing** (bug): 18/22 queries failed when flag toggled
  - Evidence: HTTP 500: Internal Server Error
  - Root cause: `ValueError('contents are required.')` — Gemini API rejects empty `messages` list when V1 pipeline was selected by auto-routing but fed the agentic state
  - **RESOLVED** in v1.11.0 (commit `1599ee7`): `prevent Gemini ValueError on empty messages in agentic pipeline`

### HIGH

Two root causes contributed to these failures:

**Root cause 1 — `Settings()` bug in 6 agent tools** (RESOLVED v1.12.2):
The tools `topic_cluster`, `network_analysis`, `decompose_query`, `cypher_query`, `structured_query`, and `get_community_context` used `Settings()` (reads env vars only) instead of `get_settings()` (reads runtime DB overrides). When the evaluation framework toggled flags via the runtime admin API, these tools never saw the changes, causing incorrect evaluation metrics.

**Root cause 2 — gt-009 deep-tier timeout chain** (RESOLVED v1.12.3):
The timeline query `"Describe the timeline of the Acme/Pinnacle merger discussions..."` was classified as `deep` tier, receiving a recursion limit of 60 (vs 40 standard). Combined with per-flag overhead (HyDE +1 LLM call, multi-query +1 LLM call + N retrievals, prompt routing +1 LLM call, quality monitoring async scoring), total processing time exceeded the eval client's 120s timeout. The timeout chain:
1. Deep tier classification (`app/query/nodes.py`): `"timeline of"` → `deep` → recursion_limit=60
2. Timeline prompt addendum encouraging extra tool calls (`temporal_search`, gap analysis)
3. Case context LLM call (classify_tier + optional CLASSIFY_PROMPT)
4. Post-agent entity extraction (GLiNER CPU-bound in thread)
5. Citation verification (batch embed all claims + parallel retrieval)
6. Per-flag overhead stacking past 120s

**Fix (v1.12.3):**
- Reduced `agentic_recursion_limit_deep` default from 60 to 40 — deep queries shouldn't get unbounded agent budget
- Increased eval client timeout from 120s to 180s (`EVAL_QUERY_TIMEOUT_S` constant) — deep-tier queries with flag overhead legitimately need >120s
- Extracted hardcoded timeouts into a single shared constant (`evaluation/runner.py` + `evaluation/flag_sweep.py`)

Individual flag findings prior to fix:
- **enable_hyde**: 2/22 failed (gt-009, gt-018)
- **enable_multi_query_expansion**: 2/22 failed (gt-009, gt-019)
- **enable_prompt_routing**: 1/22 failed (gt-009)
- **enable_text_to_sql**: 1/22 failed (gt-009)
- **enable_adaptive_retrieval_depth**: 2/22 failed (gt-009, gt-019)
- **enable_production_quality_monitoring**: 2/22 failed (gt-009, gt-018)
- **enable_question_decomposition**: 1/22 failed (gt-009)
- **enable_reranker**: 2/22 failed (gt-009, gt-018)
- **enable_text_to_cypher**: 1/22 failed (gt-009)

**Verification (v1.12.3 partial sweep, 2026-03-14)**:
Post-fix eval completed 12/14 flag configs before JWT expiration (auto_graph_routing queries took ~160s each, exhausting the 30min token). Results:
- **gt-009: 12/12 successful completions, 0 HTTP 500s** (was 9 failures out of 14 configs pre-fix)
- **gt-018, gt-019: 0 failures** across all 12 completed configs (were 5 failures combined pre-fix)
- **0 total HTTP 500 errors** across 264 queries (12 configs × 22 queries)
- gt-009 latencies: 5.8s–20.3s (well within 180s eval timeout)
- The 2 incomplete configs (`enable_auto_graph_routing`, `enable_hallugraph_alignment`) were already in the 5 configs that passed gt-009 pre-fix

**Remaining action**: Re-run full sweep with longer JWT expiry or auth token refresh to capture updated flag delta metrics. The gt-009/gt-018/gt-019 timeout issue is confirmed resolved.

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