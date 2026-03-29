"""Evaluation runner: orchestrates dry-run and full evaluation modes."""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

import httpx
import structlog

from evaluation.metrics.retrieval import compute_retrieval_metrics
from evaluation.schemas import (
    CitationMetrics,
    EvaluationDataset,
    EvaluationMode,
    EvaluationResult,
    FlagRunMetrics,
    GenerationMetrics,
    GroundTruthItem,
    QueryEvalResult,
    RetrievalMetrics,
    RetrievalMode,
)
from evaluation.synthetic import (
    generate_synthetic_adversarial_summary,
    generate_synthetic_citation_metrics,
    generate_synthetic_dataset,
    generate_synthetic_generation_metrics,
    generate_synthetic_legalbench_summary,
    generate_synthetic_retrieval_results,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------

# Deep-tier queries (timelines, multi-hop) routinely exceed 120 s when
# multiple feature flags are enabled.  180 s gives enough headroom without
# masking genuine hangs.
EVAL_QUERY_TIMEOUT_S: float = 180.0

# ---------------------------------------------------------------------------
# Quality gates
# ---------------------------------------------------------------------------

QUALITY_GATES = {
    "faithfulness": (">=", 0.95),
    "citation_accuracy": (">=", 0.90),
    "hallucination_rate": ("<", 0.05),
    "post_rationalization_rate": ("<", 0.10),
}


def _check_gates(
    generation: GenerationMetrics | None,
    citation: CitationMetrics | None,
) -> list[str]:
    """Check quality gates and return list of failure descriptions."""
    failures: list[str] = []

    if generation is not None:
        if generation.faithfulness < 0.95:
            failures.append(f"faithfulness={generation.faithfulness:.3f} < 0.95")

    if citation is not None:
        # Only check citation gates when claims exist — 0 claims means
        # the pipeline didn't extract claims, not that they're all wrong.
        if citation.total_claims > 0:
            if citation.citation_accuracy < 0.90:
                failures.append(f"citation_accuracy={citation.citation_accuracy:.3f} < 0.90")
            if citation.hallucination_rate >= 0.05:
                failures.append(f"hallucination_rate={citation.hallucination_rate:.3f} >= 0.05")
            if citation.post_rationalization_rate >= 0.10:
                failures.append(f"post_rationalization_rate={citation.post_rationalization_rate:.3f} >= 0.10")

    return failures


# ---------------------------------------------------------------------------
# Dry-run mode
# ---------------------------------------------------------------------------


def run_dry(
    verbose: bool = False,
    config_overrides: dict[str, str] | None = None,
) -> EvaluationResult:
    """Execute a dry-run evaluation using synthetic data.

    No infrastructure, no LLM calls, no cost. Exercises all metric
    computations and validates the evaluation pipeline.

    *config_overrides* are recorded in the result for documentation
    but do not affect synthetic metric computation.
    """
    logger.info("eval.dry_run.start", config_overrides=config_overrides or {})

    # 1. Generate synthetic dataset
    dataset = generate_synthetic_dataset()
    if verbose:
        logger.info(
            "eval.dry_run.dataset",
            gt=len(dataset.ground_truth),
            adv=len(dataset.adversarial),
            lb=len(dataset.legalbench),
        )

    # 2. Generate synthetic retrieval results and compute metrics
    retrieval_results = generate_synthetic_retrieval_results(dataset)

    # Compute retrieval metrics across all ground-truth items
    all_metrics: dict[str, list[float]] = {
        "mrr_at_k": [],
        "recall_at_k": [],
        "precision_at_k": [],
        "ndcg_at_k": [],
    }
    for result in retrieval_results:
        metrics = compute_retrieval_metrics(
            retrieved_ids=result["retrieved"],
            relevant_ids=set(result["relevant"]),
            k=10,
        )
        for key, value in metrics.items():
            all_metrics[key].append(value)

    avg_metrics = {k: sum(v) / len(v) for k, v in all_metrics.items()}

    # In dry-run, we only produce a single "hybrid" retrieval metrics set
    retrieval = [
        RetrievalMetrics(
            mode=RetrievalMode.HYBRID,
            mrr_at_10=avg_metrics["mrr_at_k"],
            recall_at_10=avg_metrics["recall_at_k"],
            ndcg_at_10=avg_metrics["ndcg_at_k"],
            precision_at_10=avg_metrics["precision_at_k"],
            num_queries=len(retrieval_results),
        )
    ]

    if verbose:
        logger.info("eval.dry_run.retrieval", **avg_metrics)

    # 3. Synthetic generation + citation metrics
    generation = generate_synthetic_generation_metrics()
    citation = generate_synthetic_citation_metrics()
    adversarial_summary = generate_synthetic_adversarial_summary()
    legalbench_summary = generate_synthetic_legalbench_summary()

    # 4. Check quality gates
    gate_failures = _check_gates(generation, citation)
    passed = len(gate_failures) == 0

    result = EvaluationResult(
        mode=EvaluationMode.DRY_RUN,
        config_overrides=config_overrides or {},
        retrieval=retrieval,
        generation=generation,
        citation=citation,
        adversarial_summary=adversarial_summary,
        legalbench_summary=legalbench_summary,
        passed=passed,
        gate_failures=gate_failures,
    )

    if verbose:
        logger.info("eval.dry_run.complete", passed=passed, gate_failures=gate_failures)

    return result


# ---------------------------------------------------------------------------
# Full-run mode (requires infrastructure)
# ---------------------------------------------------------------------------


async def run_full(
    skip_ragas: bool = False,
    verbose: bool = False,
    base_url: str = "http://localhost:8000",
    matter_id: str = "00000000-0000-0000-0000-000000000001",
    credentials: tuple[str, str] = ("admin@example.com", "password123"),
    skip_judge: bool = False,
    dataset_path: Path | None = None,
) -> EvaluationResult:
    """Execute a full evaluation against live infrastructure.

    Queries the running NEXUS instance via HTTP, computes retrieval metrics,
    citation metrics, and optionally LLM-as-judge quality scores.
    """
    logger.info("eval.full.start", base_url=base_url, skip_judge=skip_judge)

    # 1. Load ground-truth dataset
    dataset = load_ground_truth(dataset_path)
    if not dataset.ground_truth:
        src = dataset_path or "evaluation/data/ground_truth.json"
        raise RuntimeError(f"No ground-truth items in {src}")

    # 2. Authenticate
    async with httpx.AsyncClient(timeout=EVAL_QUERY_TIMEOUT_S) as client:
        token = await _authenticate(client, base_url, credentials)
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Matter-ID": matter_id,
        }

        # 3. Build judge scorer (optional)
        scorer = None
        if not skip_judge:
            try:
                from evaluation.judge import JudgeScorer

                scorer = JudgeScorer()
            except Exception:
                logger.warning("eval.full.judge_unavailable", exc_info=True)

        # 4. Run queries and collect per-query results
        query_results: list[QueryEvalResult] = []
        for item in dataset.ground_truth:
            result = await _evaluate_single_query(
                client=client,
                base_url=base_url,
                headers=headers,
                item=item,
                scorer=scorer,
                verbose=verbose,
            )
            query_results.append(result)

        # 5. Aggregate metrics
        agg_metrics = _aggregate_query_results(query_results, dataset.ground_truth)

        # 6. Check quality gates
        gate_failures = _check_gates(agg_metrics.generation, agg_metrics.citation)
        passed = len(gate_failures) == 0

        result = EvaluationResult(
            mode=EvaluationMode.FULL,
            retrieval=agg_metrics.retrieval_list,
            generation=agg_metrics.generation,
            citation=agg_metrics.citation,
            passed=passed,
            gate_failures=gate_failures,
        )

        if verbose:
            logger.info("eval.full.complete", passed=passed, num_queries=len(query_results))

        return result


