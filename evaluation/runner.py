"""Evaluation runner: orchestrates dry-run and full evaluation modes."""

from __future__ import annotations

import structlog

from evaluation.metrics.retrieval import compute_retrieval_metrics
from evaluation.schemas import (
    CitationMetrics,
    EvaluationMode,
    EvaluationResult,
    GenerationMetrics,
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
) -> EvaluationResult:
    """Execute a full evaluation against live infrastructure.

    Requires running Qdrant, PostgreSQL, and configured LLM provider.
    This is the post-M9 path — not part of the M9 quality gate.
    """
    logger.info("eval.full.start", skip_ragas=skip_ragas)

    # TODO: Implement full evaluation pipeline
    # 1. Load real dataset from evaluation/data/
    # 2. Run retrieval in 3 modes (dense, sparse, hybrid)
    # 3. Run full query pipeline via get_query_graph().ainvoke()
    # 4. Extract citations, compute metrics
    # 5. Run RAGAS (unless skip_ragas)
    # 6. Process adversarial set
    # 7. Process LegalBench set
    # 8. Check quality gates

    raise NotImplementedError(
        "Full evaluation mode requires live infrastructure. " "Use --dry-run for the M9 quality gate."
    )
