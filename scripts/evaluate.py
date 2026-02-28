#!/usr/bin/env python3
"""NEXUS Evaluation CLI.

Usage:
    python scripts/evaluate.py --dry-run           # Synthetic data, no infra needed
    python scripts/evaluate.py --output results.json  # Full run, save results
    python scripts/evaluate.py --skip-ragas        # Full run, skip RAGAS metrics
    python scripts/evaluate.py --verbose           # Extra logging
    python scripts/evaluate.py --dry-run --config-override RETRIEVAL_TEXT_LIMIT=30
    python scripts/evaluate.py --dry-run --tune    # Run predefined tuning sweep
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure the project root is on sys.path so evaluation/ is importable
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from evaluation.runner import run_dry  # noqa: E402
from evaluation.schemas import TuningConfig  # noqa: E402
from evaluation.tuning import run_tuning_comparison  # noqa: E402


def _parse_config_overrides(raw: list[str] | None) -> dict[str, str]:
    """Parse KEY=VALUE pairs into a dict."""
    overrides: dict[str, str] = {}
    if not raw:
        return overrides
    for item in raw:
        if "=" not in item:
            print(f"Warning: ignoring malformed override '{item}' (expected KEY=VALUE)", file=sys.stderr)
            continue
        key, _, value = item.partition("=")
        overrides[key.strip()] = value.strip()
    return overrides


def _run_tuning_sweep(verbose: bool = False) -> int:
    """Run predefined tuning experiments and print report."""
    print("Running M15 tuning sweep (dry-run mode)...\n")

    # Compute baseline
    baseline_result = run_dry(verbose=verbose)
    baseline_metrics = baseline_result.retrieval[0] if baseline_result.retrieval else None

    if baseline_metrics is None:
        print("Error: baseline produced no retrieval metrics", file=sys.stderr)
        return 1

    # --- Experiment 1: Reranker impact ---
    print("=" * 60)
    print("Experiment 1: Reranker Impact")
    print("=" * 60)
    reranker_configs = [
        TuningConfig(name="reranker-on", overrides={"ENABLE_RERANKER": "true"}),
        TuningConfig(name="reranker-on-top20", overrides={"ENABLE_RERANKER": "true", "RERANKER_TOP_N": "20"}),
    ]
    reranker_report = run_tuning_comparison(reranker_configs, baseline_metrics, verbose=verbose)
    print(f"  Baseline MRR@10:  {baseline_metrics.mrr_at_10:.4f}")
    for comp in reranker_report.comparisons:
        print(f"  {comp.config_name:20s}  MRR@10: {comp.metrics.mrr_at_10:.4f}  (delta: {comp.delta_mrr:+.4f})")
    print(f"  Best: {reranker_report.best_config}")
    print(f"  {reranker_report.recommendation}\n")

    # --- Experiment 2: Prefetch multiplier sweep ---
    print("=" * 60)
    print("Experiment 2: Prefetch Multiplier Sweep")
    print("=" * 60)
    prefetch_configs = [
        TuningConfig(name="prefetch-2x", overrides={"RETRIEVAL_PREFETCH_MULTIPLIER": "2"}),
        TuningConfig(name="prefetch-3x", overrides={"RETRIEVAL_PREFETCH_MULTIPLIER": "3"}),
        TuningConfig(name="prefetch-4x", overrides={"RETRIEVAL_PREFETCH_MULTIPLIER": "4"}),
    ]
    prefetch_report = run_tuning_comparison(prefetch_configs, baseline_metrics, verbose=verbose)
    print(f"  Baseline NDCG@10: {baseline_metrics.ndcg_at_10:.4f}")
    for comp in prefetch_report.comparisons:
        print(f"  {comp.config_name:20s}  NDCG@10: {comp.metrics.ndcg_at_10:.4f}  (delta: {comp.delta_ndcg:+.4f})")
    print(f"  Best: {prefetch_report.best_config}")
    print(f"  {prefetch_report.recommendation}\n")

    # --- Experiment 3: Entity threshold sweep ---
    print("=" * 60)
    print("Experiment 3: Entity Threshold Sweep")
    print("=" * 60)
    threshold_configs = [
        TuningConfig(name="threshold-0.3", overrides={"QUERY_ENTITY_THRESHOLD": "0.3"}),
        TuningConfig(name="threshold-0.4", overrides={"QUERY_ENTITY_THRESHOLD": "0.4"}),
        TuningConfig(name="threshold-0.5", overrides={"QUERY_ENTITY_THRESHOLD": "0.5"}),
        TuningConfig(name="threshold-0.6", overrides={"QUERY_ENTITY_THRESHOLD": "0.6"}),
    ]
    threshold_report = run_tuning_comparison(threshold_configs, baseline_metrics, verbose=verbose)
    print(f"  Baseline Recall@10: {baseline_metrics.recall_at_10:.4f}")
    for comp in threshold_report.comparisons:
        print(
            f"  {comp.config_name:20s}  Recall@10: {comp.metrics.recall_at_10:.4f}  "
            f"(delta: {comp.delta_recall:+.4f})"
        )
    print(f"  Best: {threshold_report.best_config}")
    print(f"  {threshold_report.recommendation}\n")

    # --- Summary ---
    print("=" * 60)
    print("Tuning Summary")
    print("=" * 60)
    all_reports = [
        ("Reranker", reranker_report),
        ("Prefetch", prefetch_report),
        ("Entity Threshold", threshold_report),
    ]
    for name, report in all_reports:
        print(f"  {name:20s} → best: {report.best_config}")

    # Output machine-readable summary
    summary = {
        "reranker": reranker_report.model_dump(mode="json"),
        "prefetch": prefetch_report.model_dump(mode="json"),
        "entity_threshold": threshold_report.model_dump(mode="json"),
    }
    print(f"\n{json.dumps(summary, indent=2)}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="NEXUS Evaluation Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run with synthetic data (no infrastructure required)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to write JSON results",
    )
    parser.add_argument(
        "--skip-ragas",
        action="store_true",
        help="Skip RAGAS metrics (full mode only)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--config-override",
        action="append",
        metavar="KEY=VALUE",
        help="Override a config setting (repeatable, e.g., --config-override RETRIEVAL_TEXT_LIMIT=30)",
    )
    parser.add_argument(
        "--tune",
        action="store_true",
        help="Run predefined tuning experiments (reranker, prefetch multiplier, entity threshold)",
    )

    args = parser.parse_args()

    # Tuning sweep mode
    if args.tune:
        return _run_tuning_sweep(verbose=args.verbose)

    overrides = _parse_config_overrides(args.config_override)

    if args.dry_run:
        result = run_dry(verbose=args.verbose, config_overrides=overrides or None)
    else:
        # Full mode requires asyncio
        import asyncio

        from evaluation.runner import run_full

        try:
            result = asyncio.run(run_full(skip_ragas=args.skip_ragas, verbose=args.verbose))
        except NotImplementedError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    # Output results
    result_json = result.model_dump_json(indent=2)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(result_json)
        print(f"Results written to {output_path}")
    else:
        print(result_json)

    # Exit code based on quality gates
    if not result.passed:
        print(f"\nQuality gate FAILED: {result.gate_failures}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