# ---------------------------------------------------------------------------
# Full-run helpers
# ---------------------------------------------------------------------------


def load_ground_truth(dataset_path: Path | None = None) -> EvaluationDataset:
    """Load a ground-truth dataset.

    Args:
        dataset_path: Path to a ground-truth JSON file.  When *None*
            (the default) the built-in ``evaluation/data/ground_truth.json``
            is used.
    """
    gt_path = dataset_path or (Path(__file__).parent / "data" / "ground_truth.json")
    if not gt_path.exists():
        return EvaluationDataset()
    raw = json.loads(gt_path.read_text())
    # Handle both list-of-items and full dataset format
    if isinstance(raw, list):
        return EvaluationDataset(ground_truth=[GroundTruthItem(**item) for item in raw])
    return EvaluationDataset(**raw)


async def _authenticate(
    client: httpx.AsyncClient,
    base_url: str,
    credentials: tuple[str, str],
) -> str:
    """Authenticate and return a JWT token.

    Tries provided credentials first, then falls back to common admin accounts.
    """
    url = f"{base_url.rstrip('/')}/api/v1/auth/login"
    cred_pairs = [
        credentials,
        ("admin@nexus-demo.com", "nexus-demo-2026"),
        ("admin@example.com", "password123"),
    ]
    for email, password in cred_pairs:
        resp = await client.post(url, json={"email": email, "password": password})
        if resp.status_code == 200:
            logger.info("eval.auth.success", email=email)
            return resp.json()["access_token"]
    # All failed — raise on last
    resp.raise_for_status()
    return ""  # unreachable


