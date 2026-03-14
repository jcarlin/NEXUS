"""Feature flag evaluation sweep runner.

Toggles feature flags against a live NEXUS instance and measures the impact
on retrieval quality, citation accuracy, and latency.  Requires Docker
services (Qdrant, PostgreSQL, Neo4j, MinIO, Redis) and a populated matter.

Usage:
    python scripts/evaluate.py --flag-sweep --api-url http://localhost:8000
"""

from __future__ import annotations

import statistics
import time
from itertools import combinations as iter_combinations

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
    FlagImpactSummary,
    FlagRecommendation,
    FlagRunMetrics,
    FlagSweepConfig,
    FlagSweepReport,
    FlagSweepResult,
    RetrievalMetrics,
    RetrievalMode,
)

logger = structlog.get_logger(__name__)

# Flags that affect query-time behaviour (retrieval, generation, citation).
# Ingestion-only and integration flags are excluded — they require re-ingestion
# or app restart, so sweeping them at query time is meaningless.
QUERY_TIME_FLAGS: list[str] = [
    "enable_reranker",
    "enable_sparse_embeddings",
    "enable_retrieval_grading",
    "enable_agentic_pipeline",
    "enable_citation_verification",
    "enable_multi_query_expansion",
    "enable_text_to_cypher",
    "enable_prompt_routing",
    "enable_question_decomposition",
    "enable_hyde",
    "enable_self_reflection",
    "enable_text_to_sql",
    "enable_production_quality_monitoring",
]

DEFAULT_EVAL_QUERIES: list[str] = [
    "What are the key allegations in the complaint?",
    "When was the master service agreement executed?",
    "Describe the timeline of communications between the CEO and CFO regarding the merger.",
    "Compare the indemnification clauses across documents.",
    "What discovery issues were raised in the custodian files?",
]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


async def _login(client: httpx.AsyncClient, api_url: str) -> str:
    """Login as the seed admin and return a JWT token."""
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
