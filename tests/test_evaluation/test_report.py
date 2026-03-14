"""Tests for the QA evaluation report generator."""

from __future__ import annotations

from evaluation.report import (
    compute_recommendation,
    generate_qa_report,
)
from evaluation.schemas import (
    ComboEvalResult,
    FeatureFinding,
    FlagImpactSummary,
    FlagRecommendation,
    FlagRunMetrics,
    IngestionFeatureTest,
    QARecommendation,
    QAReport,
    RetrievalMetrics,
    RetrievalMode,
    StandaloneFeatureTest,
)

# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


class TestGenerateReport:
    def test_empty_report(self) -> None:
        report = QAReport()
        md = generate_qa_report(report)
        assert "# NEXUS Feature Flag QA Evaluation Report" in md
        assert "Generated" in md

    def test_baseline_section(self) -> None:
        report = QAReport(
            baseline=ComboEvalResult(
                name="Baseline",
                metrics=FlagRunMetrics(
                    latency_p50_ms=100.0,
                    latency_mean_ms=120.0,
                    num_queries=5,
                ),
                judge_composite=3.5,
            ),
        )
        md = generate_qa_report(report)
        assert "## Baseline Results" in md
        assert "Judge Composite" in md
        assert "3.50" in md

    def test_individual_matrix(self) -> None:
        report = QAReport(
            individual_results=[
                FlagImpactSummary(
                    flag_name="enable_hyde",
                    delta_mrr=0.15,
                    delta_recall=0.10,
                    delta_ndcg=0.12,
                    delta_latency_mean_ms=500.0,
                    recommendation=FlagRecommendation.KEEP_ENABLED,
                ),
                FlagImpactSummary(
                    flag_name="enable_text_to_sql",
                    delta_mrr=-0.05,
                    delta_recall=-0.02,
                    delta_ndcg=-0.03,
                    delta_latency_mean_ms=2000.0,
                    recommendation=FlagRecommendation.KEEP_DISABLED,
                ),
            ],
        )
        md = generate_qa_report(report)
        assert "## Individual Feature Flag Results" in md
        assert "enable_hyde" in md
        assert "enable_text_to_sql" in md
        assert "+0.1500" in md

    def test_combo_matrix(self) -> None:
        report = QAReport(
            combo_results=[
                ComboEvalResult(
                    name="Quality Stack",
                    flags_enabled={"enable_hyde": True, "enable_self_reflection": True},
                    metrics=FlagRunMetrics(
                        retrieval=RetrievalMetrics(
                            mode=RetrievalMode.HYBRID,
                            mrr_at_10=0.75,
                            recall_at_10=0.80,
                            ndcg_at_10=0.72,
                            precision_at_10=0.60,
                            num_queries=5,
                        ),
                        latency_p50_ms=200.0,
                        num_queries=5,
                    ),
                    judge_composite=4.2,
                ),
            ],
        )
        md = generate_qa_report(report)
        assert "## Curated Combination Results" in md
        assert "Quality Stack" in md
        assert "4.20" in md

    def test_standalone_section(self) -> None:
        report = QAReport(
            standalone_results=[
                StandaloneFeatureTest(
                    flag_name="enable_deposition_prep",
                    endpoint="/api/v1/depositions/profiles",
                    functional=True,
                    latency_ms=500.0,
                    status_code=200,
                ),
                StandaloneFeatureTest(
                    flag_name="enable_document_comparison",
                    endpoint="/api/v1/documents/compare",
                    functional=False,
                    error="HTTP 500",
                ),
            ],
        )
        md = generate_qa_report(report)
        assert "## Standalone Feature Tests" in md
        assert "PASS" in md
        assert "FAIL" in md

    def test_ingestion_section(self) -> None:
        report = QAReport(
            ingestion_results=[
                IngestionFeatureTest(
                    flag_name="enable_contextual_chunks",
                    docs_ingested=3,
                    ingestion_latency_ms=15000.0,
                ),
            ],
        )
        md = generate_qa_report(report)
        assert "## Ingestion Feature Tests" in md
        assert "enable_contextual_chunks" in md

    def test_findings_section(self) -> None:
        report = QAReport(
            findings=[
                FeatureFinding(
                    flag_name="enable_text_to_sql",
                    severity="critical",
                    category="bug",
                    description="3/5 queries returned HTTP 500",
                    evidence="Internal server error",
                ),
                FeatureFinding(
                    flag_name="enable_hyde",
                    severity="info",
                    category="improvement",
                    description="Retrieval quality improved by +0.15 MRR",
                ),
            ],
        )
        md = generate_qa_report(report)
        assert "## Findings & Issues" in md
        assert "CRITICAL" in md
        assert "INFO" in md
        assert "enable_text_to_sql" in md

    def test_recommendations_section(self) -> None:
        report = QAReport(
            recommendations={
                "enable_hyde": QARecommendation.ENABLE,
                "enable_text_to_sql": QARecommendation.FIX_FIRST,
                "enable_prompt_routing": QARecommendation.NEUTRAL,
                "enable_production_quality_monitoring": QARecommendation.SKIP,
            },
        )
        md = generate_qa_report(report)
        assert "## Recommendations" in md
        assert "ENABLE" in md
        assert "FIX_FIRST" in md
        assert "SKIP" in md

    def test_environment_section(self) -> None:
        report = QAReport(
            environment={
                "api_url": "http://localhost:8000",
                "llm_provider": "gemini",
                "llm_model": "gemini-2.0-flash",
                "judge_provider": "anthropic",
                "judge_model": "claude-sonnet-4-20250514",
            },
        )
        md = generate_qa_report(report)
        assert "gemini" in md
        assert "claude-sonnet" in md

    def test_full_report_has_all_sections(self) -> None:
        report = QAReport(
            environment={"api_url": "http://localhost:8000"},
            baseline=ComboEvalResult(name="Baseline", metrics=FlagRunMetrics()),
            individual_results=[
                FlagImpactSummary(flag_name="enable_hyde", recommendation=FlagRecommendation.KEEP_ENABLED),
            ],
            combo_results=[ComboEvalResult(name="Quality Stack", metrics=FlagRunMetrics())],
            standalone_results=[
                StandaloneFeatureTest(flag_name="enable_deposition_prep", endpoint="/test"),
            ],
            ingestion_results=[IngestionFeatureTest(flag_name="enable_contextual_chunks")],
            findings=[
                FeatureFinding(
                    flag_name="enable_hyde",
                    severity="info",
                    category="improvement",
                    description="Good",
                ),
            ],
            recommendations={"enable_hyde": QARecommendation.ENABLE},
        )
        md = generate_qa_report(report)
        assert "## Environment" in md
        assert "## Baseline Results" in md
        assert "## Individual Feature Flag Results" in md
        assert "## Curated Combination Results" in md
        assert "## Standalone Feature Tests" in md
        assert "## Ingestion Feature Tests" in md
        assert "## Findings & Issues" in md
        assert "## Recommendations" in md