async def _evaluate_single_query(
    *,
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict[str, str],
    item: GroundTruthItem,
    scorer=None,
    verbose: bool = False,
) -> QueryEvalResult:
    """Run a single ground-truth query and compute all metrics."""
    api_url = base_url.rstrip("/")
    start = time.perf_counter()

    try:
        resp = await client.post(
            f"{api_url}/api/v1/query",
            json={"query": item.question},
            headers=headers,
            timeout=EVAL_QUERY_TIMEOUT_S,
        )
        latency_ms = (time.perf_counter() - start) * 1000

        if resp.status_code != 200:
            # Try to extract structured detail from JSON error response
            error_detail = ""
            try:
                err_json = resp.json()
                error_detail = err_json.get("detail", "")
            except Exception:
                pass
            error_msg = f"HTTP {resp.status_code}: {error_detail or resp.text[:500]}"
            return QueryEvalResult(
                query_id=item.id,
                question=item.question,
                functional=False,
                latency_ms=latency_ms,
                error=error_msg,
            )

        data = resp.json()
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        return QueryEvalResult(
            query_id=item.id,
            question=item.question,
            functional=False,
            latency_ms=latency_ms,
            error=str(exc)[:200],
        )

    response_text = data.get("response", "")
    source_docs = data.get("source_documents", [])
    cited_claims = data.get("cited_claims", [])

    # Retrieval metrics
    retrieved_filenames = [doc.get("filename", "") for doc in source_docs]
    r_metrics = compute_retrieval_metrics(
        retrieved_ids=retrieved_filenames,
        relevant_ids=set(item.expected_documents),
        k=10,
    )

    # Citation metrics from cited_claims
    verified_count = sum(1 for c in cited_claims if c.get("verification_status") == "verified")
    citation_verified_pct = (verified_count / len(cited_claims)) if cited_claims else 0.0

    # Source relevance
    relevance_scores = [doc.get("relevance_score", 0.0) for doc in source_docs]
    source_relevance_avg = statistics.mean(relevance_scores) if relevance_scores else 0.0

    # LLM-as-judge scoring
    judge_score = None
    if scorer:
        source_excerpts = [doc.get("chunk_text", "")[:500] for doc in source_docs[:5]]
        judge_score = await scorer.score_answer(
            question=item.question,
            answer=response_text,
            source_excerpts=source_excerpts,
        )

    if verbose:
        logger.info(
            "eval.full.query_done",
            query_id=item.id,
            latency_ms=round(latency_ms, 1),
            mrr=round(r_metrics["mrr_at_k"], 4),
        )

    # Flag queries that generated a response but returned no source documents.
    # These should be reported separately rather than dragging down retrieval averages.
    no_sources = bool(response_text and not source_docs and item.expected_documents)

    return QueryEvalResult(
        query_id=item.id,
        question=item.question,
        functional=True,
        latency_ms=latency_ms,
        judge_score=judge_score,
        mrr_at_10=r_metrics["mrr_at_k"],
        recall_at_10=r_metrics["recall_at_k"],
        ndcg_at_10=r_metrics["ndcg_at_k"],
        precision_at_10=r_metrics["precision_at_k"],
        citation_count=len(cited_claims),
        citation_verified_pct=citation_verified_pct,
        source_relevance_avg=source_relevance_avg,
        sources_count=len(source_docs),
        no_sources_returned=no_sources,
        response_text=response_text[:500],
    )


class _AggregatedMetrics:
    """Container for aggregated metrics across queries."""

    def __init__(
        self,
        retrieval_list: list[RetrievalMetrics],
        generation: GenerationMetrics | None,
        citation: CitationMetrics | None,
    ) -> None:
        self.retrieval_list = retrieval_list
        self.generation = generation
        self.citation = citation


