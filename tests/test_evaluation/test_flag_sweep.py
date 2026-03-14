"""Tests for the feature flag evaluation sweep runner."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from evaluation.flag_sweep import (
    DEFAULT_EVAL_QUERIES,
    QUERY_TIME_FLAGS,
    _collect_metrics_from_responses,
    _percentile,
    compute_flag_impact,
    format_flag_sweep_report,
    run_flag_sweep,
)
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

# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestFlagSweepSchemas:
    def test_flag_sweep_config_defaults(self) -> None:
        config = FlagSweepConfig()
        assert config.flags == []
        assert config.combinations is False
        assert config.api_url == "http://localhost:8000"
        assert config.auth_token is None
        assert config.matter_id == "00000000-0000-0000-0000-000000000001"
        assert config.queries == []

    def test_flag_sweep_config_custom(self) -> None:
        config = FlagSweepConfig(
            flags=["enable_reranker", "enable_hyde"],
            combinations=True,
            api_url="http://nexus:9000",
            auth_token="tok-123",
            matter_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            queries=["What happened?"],
        )
        assert len(config.flags) == 2
        assert config.combinations is True
        assert config.queries == ["What happened?"]

    def test_flag_run_metrics_defaults(self) -> None:
        m = FlagRunMetrics()
        assert m.retrieval is None
        assert m.citation is None
        assert m.latency_p50_ms == 0.0
        assert m.num_queries == 0
        assert m.quality_gates_passed is False

    def test_flag_sweep_result_serialization(self) -> None:
        result = FlagSweepResult(
            flag_states={"enable_reranker": True},
            label="enable_reranker=ON",
            metrics=FlagRunMetrics(latency_mean_ms=42.0, num_queries=5),
        )
        data = result.model_dump(mode="json")
        assert data["flag_states"]["enable_reranker"] is True
        assert data["label"] == "enable_reranker=ON"
        assert data["metrics"]["latency_mean_ms"] == 42.0

    def test_flag_impact_summary_defaults(self) -> None:
        impact = FlagImpactSummary(flag_name="enable_reranker")
        assert impact.delta_mrr == 0.0
        assert impact.recommendation == FlagRecommendation.NEGLIGIBLE_IMPACT

    def test_flag_sweep_report_serialization(self) -> None:
        config = FlagSweepConfig()
        baseline = FlagSweepResult(
            flag_states={},
            label="baseline",
            metrics=FlagRunMetrics(),
        )
        report = FlagSweepReport(
            config=config,
            baseline=baseline,
            total_queries_run=10,
            total_duration_s=5.5,
        )
        json_str = report.model_dump_json()
        loaded = json.loads(json_str)
        assert loaded["total_queries_run"] == 10
        assert loaded["total_duration_s"] == 5.5

    def test_flag_recommendation_enum_values(self) -> None:
        assert FlagRecommendation.KEEP_ENABLED == "keep_enabled"
        assert FlagRecommendation.KEEP_DISABLED == "keep_disabled"
        assert FlagRecommendation.NEGLIGIBLE_IMPACT == "negligible_impact"


# ---------------------------------------------------------------------------
# Metric collection tests
# ---------------------------------------------------------------------------


class TestCollectMetrics:
    def test_empty_responses(self) -> None:
        metrics = _collect_metrics_from_responses([])
        assert metrics.num_queries == 0
        assert metrics.latency_mean_ms == 0.0

    def test_latency_computation(self) -> None:
        responses = [
            ({"response": "answer", "source_documents": []}, 100.0),
            ({"response": "answer", "source_documents": []}, 200.0),
            ({"response": "answer", "source_documents": []}, 300.0),
        ]
        metrics = _collect_metrics_from_responses(responses)
        assert metrics.num_queries == 3
        assert metrics.latency_mean_ms == 200.0
        assert metrics.latency_p50_ms == 200.0

    def test_citation_extraction_from_responses(self) -> None:
        responses = [
            (
                {
                    "response": "The contract was signed. [Source: contract.pdf, page 3]",
                    "source_documents": [{"filename": "contract.pdf"}],
                },
                50.0,
            ),
        ]
        metrics = _collect_metrics_from_responses(responses)
        assert metrics.citation is not None
        assert metrics.citation.total_claims == 1
        assert metrics.citation.hallucination_rate == 0.0

    def test_hallucination_detected(self) -> None:
        responses = [
            (
                {
                    "response": "See [Source: nonexistent.pdf, page 1]",
                    "source_documents": [{"filename": "real_doc.pdf"}],
                },
                50.0,
            ),
        ]
        metrics = _collect_metrics_from_responses(responses)
        assert metrics.citation is not None
        assert metrics.citation.hallucination_rate == 1.0
        assert metrics.citation.unsupported_claims == 1

    def test_retrieval_metrics_with_expected_docs(self) -> None:
        responses = [
            (
                {
                    "response": "answer",
                    "source_documents": [
                        {"filename": "doc_a.pdf"},
                        {"filename": "doc_b.pdf"},
                        {"filename": "noise.pdf"},
                    ],
                },
                100.0,
            ),
        ]
        expected = [["doc_a.pdf", "doc_b.pdf"]]
        metrics = _collect_metrics_from_responses(responses, expected_docs_per_query=expected)
        assert metrics.retrieval is not None
        assert metrics.retrieval.mrr_at_10 == 1.0  # doc_a is first
        assert metrics.retrieval.recall_at_10 == 1.0  # both found


class TestPercentile:
    def test_empty(self) -> None:
        assert _percentile([], 95) == 0.0

    def test_single_value(self) -> None:
        assert _percentile([42.0], 95) == 42.0

    def test_p50_is_median(self) -> None:
        assert _percentile([1.0, 2.0, 3.0], 50) == 2.0

    def test_p95(self) -> None:
        data = list(range(1, 101))  # 1..100
        p95 = _percentile([float(x) for x in data], 95)
        assert 95.0 <= p95 <= 96.0


# ---------------------------------------------------------------------------
# Impact computation tests
# ---------------------------------------------------------------------------


class TestComputeFlagImpact:
    def _make_metrics(
        self,
        mrr: float = 0.5,
        recall: float = 0.5,
        ndcg: float = 0.5,
        precision: float = 0.5,
        latency: float = 100.0,
        hallucination: float = 0.0,
    ) -> FlagRunMetrics:
        return FlagRunMetrics(
            retrieval=RetrievalMetrics(
                mode=RetrievalMode.HYBRID,
                mrr_at_10=mrr,
                recall_at_10=recall,
                ndcg_at_10=ndcg,
                precision_at_10=precision,
                num_queries=5,
            ),
            citation=CitationMetrics(
                citation_accuracy=1.0,
                hallucination_rate=hallucination,
                post_rationalization_rate=0.0,
                total_claims=10,
                supported_claims=10,
                unsupported_claims=0,
                post_rationalized_claims=0,
            ),
            latency_mean_ms=latency,
            num_queries=5,
            quality_gates_passed=True,
            gate_failures=[],
        )

    def test_flag_improves_retrieval(self) -> None:
        on = self._make_metrics(mrr=0.8, recall=0.9, ndcg=0.85)
        off = self._make_metrics(mrr=0.5, recall=0.5, ndcg=0.5)
        impact = compute_flag_impact("enable_reranker", on, off)
        assert impact.delta_mrr == pytest.approx(0.3, abs=1e-5)
        assert impact.delta_recall == pytest.approx(0.4, abs=1e-5)
        assert impact.recommendation == FlagRecommendation.KEEP_ENABLED

    def test_flag_hurts_retrieval(self) -> None:
        on = self._make_metrics(mrr=0.3, recall=0.3, ndcg=0.3)
        off = self._make_metrics(mrr=0.5, recall=0.5, ndcg=0.5)
        impact = compute_flag_impact("enable_hyde", on, off)
        assert impact.delta_mrr < 0
        assert impact.recommendation == FlagRecommendation.KEEP_DISABLED

    def test_negligible_impact(self) -> None:
        on = self._make_metrics(mrr=0.505, recall=0.505, ndcg=0.505)
        off = self._make_metrics(mrr=0.5, recall=0.5, ndcg=0.5)
        impact = compute_flag_impact("enable_prompt_routing", on, off)
        assert impact.recommendation == FlagRecommendation.NEGLIGIBLE_IMPACT

    def test_latency_delta(self) -> None:
        on = self._make_metrics(latency=250.0)
        off = self._make_metrics(latency=100.0)
        impact = compute_flag_impact("enable_reranker", on, off)
        assert impact.delta_latency_mean_ms == pytest.approx(150.0, abs=0.1)

    def test_no_retrieval_metrics(self) -> None:
        on = FlagRunMetrics(latency_mean_ms=100.0, num_queries=5)
        off = FlagRunMetrics(latency_mean_ms=200.0, num_queries=5)
        impact = compute_flag_impact("enable_reranker", on, off)
        assert impact.delta_mrr == 0.0
        assert impact.recommendation == FlagRecommendation.NEGLIGIBLE_IMPACT


# ---------------------------------------------------------------------------
# Report formatting tests
# ---------------------------------------------------------------------------


class TestFormatReport:
    def test_format_with_impacts(self) -> None:
        config = FlagSweepConfig()
        baseline = FlagSweepResult(
            flag_states={},
            label="baseline",
            metrics=FlagRunMetrics(latency_mean_ms=100.0, num_queries=5),
        )
        report = FlagSweepReport(
            config=config,
            baseline=baseline,
            impact_summary=[
                FlagImpactSummary(
                    flag_name="enable_reranker",
                    delta_mrr=0.15,
                    delta_recall=0.10,
                    delta_ndcg=0.12,
                    delta_latency_mean_ms=45.0,
                    recommendation=FlagRecommendation.KEEP_ENABLED,
                ),
            ],
            total_queries_run=10,
            total_duration_s=5.5,
        )
        text = format_flag_sweep_report(report)
        assert "FEATURE FLAG EVALUATION SWEEP" in text
        assert "enable_reranker" in text
        assert "keep_enabled" in text
        assert "+0.1500" in text

    def test_format_empty_report(self) -> None:
        config = FlagSweepConfig()
        baseline = FlagSweepResult(
            flag_states={},
            label="baseline",
            metrics=FlagRunMetrics(),
        )
        report = FlagSweepReport(config=config, baseline=baseline)
        text = format_flag_sweep_report(report)
        assert "No impact data collected" in text


# ---------------------------------------------------------------------------
# Constants tests
# ---------------------------------------------------------------------------


class TestConstants:
    def test_query_time_flags_are_valid(self) -> None:
        """All QUERY_TIME_FLAGS should be real Settings attributes."""
        for flag in QUERY_TIME_FLAGS:
            assert flag.startswith("enable_"), f"Flag {flag} doesn't start with enable_"

    def test_default_queries_non_empty(self) -> None:
        assert len(DEFAULT_EVAL_QUERIES) >= 3

    def test_query_time_flags_non_empty(self) -> None:
        assert len(QUERY_TIME_FLAGS) >= 5


# ---------------------------------------------------------------------------
# E2E sweep runner tests (mocked HTTP)
# ---------------------------------------------------------------------------


class TestRunFlagSweep:
    @pytest.mark.asyncio
    async def test_sweep_single_flag(self) -> None:
        """Sweep a single flag with mocked HTTP calls."""
        config = FlagSweepConfig(
            flags=["enable_reranker"],
            api_url="http://mock:8000",
            auth_token="fake-token",
            queries=["test query"],
        )

        mock_flag_list = {
            "items": [
                {"flag_name": "enable_reranker", "enabled": True},
            ]
        }
        mock_query_response = {
            "response": "Answer [Source: doc.pdf, page 1]",
            "source_documents": [{"filename": "doc.pdf"}],
            "follow_up_questions": [],
            "entities_mentioned": [],
            "thread_id": "t-1",
            "message_id": "m-1",
            "cited_claims": [],
        }

        call_count = {"set": 0}

        async def mock_request(method, url, **kwargs):
            resp = AsyncMock()
            resp.status_code = 200
            resp.raise_for_status = lambda: None

            if "feature-flags" in url and method == "GET":
                resp.json = lambda: mock_flag_list
            elif "feature-flags" in url and method == "PUT":
                call_count["set"] += 1
                resp.json = lambda: {"flag_name": "enable_reranker", "enabled": False}
            elif "query" in url:
                resp.json = lambda: mock_query_response
            else:
                resp.json = lambda: {}
            return resp

        with patch("evaluation.flag_sweep.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            async def dispatch(method, url, **kwargs):
                return await mock_request(method, url, **kwargs)

            mock_client.get = lambda url, **kw: mock_request("GET", url, **kw)
            mock_client.put = lambda url, **kw: mock_request("PUT", url, **kw)
            mock_client.post = lambda url, **kw: mock_request("POST", url, **kw)

            mock_client_cls.return_value = mock_client

            report = await run_flag_sweep(config)

        assert report.baseline.label == "baseline"
        assert len(report.experiments) == 1
        assert report.experiments[0].label == "enable_reranker=OFF"
        assert len(report.impact_summary) == 1
        assert report.impact_summary[0].flag_name == "enable_reranker"
        # Flag was toggled OFF then restored = 2 set calls
        assert call_count["set"] == 2

    @pytest.mark.asyncio
    async def test_sweep_missing_flag_skipped(self) -> None:
        """Flags not in the API response are skipped gracefully."""
        config = FlagSweepConfig(
            flags=["enable_nonexistent_flag"],
            api_url="http://mock:8000",
            auth_token="fake-token",
            queries=["test query"],
        )

        mock_flag_list = {"items": []}
        mock_query_response = {
            "response": "answer",
            "source_documents": [],
        }

        async def mock_request(method, url, **kwargs):
            resp = AsyncMock()
            resp.status_code = 200
            resp.raise_for_status = lambda: None
            if "feature-flags" in url:
                resp.json = lambda: mock_flag_list
            elif "query" in url:
                resp.json = lambda: mock_query_response
            else:
                resp.json = lambda: {}
            return resp

        with patch("evaluation.flag_sweep.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = lambda url, **kw: mock_request("GET", url, **kw)
            mock_client.post = lambda url, **kw: mock_request("POST", url, **kw)
            mock_client_cls.return_value = mock_client

            report = await run_flag_sweep(config)

        # No experiments since the flag wasn't found
        assert len(report.experiments) == 0
        assert len(report.impact_summary) == 0


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestFlagSweepCLI:
    def test_flag_sweep_help(self) -> None:
        """--flag-sweep appears in help output."""
        script = Path(__file__).resolve().parents[2] / "scripts" / "evaluate.py"
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--flag-sweep" in result.stdout
        assert "--api-url" in result.stdout
        assert "--flags" in result.stdout
        assert "--combinations" in result.stdout