# ---------------------------------------------------------------------------
# Recommendation logic
# ---------------------------------------------------------------------------


class TestComputeRecommendation:
    def test_fix_first_when_not_functional(self) -> None:
        rec = compute_recommendation(
            functional=False,
            error_rate=0.0,
            judge_composite_delta=0.5,
            retrieval_delta=0.1,
            latency_delta_s=1.0,
        )
        assert rec == QARecommendation.FIX_FIRST

    def test_fix_first_high_error_rate(self) -> None:
        rec = compute_recommendation(
            functional=True,
            error_rate=0.25,
            judge_composite_delta=0.5,
            retrieval_delta=0.1,
            latency_delta_s=1.0,
        )
        assert rec == QARecommendation.FIX_FIRST

    def test_enable_high_judge_delta(self) -> None:
        rec = compute_recommendation(
            functional=True,
            error_rate=0.0,
            judge_composite_delta=0.3,
            retrieval_delta=0.0,
            latency_delta_s=2.0,
        )
        assert rec == QARecommendation.ENABLE

    def test_enable_good_retrieval_low_latency(self) -> None:
        rec = compute_recommendation(
            functional=True,
            error_rate=0.0,
            judge_composite_delta=0.0,
            retrieval_delta=0.05,
            latency_delta_s=2.0,
        )
        assert rec == QARecommendation.ENABLE

    def test_skip_negative_judge_delta(self) -> None:
        rec = compute_recommendation(
            functional=True,
            error_rate=0.0,
            judge_composite_delta=-0.5,
            retrieval_delta=0.0,
            latency_delta_s=1.0,
        )
        assert rec == QARecommendation.SKIP

    def test_skip_high_latency_no_quality(self) -> None:
        rec = compute_recommendation(
            functional=True,
            error_rate=0.0,
            judge_composite_delta=0.05,
            retrieval_delta=0.01,
            latency_delta_s=4.0,
        )
        assert rec == QARecommendation.SKIP

    def test_neutral_small_changes(self) -> None:
        rec = compute_recommendation(
            functional=True,
            error_rate=0.0,
            judge_composite_delta=0.05,
            retrieval_delta=0.01,
            latency_delta_s=1.0,
        )
        assert rec == QARecommendation.NEUTRAL