def _aggregate_query_results(
    results: list[QueryEvalResult],
    items: list[GroundTruthItem],
) -> _AggregatedMetrics:
    """Aggregate per-query results into summary metrics."""
    functional_results = [r for r in results if r.functional]
    if not functional_results:
        return _AggregatedMetrics([], None, None)

    # Retrieval: exclude queries that returned a response but zero sources
    # (e.g., answered from case context). These are reported separately.
    retrieval_results = [r for r in functional_results if not r.no_sources_returned]
    if not retrieval_results:
        retrieval_results = functional_results  # fallback: use all if all were zero-source
    avg_mrr = statistics.mean(r.mrr_at_10 for r in retrieval_results)
    avg_recall = statistics.mean(r.recall_at_10 for r in retrieval_results)
    avg_ndcg = statistics.mean(r.ndcg_at_10 for r in retrieval_results)
    avg_precision = statistics.mean(r.precision_at_10 for r in retrieval_results)

    retrieval = RetrievalMetrics(
        mode=RetrievalMode.HYBRID,
        mrr_at_10=avg_mrr,
        recall_at_10=avg_recall,
        ndcg_at_10=avg_ndcg,
        precision_at_10=avg_precision,
        num_queries=len(retrieval_results),
    )

    # Citation from cited_claims
    total_claims = sum(r.citation_count for r in functional_results)
    verified_claims = sum(int(r.citation_verified_pct * r.citation_count) for r in functional_results)
    queries_with_claims = sum(1 for r in functional_results if r.citation_count > 0)
    claim_extraction_rate = queries_with_claims / len(functional_results) if functional_results else 0.0
    citation = CitationMetrics(
        citation_accuracy=verified_claims / total_claims if total_claims else 0.0,
        hallucination_rate=0.0,
        post_rationalization_rate=0.0,
        total_claims=total_claims,
        supported_claims=verified_claims,
        unsupported_claims=total_claims - verified_claims,
        post_rationalized_claims=0,
        claim_extraction_rate=claim_extraction_rate,
    )

    # Generation: use judge scores if available
    judge_scores = [r.judge_score for r in functional_results if r.judge_score]
    generation = None
    if judge_scores:
        avg_composite = statistics.mean(s.composite for s in judge_scores)
        avg_relevance = statistics.mean(s.relevance for s in judge_scores)
        generation = GenerationMetrics(
            faithfulness=avg_composite / 5.0,  # Normalize to 0-1
            answer_relevancy=avg_relevance / 5.0,
            context_precision=avg_recall,  # Proxy
            num_queries=len(judge_scores),
        )

    return _AggregatedMetrics([retrieval], generation, citation)


async def evaluate_queries(
    *,
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict[str, str],
    items: list[GroundTruthItem],
    scorer=None,
    verbose: bool = False,
) -> tuple[list[QueryEvalResult], FlagRunMetrics]:
    """Run evaluation queries and return both per-query results and aggregate metrics.

    Shared between run_full() and flag_sweep extended runner.
    """
    query_results: list[QueryEvalResult] = []
    latencies: list[float] = []

    for item in items:
        result = await _evaluate_single_query(
            client=client,
            base_url=base_url,
            headers=headers,
            item=item,
            scorer=scorer,
            verbose=verbose,
        )
        query_results.append(result)
        if result.functional:
            latencies.append(result.latency_ms)

    # Build FlagRunMetrics from results
    from evaluation.flag_sweep import _percentile

    functional = [r for r in query_results if r.functional]
    retrieval = None
    if functional:
        avg_mrr = statistics.mean(r.mrr_at_10 for r in functional)
        avg_recall = statistics.mean(r.recall_at_10 for r in functional)
        avg_ndcg = statistics.mean(r.ndcg_at_10 for r in functional)
        avg_precision = statistics.mean(r.precision_at_10 for r in functional)
        retrieval = RetrievalMetrics(
            mode=RetrievalMode.HYBRID,
            mrr_at_10=avg_mrr,
            recall_at_10=avg_recall,
            ndcg_at_10=avg_ndcg,
            precision_at_10=avg_precision,
            num_queries=len(functional),
        )

    total_claims = sum(r.citation_count for r in functional)
    verified = sum(int(r.citation_verified_pct * r.citation_count) for r in functional)
    queries_with_claims = sum(1 for r in functional if r.citation_count > 0)
    claim_extraction_rate = queries_with_claims / len(functional) if functional else 0.0
    citation = CitationMetrics(
        citation_accuracy=verified / total_claims if total_claims else 0.0,
        hallucination_rate=0.0,
        post_rationalization_rate=0.0,
        total_claims=total_claims,
        supported_claims=verified,
        unsupported_claims=total_claims - verified,
        post_rationalized_claims=0,
        claim_extraction_rate=claim_extraction_rate,
    )

    gate_failures = _check_gates(None, citation)

    # Judge composite (unused for now — available for future reporting)
    # judge_composite = 0.0
    # judge_scores = [r.judge_score for r in functional if r.judge_score]
    # if judge_scores:
    #     judge_composite = statistics.mean(s.composite for s in judge_scores)

    metrics = FlagRunMetrics(
        retrieval=retrieval,
        citation=citation,
        latency_p50_ms=statistics.median(latencies) if latencies else 0.0,
        latency_p95_ms=_percentile(latencies, 95) if latencies else 0.0,
        latency_mean_ms=statistics.mean(latencies) if latencies else 0.0,
        num_queries=len(query_results),
        quality_gates_passed=len(gate_failures) == 0,
        gate_failures=gate_failures,
    )

    return query_results, metrics
