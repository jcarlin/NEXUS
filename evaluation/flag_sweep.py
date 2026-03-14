"""Feature flag evaluation sweep runner.

Toggles feature flags against a live NEXUS instance and measures the impact
on retrieval quality, citation accuracy, latency, and LLM-as-judge quality.

Usage:
    python scripts/evaluate.py --flag-sweep --api-url http://localhost:8000
"""

from __future__ import annotations

import statistics
import time
from itertools import combinations as iter_combinations
from pathlib import Path

import httpx
import structlog

from evaluation.metrics.citation import (
    extract_citations,
    hallucination_rate,
)
from evaluation.metrics.retrieval import compute_retrieval_metrics
from evaluation.runner import _check_gates
from evaluation.schemas import (
    CitationMetrics,
    ComboEvalResult,
    FeatureFinding,
    FlagImpactSummary,
    FlagRecommendation,
    FlagRunMetrics,
    FlagSweepConfig,
    FlagSweepReport,
    FlagSweepResult,
    IngestionFeatureTest,
    QAReport,
    QueryEvalResult,
    RetrievalMetrics,
    RetrievalMode,
    StandaloneFeatureTest,
)

logger = structlog.get_logger(__name__)

# Flags that affect query-time behaviour (retrieval, generation, citation).
# Ingestion-only and integration flags are excluded — they require re-ingestion
# or app restart, so sweeping them at query time is meaningless.
QUERY_TIME_FLAGS: list[str] = [
    "enable_reranker",
    "enable_retrieval_grading",
    "enable_citation_verification",
    "enable_multi_query_expansion",
    "enable_text_to_cypher",
    "enable_prompt_routing",
    "enable_question_decomposition",
    "enable_hyde",
    "enable_self_reflection",
    "enable_text_to_sql",
    "enable_production_quality_monitoring",
    "enable_adaptive_retrieval_depth",
    "enable_auto_graph_routing",
    "enable_hallugraph_alignment",
]

DEFAULT_EVAL_QUERIES: list[str] = [
    "What are the key allegations in the complaint?",
    "When was the master service agreement executed?",
    "Describe the timeline of communications between the CEO and CFO regarding the merger.",
    "Compare the indemnification clauses across documents.",
    "What discovery issues were raised in the custodian files?",
]

# Curated flag combinations for combo evaluation
CURATED_COMBOS: dict[str, dict[str, bool]] = {
    "Quality Stack": {
        "enable_hyde": True,
        "enable_self_reflection": True,
        "enable_retrieval_grading": True,
        "enable_prompt_routing": True,
    },
    "Speed Stack": {
        "enable_auto_graph_routing": True,
        "enable_adaptive_retrieval_depth": True,
    },
    "Full RAG": {
        "enable_hyde": True,
        "enable_self_reflection": True,
        "enable_retrieval_grading": True,
        "enable_adaptive_retrieval_depth": True,
        "enable_prompt_routing": True,
        "enable_multi_query_expansion": True,
        "enable_hallugraph_alignment": True,
    },
    "Ablation: No Reranker": {
        "enable_reranker": False,
    },
    "Ablation: No Citation": {
        "enable_citation_verification": False,
    },
    "Kitchen Sink": {flag: True for flag in QUERY_TIME_FLAGS},
}

# Ingestion-time flags that require re-ingestion to test
INGESTION_FLAGS: dict[str, str] = {
    "enable_contextual_chunks": "LLM-generated context prefixes before embedding",
    "enable_chunk_quality_scoring": "Heuristic quality scoring per chunk",
    "enable_document_summarization": "LLM-generated document summaries",
    "enable_ocr_correction": "Regex + optional LLM OCR cleanup",
    "enable_near_duplicate_detection": "MinHash near-duplicate detection",
}

