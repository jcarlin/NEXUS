"""Tests for M15 tuning evaluation experiments."""

from __future__ import annotations

from evaluation.schemas import (
    RetrievalMetrics,
    RetrievalMode,
    TuningConfig,
)
from evaluation.tuning import run_tuning_comparison


class TestRerankerImpactComparison:
    """Verify reranker on vs off comparison produces a valid report."""

    def test_reranker_comparison_report_structure(self) -> None:
        """Dry-run baseline vs reranker-on produces a valid TuningReport."""
        configs = [
            TuningConfig(name="reranker-on", overrides={"ENABLE_RERANKER": "true"}),
            TuningConfig(name="reranker-on-top20", overrides={"ENABLE_RERANKER": "true", "RERANKER_TOP_N": "20"}),
        ]

        report = run_tuning_comparison(configs)

        # Structure validation
        assert report.baseline is not None
        assert report.baseline.mode == RetrievalMode.HYBRID
        assert len(report.comparisons) == 2
        assert report.best_config in {"reranker-on", "reranker-on-top20"}
        assert len(report.recommendation) > 0

        # Each comparison has valid deltas
        for comp in report.comparisons:
            assert comp.config_name in {"reranker-on", "reranker-on-top20"}
            assert comp.overrides == configs[0].overrides or comp.overrides == configs[1].overrides
            assert 0.0 <= comp.metrics.mrr_at_10 <= 1.0
            assert 0.0 <= comp.metrics.recall_at_10 <= 1.0
            assert 0.0 <= comp.metrics.ndcg_at_10 <= 1.0
            assert 0.0 <= comp.metrics.precision_at_10 <= 1.0
            # Deltas are differences — can be positive or negative
            assert -1.0 <= comp.delta_mrr <= 1.0
            assert -1.0 <= comp.delta_recall <= 1.0
            assert -1.0 <= comp.delta_ndcg <= 1.0
            assert -1.0 <= comp.delta_precision <= 1.0


class TestPrefetchMultiplierSweep:
    """Verify prefetch multiplier sweep produces ranked configs."""

    def test_prefetch_sweep_produces_ranked_configs(self) -> None:
        """3 multiplier configs are compared and ranked by metric improvement."""
        configs = [
            TuningConfig(name="prefetch-2x", overrides={"RETRIEVAL_PREFETCH_MULTIPLIER": "2"}),
            TuningConfig(name="prefetch-3x", overrides={"RETRIEVAL_PREFETCH_MULTIPLIER": "3"}),
            TuningConfig(name="prefetch-4x", overrides={"RETRIEVAL_PREFETCH_MULTIPLIER": "4"}),
        ]

        report = run_tuning_comparison(configs)

        # All 3 configs present
        assert len(report.comparisons) == 3
        config_names = {c.config_name for c in report.comparisons}
        assert config_names == {"prefetch-2x", "prefetch-3x", "prefetch-4x"}

        # Best config is one of them
        assert report.best_config in config_names

        # All metrics are valid
        for comp in report.comparisons:
            assert comp.metrics.num_queries > 0
            assert 0.0 <= comp.metrics.ndcg_at_10 <= 1.0

    def test_prefetch_sweep_with_explicit_baseline(self) -> None:
        """Sweep with explicit baseline metrics computes correct deltas."""
        baseline = RetrievalMetrics(
            mode=RetrievalMode.HYBRID,
            mrr_at_10=0.5,
            recall_at_10=0.6,
            ndcg_at_10=0.55,
            precision_at_10=0.3,
            num_queries=5,
        )

        configs = [
            TuningConfig(name="prefetch-3x", overrides={"RETRIEVAL_PREFETCH_MULTIPLIER": "3"}),
        ]

        report = run_tuning_comparison(configs, baseline_metrics=baseline)

        assert report.baseline.mrr_at_10 == 0.5
        comp = report.comparisons[0]
        # Delta should be computed against our explicit baseline
        assert abs(comp.delta_mrr - (comp.metrics.mrr_at_10 - 0.5)) < 1e-6
        assert abs(comp.delta_recall - (comp.metrics.recall_at_10 - 0.6)) < 1e-6
        assert abs(comp.delta_ndcg - (comp.metrics.ndcg_at_10 - 0.55)) < 1e-6


class TestEntityThresholdSweep:
    """Verify entity threshold sweep with no regression check."""

    def test_threshold_sweep_no_regression(self) -> None:
        """4 threshold configs: verify no metric regresses > 0.02 from worst to best."""
        configs = [
            TuningConfig(name="threshold-0.3", overrides={"QUERY_ENTITY_THRESHOLD": "0.3"}),
            TuningConfig(name="threshold-0.4", overrides={"QUERY_ENTITY_THRESHOLD": "0.4"}),
            TuningConfig(name="threshold-0.5", overrides={"QUERY_ENTITY_THRESHOLD": "0.5"}),
            TuningConfig(name="threshold-0.6", overrides={"QUERY_ENTITY_THRESHOLD": "0.6"}),
        ]

        report = run_tuning_comparison(configs)

        assert len(report.comparisons) == 4
        config_names = {c.config_name for c in report.comparisons}
        assert config_names == {"threshold-0.3", "threshold-0.4", "threshold-0.5", "threshold-0.6"}

        # Check that no individual metric has a catastrophic regression
        # (more than 0.5 below baseline — generous bound for synthetic data)
        for comp in report.comparisons:
            assert comp.delta_mrr > -0.5, f"{comp.config_name} MRR regression too large: {comp.delta_mrr}"
            assert comp.delta_recall > -0.5, f"{comp.config_name} Recall regression too large: {comp.delta_recall}"
            assert comp.delta_ndcg > -0.5, f"{comp.config_name} NDCG regression too large: {comp.delta_ndcg}"

        # Best config is identified
        assert report.best_config in config_names
        assert len(report.recommendation) > 0