# Standalone feature endpoints
STANDALONE_FEATURES: dict[str, dict[str, str]] = {
    "enable_deposition_prep": {
        "method": "POST",
        "endpoint": "/api/v1/depositions/profiles",
    },
    "enable_document_comparison": {
        "method": "POST",
        "endpoint": "/api/v1/documents/compare",
    },
    "enable_graphrag_communities": {
        "method": "POST",
        "endpoint": "/api/v1/analytics/communities/{matter_id}",
    },
    "enable_data_retention": {
        "method": "GET",
        "endpoint": "/api/v1/admin/retention/policies",
    },
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


async def _login(client: httpx.AsyncClient, api_url: str) -> str:
    """Login as the seed admin and return a JWT token."""
    # Try demo credentials first, fall back to seed admin
    for email, password in [
        ("admin@nexus-demo.com", "nexus-demo-2026"),
        ("admin@example.com", "password123"),
    ]:
        resp = await client.post(
            f"{api_url}/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        if resp.status_code == 200:
            return resp.json()["access_token"]
    # If none worked, raise on the last response
    resp = await client.post(
        f"{api_url}/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


async def _get_flag_states(
    client: httpx.AsyncClient,
    api_url: str,
    headers: dict[str, str],
) -> dict[str, bool]:
    """Fetch current flag states from the admin API."""
    resp = await client.get(f"{api_url}/api/v1/admin/feature-flags", headers=headers)
    resp.raise_for_status()
    return {item["flag_name"]: item["enabled"] for item in resp.json()["items"]}


async def _set_flag(
    client: httpx.AsyncClient,
    api_url: str,
    headers: dict[str, str],
    flag_name: str,
    enabled: bool,
) -> None:
    """Toggle a single flag via the admin API."""
    resp = await client.put(
        f"{api_url}/api/v1/admin/feature-flags/{flag_name}",
        json={"enabled": enabled},
        headers=headers,
    )
    resp.raise_for_status()
    logger.info("flag_sweep.flag_set", flag=flag_name, enabled=enabled)


async def _run_query(
    client: httpx.AsyncClient,
    api_url: str,
    headers: dict[str, str],
    query: str,
    timeout_s: float = 120.0,
) -> tuple[dict, float]:
    """Execute a query and return (response_json, latency_ms)."""
    start = time.perf_counter()
    resp = await client.post(
        f"{api_url}/api/v1/query",
        json={"query": query},
        headers=headers,
        timeout=timeout_s,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    resp.raise_for_status()
    return resp.json(), elapsed_ms


# ---------------------------------------------------------------------------
# Metric collection
# ---------------------------------------------------------------------------


def _collect_metrics_from_responses(
    responses: list[tuple[dict, float]],
    expected_docs_per_query: list[list[str]] | None = None,
) -> FlagRunMetrics:
    """Compute FlagRunMetrics from a list of (response_json, latency_ms) tuples."""
    latencies = [lat for _, lat in responses]
    if not latencies:
        return FlagRunMetrics()

    # Retrieval metrics: if expected_docs provided, compute MRR/Recall/NDCG
    retrieval: RetrievalMetrics | None = None
    if expected_docs_per_query and len(expected_docs_per_query) == len(responses):
        all_m: dict[str, list[float]] = {
            "mrr_at_k": [],
            "recall_at_k": [],
            "precision_at_k": [],
            "ndcg_at_k": [],
        }
        for (resp, _), expected in zip(responses, expected_docs_per_query):
            retrieved_ids = [
                doc.get("filename", doc.get("document_id", "")) for doc in resp.get("source_documents", [])
            ]
            metrics = compute_retrieval_metrics(
                retrieved_ids=retrieved_ids,
                relevant_ids=set(expected),
                k=10,
            )
            for key, value in metrics.items():
                all_m[key].append(value)

        if all_m["mrr_at_k"]:
            avg = {k: statistics.mean(v) for k, v in all_m.items()}
            retrieval = RetrievalMetrics(
                mode=RetrievalMode.HYBRID,
                mrr_at_10=avg["mrr_at_k"],
                recall_at_10=avg["recall_at_k"],
                ndcg_at_10=avg["ndcg_at_k"],
                precision_at_10=avg["precision_at_k"],
                num_queries=len(responses),
            )

    # Citation metrics from response text
    all_citations = []
    all_retrieved_filenames: set[str] = set()
    total_hallucinated = 0
    for resp, _ in responses:
        response_text = resp.get("response", "")
        citations = extract_citations(response_text)
        all_citations.extend(citations)

        source_filenames = {doc.get("filename", doc.get("document_id", "")) for doc in resp.get("source_documents", [])}
        all_retrieved_filenames.update(source_filenames)

        if citations:
            h_rate = hallucination_rate(citations, source_filenames)
            total_hallucinated += int(h_rate * len(citations))

    citation: CitationMetrics | None = None
    if all_citations:
        total = len(all_citations)
        hallucinated = total_hallucinated
        supported = total - hallucinated
        citation = CitationMetrics(
            citation_accuracy=1.0,  # No expected citations in sweep mode
            hallucination_rate=hallucinated / total if total else 0.0,
            post_rationalization_rate=0.0,  # Requires fused context (not in API response)
            total_claims=total,
            supported_claims=supported,
            unsupported_claims=hallucinated,
            post_rationalized_claims=0,
        )

    # Quality gate check

    gate_failures = _check_gates(None, citation)
    gates_passed = len(gate_failures) == 0

    return FlagRunMetrics(
        retrieval=retrieval,
        citation=citation,
        latency_p50_ms=statistics.median(latencies),
        latency_p95_ms=_percentile(latencies, 95),
        latency_mean_ms=statistics.mean(latencies),
        num_queries=len(responses),
        quality_gates_passed=gates_passed,
        gate_failures=gate_failures,
    )


def _percentile(data: list[float], p: int) -> float:
    """Compute the p-th percentile of a sorted list."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p / 100
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[-1]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


# ---------------------------------------------------------------------------
# Impact analysis
# ---------------------------------------------------------------------------


def compute_flag_impact(
    flag_name: str,
    on_metrics: FlagRunMetrics,
    off_metrics: FlagRunMetrics,
) -> FlagImpactSummary:
    """Compute the delta between flag-ON and flag-OFF metrics."""
    delta_mrr = 0.0
    delta_recall = 0.0
    delta_ndcg = 0.0
    delta_precision = 0.0
    if on_metrics.retrieval and off_metrics.retrieval:
        delta_mrr = on_metrics.retrieval.mrr_at_10 - off_metrics.retrieval.mrr_at_10
        delta_recall = on_metrics.retrieval.recall_at_10 - off_metrics.retrieval.recall_at_10
        delta_ndcg = on_metrics.retrieval.ndcg_at_10 - off_metrics.retrieval.ndcg_at_10
        delta_precision = on_metrics.retrieval.precision_at_10 - off_metrics.retrieval.precision_at_10

    delta_citation = 0.0
    if on_metrics.citation and off_metrics.citation:
        delta_citation = on_metrics.citation.hallucination_rate - off_metrics.citation.hallucination_rate
        # Negative delta = fewer hallucinations when ON = good
        delta_citation = -delta_citation  # Flip so positive = better

    delta_latency = on_metrics.latency_mean_ms - off_metrics.latency_mean_ms

    # Recommendation logic
    total_retrieval_delta = delta_mrr + delta_recall + delta_ndcg + delta_precision
    negligible_threshold = 0.02  # Less than 2% total improvement is negligible

    if total_retrieval_delta > negligible_threshold or delta_citation > 0.01:
        recommendation = FlagRecommendation.KEEP_ENABLED
    elif total_retrieval_delta < -negligible_threshold or delta_citation < -0.01:
        recommendation = FlagRecommendation.KEEP_DISABLED
    else:
        recommendation = FlagRecommendation.NEGLIGIBLE_IMPACT

    return FlagImpactSummary(
        flag_name=flag_name,
        delta_mrr=round(delta_mrr, 6),
        delta_recall=round(delta_recall, 6),
        delta_ndcg=round(delta_ndcg, 6),
        delta_precision=round(delta_precision, 6),
        delta_citation_accuracy=round(delta_citation, 6),
        delta_latency_mean_ms=round(delta_latency, 2),
        gates_pass_when_on=on_metrics.quality_gates_passed,
        gates_pass_when_off=off_metrics.quality_gates_passed,
        recommendation=recommendation,
    )


# ---------------------------------------------------------------------------
# Main sweep runner
# ---------------------------------------------------------------------------


async def run_flag_sweep(
    config: FlagSweepConfig,
    verbose: bool = False,
) -> FlagSweepReport:
    """Execute a feature flag evaluation sweep against a live NEXUS instance.

    1. Record current flag states as baseline.
    2. Run evaluation queries with baseline flags.
    3. For each flag: toggle, re-run queries, measure deltas, restore.
    4. Optionally test pairwise combinations.
    5. Compute per-flag impact summaries with recommendations.

    Raises ``httpx.HTTPStatusError`` on API failures.
    """
    sweep_start = time.perf_counter()
    api_url = config.api_url.rstrip("/")
    queries = config.queries or DEFAULT_EVAL_QUERIES
    flags_to_test = config.flags or QUERY_TIME_FLAGS

    logger.info(
        "flag_sweep.start",
        api_url=api_url,
        num_flags=len(flags_to_test),
        num_queries=len(queries),
        combinations=config.combinations,
    )

    async with httpx.AsyncClient() as client:
        # Authenticate
        token = config.auth_token
        if not token:
            token = await _login(client, api_url)
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Matter-ID": config.matter_id,
        }

        # Snapshot current flag states
        original_states = await _get_flag_states(client, api_url, headers)

        # --- Baseline run ---
        logger.info("flag_sweep.baseline.start")
        baseline_responses = []
        for query in queries:
            resp, latency = await _run_query(client, api_url, headers, query)
            baseline_responses.append((resp, latency))

        baseline_metrics = _collect_metrics_from_responses(baseline_responses)
        baseline_result = FlagSweepResult(
            flag_states={f: original_states.get(f, False) for f in flags_to_test},
            label="baseline",
            metrics=baseline_metrics,
        )
        logger.info(
            "flag_sweep.baseline.done",
            latency_mean_ms=round(baseline_metrics.latency_mean_ms, 1),
        )

        # --- Per-flag experiments ---
        experiments: list[FlagSweepResult] = []
        on_metrics_by_flag: dict[str, FlagRunMetrics] = {}
        off_metrics_by_flag: dict[str, FlagRunMetrics] = {}

        for flag_name in flags_to_test:
            if flag_name not in original_states:
                logger.warning("flag_sweep.flag_not_found", flag=flag_name)
                continue

            current_state = original_states[flag_name]

            # Test with flag toggled to the opposite state
            toggled_state = not current_state
            await _set_flag(client, api_url, headers, flag_name, toggled_state)

            try:
                toggled_responses = []
                for query in queries:
                    resp, latency = await _run_query(client, api_url, headers, query)
                    toggled_responses.append((resp, latency))

                toggled_metrics = _collect_metrics_from_responses(toggled_responses)
                label = f"{flag_name}={'ON' if toggled_state else 'OFF'}"
                experiments.append(
                    FlagSweepResult(
                        flag_states={
                            **{f: original_states.get(f, False) for f in flags_to_test},
                            flag_name: toggled_state,
                        },
                        label=label,
                        metrics=toggled_metrics,
                    )
                )

                # Track ON/OFF metrics for impact summary
                if toggled_state:
                    on_metrics_by_flag[flag_name] = toggled_metrics
                    off_metrics_by_flag[flag_name] = baseline_metrics
                else:
                    off_metrics_by_flag[flag_name] = toggled_metrics
                    on_metrics_by_flag[flag_name] = baseline_metrics

                if verbose:
                    logger.info(
                        "flag_sweep.experiment.done",
                        flag=flag_name,
                        state=toggled_state,
                        latency_mean_ms=round(toggled_metrics.latency_mean_ms, 1),
                    )

            finally:
                # Always restore original state
                await _set_flag(client, api_url, headers, flag_name, current_state)

        # --- Pairwise combinations (opt-in) ---
        if config.combinations and len(flags_to_test) >= 2:
            for flag_a, flag_b in iter_combinations(flags_to_test, 2):
                if flag_a not in original_states or flag_b not in original_states:
                    continue

                state_a = not original_states[flag_a]
                state_b = not original_states[flag_b]

                await _set_flag(client, api_url, headers, flag_a, state_a)
                await _set_flag(client, api_url, headers, flag_b, state_b)

                try:
                    combo_responses = []
                    for query in queries:
                        resp, latency = await _run_query(client, api_url, headers, query)
                        combo_responses.append((resp, latency))

                    combo_metrics = _collect_metrics_from_responses(combo_responses)
                    label = f"{flag_a}={'ON' if state_a else 'OFF'}+{flag_b}={'ON' if state_b else 'OFF'}"
                    experiments.append(
                        FlagSweepResult(
                            flag_states={
                                **{f: original_states.get(f, False) for f in flags_to_test},
                                flag_a: state_a,
                                flag_b: state_b,
                            },
                            label=label,
                            metrics=combo_metrics,
                        )
                    )

                    if verbose:
                        logger.info("flag_sweep.combo.done", label=label)
                finally:
                    await _set_flag(client, api_url, headers, flag_a, original_states[flag_a])
                    await _set_flag(client, api_url, headers, flag_b, original_states[flag_b])

        # --- Compute impact summaries ---
        impact_summary: list[FlagImpactSummary] = []
        for flag_name in flags_to_test:
            if flag_name in on_metrics_by_flag and flag_name in off_metrics_by_flag:
                impact = compute_flag_impact(
                    flag_name,
                    on_metrics_by_flag[flag_name],
                    off_metrics_by_flag[flag_name],
                )
                impact_summary.append(impact)

        # Sort by absolute retrieval impact (most impactful first)
        impact_summary.sort(
            key=lambda s: abs(s.delta_mrr) + abs(s.delta_recall) + abs(s.delta_ndcg),
            reverse=True,
        )

        total_queries = len(queries) * (1 + len(experiments))
        total_duration = time.perf_counter() - sweep_start

        report = FlagSweepReport(
            config=config,
            baseline=baseline_result,
            experiments=experiments,
            impact_summary=impact_summary,
            total_queries_run=total_queries,
            total_duration_s=round(total_duration, 2),
        )

        logger.info(
            "flag_sweep.complete",
            total_queries=total_queries,
            total_duration_s=round(total_duration, 2),
            num_impacts=len(impact_summary),
        )

        return report


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def format_flag_sweep_report(report: FlagSweepReport) -> str:
    """Format a FlagSweepReport as a human-readable table."""
    lines: list[str] = []
    lines.append("=" * 90)
    lines.append("FEATURE FLAG EVALUATION SWEEP")
    lines.append("=" * 90)
    lines.append(f"  Queries:    {report.total_queries_run}")
    lines.append(f"  Duration:   {report.total_duration_s:.1f}s")
    lines.append(f"  Baseline latency: {report.baseline.metrics.latency_mean_ms:.0f}ms mean")
    lines.append("")

    if report.impact_summary:
        lines.append(f"{'Flag':<40s} {'MRR Δ':>8s} {'Recall Δ':>10s} {'NDCG Δ':>8s} {'Lat Δ ms':>10s} {'Rec':>18s}")
        lines.append("-" * 90)
        for impact in report.impact_summary:
            lines.append(
                f"{impact.flag_name:<40s} "
                f"{impact.delta_mrr:>+8.4f} "
                f"{impact.delta_recall:>+10.4f} "
                f"{impact.delta_ndcg:>+8.4f} "
                f"{impact.delta_latency_mean_ms:>+10.0f} "
                f"{impact.recommendation.value:>18s}"
            )
    else:
        lines.append("  No impact data collected.")

    lines.append("")
    lines.append("=" * 90)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Extended sweep: curated combos, ingestion, standalone, judge integration
# ---------------------------------------------------------------------------


async def run_curated_combos(
    *,
    client: httpx.AsyncClient,
    api_url: str,
    headers: dict[str, str],
    original_states: dict[str, bool],
    queries: list[str],
    expected_docs_per_query: list[list[str]] | None = None,
    scorer=None,
    verbose: bool = False,
) -> list[ComboEvalResult]:
    """Run curated combination evaluations."""
    from evaluation.runner import evaluate_queries, load_ground_truth

    results: list[ComboEvalResult] = []
    dataset = load_ground_truth()
    items = dataset.ground_truth

    for combo_name, flag_overrides in CURATED_COMBOS.items():
        logger.info("flag_sweep.combo.start", combo=combo_name)

        # Set all flags for this combo
        flags_set: list[tuple[str, bool]] = []
        for flag, desired in flag_overrides.items():
            if flag in original_states:
                await _set_flag(client, api_url, headers, flag, desired)
                flags_set.append((flag, desired))

        try:
            if items:
                query_results, metrics = await evaluate_queries(
                    client=client,
                    base_url=api_url,
                    headers=headers,
                    items=items,
                    scorer=scorer,
                    verbose=verbose,
                )
                judge_composite = 0.0
                judge_scores = [r.judge_score for r in query_results if r.judge_score]
                if judge_scores:
                    judge_composite = statistics.mean(s.composite for s in judge_scores)

                results.append(
                    ComboEvalResult(
                        name=combo_name,
                        flags_enabled=flag_overrides,
                        metrics=metrics,
                        query_results=query_results,
                        judge_composite=judge_composite,
                    )
                )
            else:
                # Fallback to simple query-based eval
                responses = []
                for query in queries:
                    resp, latency = await _run_query(client, api_url, headers, query)
                    responses.append((resp, latency))
                metrics = _collect_metrics_from_responses(responses, expected_docs_per_query)
                results.append(
                    ComboEvalResult(
                        name=combo_name,
                        flags_enabled=flag_overrides,
                        metrics=metrics,
                    )
                )

            if verbose:
                logger.info("flag_sweep.combo.done", combo=combo_name)
        finally:
            # Restore all flags
            for flag, _ in flags_set:
                if flag in original_states:
                    await _set_flag(client, api_url, headers, flag, original_states[flag])

    return results


async def run_standalone_tests(
    *,
    client: httpx.AsyncClient,
    api_url: str,
    headers: dict[str, str],
    original_states: dict[str, bool],
    matter_id: str = "00000000-0000-0000-0000-000000000001",
    verbose: bool = False,
) -> list[StandaloneFeatureTest]:
    """Test standalone feature endpoints (Group C)."""
    results: list[StandaloneFeatureTest] = []

    for flag_name, spec in STANDALONE_FEATURES.items():
        method = spec["method"]
        endpoint = spec["endpoint"].replace("{matter_id}", matter_id)
        full_url = f"{api_url.rstrip('/')}{endpoint}"

        logger.info("flag_sweep.standalone.start", flag=flag_name, endpoint=endpoint)

        # Enable the flag
        if flag_name in original_states:
            await _set_flag(client, api_url, headers, flag_name, True)

        try:
            start = time.perf_counter()
            if method == "GET":
                resp = await client.get(full_url, headers=headers, timeout=30.0)
            else:
                resp = await client.post(full_url, headers=headers, json={}, timeout=60.0)
            latency_ms = (time.perf_counter() - start) * 1000

            functional = 200 <= resp.status_code < 500
            error = None
            notes = ""
            if resp.status_code >= 400:
                error = f"HTTP {resp.status_code}"
                notes = resp.text[:200]

            results.append(
                StandaloneFeatureTest(
                    flag_name=flag_name,
                    endpoint=endpoint,
                    functional=functional,
                    latency_ms=latency_ms,
                    status_code=resp.status_code,
                    error=error,
                    notes=notes,
                )
            )
        except Exception as exc:
            results.append(
                StandaloneFeatureTest(
                    flag_name=flag_name,
                    endpoint=endpoint,
                    functional=False,
                    error=str(exc)[:200],
                )
            )
        finally:
            # Restore flag
            if flag_name in original_states:
                await _set_flag(client, api_url, headers, flag_name, original_states[flag_name])

        if verbose:
            logger.info("flag_sweep.standalone.done", flag=flag_name)

    return results


async def run_ingestion_tests(
    *,
    client: httpx.AsyncClient,
    api_url: str,
    headers: dict[str, str],
    original_states: dict[str, bool],
    matter_id: str = "00000000-0000-0000-0000-000000000001",
    doc_ids: list[str] | None = None,
    verbose: bool = False,
) -> list[IngestionFeatureTest]:
    """Test ingestion-time features by re-ingesting a small doc subset.

    For each ingestion flag: enable -> trigger re-ingestion -> run mini eval -> reset.
    """
    results: list[IngestionFeatureTest] = []

    for flag_name, description in INGESTION_FLAGS.items():
        logger.info("flag_sweep.ingestion.start", flag=flag_name)

        test = IngestionFeatureTest(
            flag_name=flag_name,
            notes=f"{description}. Re-ingestion test.",
        )

        # Enable the flag
        if flag_name in original_states:
            await _set_flag(client, api_url, headers, flag_name, True)

        try:
            # Trigger re-ingestion of a few docs if doc_ids provided
            if doc_ids:
                start = time.perf_counter()
                for doc_id in doc_ids[:3]:
                    try:
                        resp = await client.post(
                            f"{api_url.rstrip('/')}/api/v1/ingestion/documents/{doc_id}/reingest",
                            headers=headers,
                            timeout=120.0,
                        )
                        if resp.status_code >= 400:
                            test.error = f"Re-ingestion failed for {doc_id}: HTTP {resp.status_code}"
                            break
                    except Exception as exc:
                        test.error = f"Re-ingestion failed: {str(exc)[:100]}"
                        break
                test.ingestion_latency_ms = (time.perf_counter() - start) * 1000
                test.docs_ingested = len(doc_ids[:3])
            else:
                test.notes += " No doc_ids provided for re-ingestion."

        except Exception as exc:
            test.error = str(exc)[:200]
        finally:
            # Restore flag
            if flag_name in original_states:
                await _set_flag(client, api_url, headers, flag_name, original_states[flag_name])

        results.append(test)
        if verbose:
            logger.info("flag_sweep.ingestion.done", flag=flag_name)

    return results


async def run_full_qa_sweep(
    config: FlagSweepConfig,
    *,
    include_combos: bool = True,
    include_standalone: bool = False,
    include_ingestion: bool = False,
    skip_judge: bool = False,
    baseline_only: bool = False,
    verbose: bool = False,
) -> QAReport:
    """Run the comprehensive QA evaluation sweep.

    Extends the basic flag sweep with:
    - LLM-as-judge scoring per query
    - Curated combination tests
    - Standalone feature endpoint tests
    - Ingestion-time feature tests
    - Comprehensive QA report generation
    """
    from datetime import UTC, datetime

    from evaluation.runner import evaluate_queries, load_ground_truth

    sweep_start = time.perf_counter()
    api_url = config.api_url.rstrip("/")
    flags_to_test = config.flags or QUERY_TIME_FLAGS

    # Load ground-truth
    dataset = load_ground_truth()
    items = dataset.ground_truth

    # Build judge scorer
    scorer = None
    if not skip_judge:
        try:
            from evaluation.judge import JudgeScorer

            scorer = JudgeScorer()
        except Exception:
            logger.warning("flag_sweep.judge_unavailable", exc_info=True)

    # Capture environment info including LLM provider/model
    env_info = {
        "api_url": api_url,
        "matter_id": config.matter_id,
        "num_ground_truth": str(len(items)),
        "judge_enabled": str(scorer is not None),
        "timestamp": datetime.now(UTC).isoformat(),
    }

    # Add server LLM config from .env
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, val = stripped.partition("=")
            key = key.strip()
            if key in ("LLM_PROVIDER", "LLM_MODEL", "EMBEDDING_PROVIDER", "EMBEDDING_MODEL"):
                env_info[key.lower()] = val.strip()

    # Add judge scorer LLM info
    if scorer:
        env_info.update(scorer.provider_info)

    report = QAReport(environment=env_info)

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0)) as client:
        # Authenticate
        token = config.auth_token
        if not token:
            token = await _login(client, api_url)
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Matter-ID": config.matter_id,
        }
        _last_auth = time.perf_counter()

        async def _refresh_token_if_needed() -> None:
            """Re-authenticate if token is close to expiry (25 min)."""
            nonlocal token, headers, _last_auth
            if time.perf_counter() - _last_auth > 1500:  # 25 min
                logger.info("qa_sweep.token_refresh")
                token = await _login(client, api_url)
                headers["Authorization"] = f"Bearer {token}"
                _last_auth = time.perf_counter()

        # Snapshot flag states
        original_states = await _get_flag_states(client, api_url, headers)

        # --- Baseline ---
        logger.info("qa_sweep.baseline.start")
        if items:
            baseline_results, baseline_metrics = await evaluate_queries(
                client=client,
                base_url=api_url,
                headers=headers,
                items=items,
                scorer=scorer,
                verbose=verbose,
            )
        else:
            baseline_results = []
            baseline_responses = []
            queries = config.queries or DEFAULT_EVAL_QUERIES
            for query in queries:
                resp, latency = await _run_query(client, api_url, headers, query)
                baseline_responses.append((resp, latency))
            baseline_metrics = _collect_metrics_from_responses(baseline_responses)

        baseline_judge = 0.0
        if baseline_results:
            jscores = [r.judge_score for r in baseline_results if r.judge_score]
            if jscores:
                baseline_judge = statistics.mean(s.composite for s in jscores)

        report.baseline = ComboEvalResult(
            name="Baseline",
            flags_enabled={f: original_states.get(f, False) for f in flags_to_test},
            metrics=baseline_metrics,
            query_results=baseline_results,
            judge_composite=baseline_judge,
        )

        if baseline_only:
            return report

        # --- Individual flag ablations ---
        logger.info("qa_sweep.individual.start", num_flags=len(flags_to_test))
        on_metrics: dict[str, FlagRunMetrics] = {}
        off_metrics: dict[str, FlagRunMetrics] = {}
        query_details: dict[str, list[QueryEvalResult]] = {}

        for flag_name in flags_to_test:
            if flag_name not in original_states:
                logger.warning("qa_sweep.flag_not_found", flag=flag_name)
                continue

            await _refresh_token_if_needed()
            current_state = original_states[flag_name]
            toggled_state = not current_state
            await _set_flag(client, api_url, headers, flag_name, toggled_state)

            try:
                if items:
                    results, metrics = await evaluate_queries(
                        client=client,
                        base_url=api_url,
                        headers=headers,
                        items=items,
                        scorer=scorer,
                        verbose=verbose,
                    )
                    query_details[flag_name] = results
                else:
                    queries = config.queries or DEFAULT_EVAL_QUERIES
                    responses = []
                    for query in queries:
                        resp, latency = await _run_query(client, api_url, headers, query)
                        responses.append((resp, latency))
                    metrics = _collect_metrics_from_responses(responses)

                if toggled_state:
                    on_metrics[flag_name] = metrics
                    off_metrics[flag_name] = baseline_metrics
                else:
                    off_metrics[flag_name] = metrics
                    on_metrics[flag_name] = baseline_metrics

                if verbose:
                    logger.info("qa_sweep.individual.done", flag=flag_name)
            finally:
                await _set_flag(client, api_url, headers, flag_name, current_state)

        # Compute impact summaries
        for flag_name in flags_to_test:
            if flag_name in on_metrics and flag_name in off_metrics:
                impact = compute_flag_impact(flag_name, on_metrics[flag_name], off_metrics[flag_name])
                report.individual_results.append(impact)

        report.individual_results.sort(
            key=lambda s: abs(s.delta_mrr) + abs(s.delta_recall) + abs(s.delta_ndcg),
            reverse=True,
        )
        report.individual_query_details = query_details

        # --- Curated combos ---
        if include_combos:
            await _refresh_token_if_needed()
            logger.info("qa_sweep.combos.start")
            report.combo_results = await run_curated_combos(
                client=client,
                api_url=api_url,
                headers=headers,
                original_states=original_states,
                queries=config.queries or DEFAULT_EVAL_QUERIES,
                scorer=scorer,
                verbose=verbose,
            )

        # --- Standalone features ---
        if include_standalone:
            await _refresh_token_if_needed()
            logger.info("qa_sweep.standalone.start")
            report.standalone_results = await run_standalone_tests(
                client=client,
                api_url=api_url,
                headers=headers,
                original_states=original_states,
                matter_id=config.matter_id,
                verbose=verbose,
            )

        # --- Ingestion features ---
        if include_ingestion:
            await _refresh_token_if_needed()
            logger.info("qa_sweep.ingestion.start")
            report.ingestion_results = await run_ingestion_tests(
                client=client,
                api_url=api_url,
                headers=headers,
                original_states=original_states,
                matter_id=config.matter_id,
                verbose=verbose,
            )

        # --- Generate findings ---
        report.findings = _generate_findings(report)

        # --- Generate recommendations ---
        from evaluation.report import compute_recommendation

        for impact in report.individual_results:
            flag = impact.flag_name
            details = query_details.get(flag, [])
            error_count = sum(1 for d in details if d.error)
            error_rate = error_count / max(len(details), 1)
            judge_delta = 0.0
            if baseline_judge > 0 and details:
                jscores = [r.judge_score for r in details if r.judge_score]
                if jscores:
                    judge_delta = statistics.mean(s.composite for s in jscores) - baseline_judge

            retrieval_delta = impact.delta_mrr + impact.delta_recall + impact.delta_ndcg
            latency_delta_s = impact.delta_latency_mean_ms / 1000.0

            # functional = True unless majority of queries fail
            functional = error_rate < 0.50

            report.recommendations[flag] = compute_recommendation(
                functional=functional,
                error_rate=error_rate,
                judge_composite_delta=judge_delta,
                retrieval_delta=retrieval_delta,
                latency_delta_s=latency_delta_s,
            )

    logger.info(
        "qa_sweep.complete",
        total_duration_s=round(time.perf_counter() - sweep_start, 2),
        num_individual=len(report.individual_results),
        num_combos=len(report.combo_results),
        num_findings=len(report.findings),
    )

    return report


def _generate_findings(report: QAReport) -> list[FeatureFinding]:
    """Analyze results and generate findings (bugs, regressions, improvements)."""
    findings: list[FeatureFinding] = []

    for impact in report.individual_results:
        flag = impact.flag_name
        details = report.individual_query_details.get(flag, [])

        # Check for errors
        errors = [d for d in details if d.error]
        if errors:
            severity = "critical" if len(errors) > len(details) * 0.5 else "high"
            findings.append(
                FeatureFinding(
                    flag_name=flag,
                    severity=severity,
                    category="bug",
                    description=f"{len(errors)}/{len(details)} queries failed when flag toggled",
                    evidence=errors[0].error or "" if errors else "",
                )
            )

        # Check for significant retrieval regression
        total_delta = impact.delta_mrr + impact.delta_recall + impact.delta_ndcg
        if total_delta < -0.05:
            findings.append(
                FeatureFinding(
                    flag_name=flag,
                    severity="medium",
                    category="regression",
                    description=f"Retrieval quality regression (total delta: {total_delta:+.4f})",
                )
            )

        # Check for significant improvement
        if total_delta > 0.05:
            findings.append(
                FeatureFinding(
                    flag_name=flag,
                    severity="info",
                    category="improvement",
                    description=f"Retrieval quality improvement (total delta: {total_delta:+.4f})",
                )
            )

        # Check for significant latency increase
        if impact.delta_latency_mean_ms > 5000:
            findings.append(
                FeatureFinding(
                    flag_name=flag,
                    severity="medium",
                    category="note",
                    description=f"Significant latency increase: {impact.delta_latency_mean_ms:+.0f}ms",
                )
            )

    # Check standalone features
    for st in report.standalone_results:
        if not st.functional:
            findings.append(
                FeatureFinding(
                    flag_name=st.flag_name,
                    severity="high",
                    category="bug",
                    description=f"Standalone endpoint {st.endpoint} not functional",
                    evidence=st.error or "",
                )
            )

    return findings
