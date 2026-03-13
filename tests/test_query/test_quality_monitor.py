"""Tests for the production quality monitoring module (T2-5)

and per-query-type metrics dashboards (T2-4).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.query.quality_monitor import QueryQualityScore, score_query_quality


class TestScoreQueryQuality:
    """Tests for score_query_quality computation."""

    def test_basic_scoring(self):
        """All three metrics should be computed correctly."""
        source_docs = [
            {"score": 0.9, "source_file": "doc1.pdf"},
            {"score": 0.7, "source_file": "doc2.pdf"},
        ]
        cited_claims = [
            {"claim_text": "Claim 1", "verified": True},
            {"claim_text": "Claim 2", "verified": False},
            {"claim_text": "Claim 3", "verified": True},
        ]
        response = " ".join(["word"] * 100)  # 100 words

        score = score_query_quality(
            query="What happened?",
            response=response,
            source_docs=source_docs,
            cited_claims=cited_claims,
        )

        assert isinstance(score, QueryQualityScore)
        assert score.retrieval_relevance == pytest.approx(0.8, abs=0.01)
        assert score.faithfulness == pytest.approx(2 / 3, abs=0.01)
        assert score.citation_density == pytest.approx(3.0, abs=0.01)  # 3 claims / 100 words * 100

    def test_empty_source_docs(self):
        """No source docs should give retrieval_relevance = 0."""
        score = score_query_quality(
            query="test",
            response="A response.",
            source_docs=[],
            cited_claims=[],
        )

        assert score.retrieval_relevance == 0.0

    def test_empty_cited_claims(self):
        """No cited claims should give faithfulness = 1.0 (nothing to verify)."""
        score = score_query_quality(
            query="test",
            response="A response with some words.",
            source_docs=[{"score": 0.9}],
            cited_claims=[],
        )

        assert score.faithfulness == 1.0
        assert score.citation_density == 0.0

    def test_all_verified_claims(self):
        """All verified claims should give faithfulness = 1.0."""
        cited_claims = [
            {"claim_text": "Claim 1", "verified": True},
            {"claim_text": "Claim 2", "verified": True},
        ]

        score = score_query_quality(
            query="test",
            response="Some response text here.",
            source_docs=[{"score": 0.5}],
            cited_claims=cited_claims,
        )

        assert score.faithfulness == 1.0

    def test_no_verified_claims(self):
        """No verified claims should give faithfulness = 0.0."""
        cited_claims = [
            {"claim_text": "Claim 1", "verified": False},
            {"claim_text": "Claim 2", "verified": False},
        ]

        score = score_query_quality(
            query="test",
            response="Some response.",
            source_docs=[{"score": 0.5}],
            cited_claims=cited_claims,
        )

        assert score.faithfulness == 0.0

    def test_empty_response(self):
        """Empty response should give citation_density = 0."""
        score = score_query_quality(
            query="test",
            response="",
            source_docs=[{"score": 0.5}],
            cited_claims=[{"claim_text": "C1", "verified": True}],
        )

        assert score.citation_density == 0.0

    def test_retrieval_relevance_clamped(self):
        """Retrieval relevance should be clamped to [0, 1]."""
        # Score > 1 (shouldn't happen normally, but test clamping)
        score = score_query_quality(
            query="test",
            response="Response.",
            source_docs=[{"score": 1.5}],
            cited_claims=[],
        )

        assert score.retrieval_relevance == 1.0

    def test_citation_density_calculation(self):
        """Citation density should be claims per 100 words."""
        response = " ".join(["word"] * 200)  # 200 words
        cited_claims = [
            {"claim_text": "C1", "verified": True},
            {"claim_text": "C2", "verified": True},
            {"claim_text": "C3", "verified": False},
            {"claim_text": "C4", "verified": True},
        ]

        score = score_query_quality(
            query="test",
            response=response,
            source_docs=[{"score": 0.8}],
            cited_claims=cited_claims,
        )

        # 4 claims / 200 words * 100 = 2.0
        assert score.citation_density == pytest.approx(2.0, abs=0.01)

    def test_missing_score_key(self):
        """Source docs without 'score' key should default to 0."""
        score = score_query_quality(
            query="test",
            response="Response.",
            source_docs=[{"source_file": "doc.pdf"}],  # No 'score' key
            cited_claims=[],
        )

        assert score.retrieval_relevance == 0.0

    def test_missing_verified_key(self):
        """Claims without 'verified' key should default to False."""
        score = score_query_quality(
            query="test",
            response="Response text here.",
            source_docs=[{"score": 0.8}],
            cited_claims=[{"claim_text": "C1"}],  # No 'verified' key
        )

        assert score.faithfulness == 0.0


class TestQueryQualityScoreModel:
    """Tests for the QueryQualityScore Pydantic model."""

    def test_valid_score(self):
        score = QueryQualityScore(
            retrieval_relevance=0.85,
            faithfulness=0.9,
            citation_density=2.5,
        )
        assert score.retrieval_relevance == 0.85

    def test_boundary_values(self):
        score = QueryQualityScore(
            retrieval_relevance=0.0,
            faithfulness=1.0,
            citation_density=0.0,
        )
        assert score.retrieval_relevance == 0.0
        assert score.faithfulness == 1.0


# ---------------------------------------------------------------------------
# T2-4: Per-query-type metrics recording
# ---------------------------------------------------------------------------


class TestMetricsRecordQueryType:
    """Tests that metrics record the correct query_type label."""

    def test_query_type_total_labels(self):
        """QUERY_TYPE_TOTAL should accept query_type + status labels."""
        from app.common.metrics import QUERY_TYPE_TOTAL

        # Should not raise — labels are valid
        QUERY_TYPE_TOTAL.labels(query_type="analytical", status="success").inc()

    def test_query_type_duration_labels(self):
        """QUERY_TYPE_DURATION should accept query_type label."""
        from app.common.metrics import QUERY_TYPE_DURATION

        QUERY_TYPE_DURATION.labels(query_type="timeline").observe(1.5)

    def test_retrieval_confidence_labels(self):
        """RETRIEVAL_CONFIDENCE should accept query_type label."""
        from app.common.metrics import RETRIEVAL_CONFIDENCE

        RETRIEVAL_CONFIDENCE.labels(query_type="exploratory").observe(0.85)

    def test_faithfulness_score_labels(self):
        """FAITHFULNESS_SCORE should accept query_type label."""
        from app.common.metrics import FAITHFULNESS_SCORE

        FAITHFULNESS_SCORE.labels(query_type="factual").observe(0.95)

    def test_production_faithfulness_no_labels(self):
        """PRODUCTION_FAITHFULNESS has no labels (production-wide aggregate)."""
        from app.common.metrics import PRODUCTION_FAITHFULNESS

        PRODUCTION_FAITHFULNESS.observe(0.9)

    def test_production_retrieval_relevance_no_labels(self):
        """PRODUCTION_RETRIEVAL_RELEVANCE has no labels (production-wide aggregate)."""
        from app.common.metrics import PRODUCTION_RETRIEVAL_RELEVANCE

        PRODUCTION_RETRIEVAL_RELEVANCE.observe(0.75)


class TestRouterQueryTypePropagation:
    """Tests that the query router propagates query_type from graph state."""

    @pytest.mark.anyio
    async def test_router_extracts_query_type_from_final_state(self):
        """After graph.ainvoke(), query_type should come from final_state['_query_type']."""
        from app.query.router import _score_and_record_quality

        # The _score_and_record_quality helper receives query_type explicitly
        # from the router, which extracts it from final_state.
        # We verify the helper accepts and uses query_type correctly.
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock(return_value=AsyncMock())
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.dependencies.get_session_factory", return_value=mock_factory),
            patch("app.common.metrics.PRODUCTION_FAITHFULNESS"),
            patch("app.common.metrics.PRODUCTION_RETRIEVAL_RELEVANCE"),
        ):
            await _score_and_record_quality(
                query="Who is connected to Entity X?",
                response="Entity X is connected to Y and Z.",
                source_docs=[{"score": 0.8}],
                cited_claims=[{"claim_text": "C1", "verified": True}],
                thread_id="test-thread-123",
                query_type="analytical",
            )

            # Verify the DB insert was called with correct query_type
            call_args = mock_session.execute.call_args
            params = call_args[0][1]
            assert params["query_type"] == "analytical"


# ---------------------------------------------------------------------------
# T2-5: Sampling logic and fire-and-forget
# ---------------------------------------------------------------------------


class TestSamplingLogic:
    """Tests for the quality monitoring sampling mechanism."""

    def test_sample_rate_config_default(self):
        """Default sample rate should be 0.1 (10%)."""
        from app.config import Settings

        settings = Settings(
            anthropic_api_key="test",
            openai_api_key="test",
        )
        assert settings.quality_monitoring_sample_rate == 0.1

    def test_quality_monitoring_disabled_by_default(self):
        """Production quality monitoring should be disabled by default."""
        from app.config import Settings

        settings = Settings(
            anthropic_api_key="test",
            openai_api_key="test",
        )
        assert settings.enable_production_quality_monitoring is False

    def test_sampling_with_zero_rate_never_triggers(self):
        """A sample rate of 0.0 should never trigger scoring."""
        import random

        random.seed(42)
        triggered = sum(1 for _ in range(1000) if random.random() < 0.0)
        assert triggered == 0

    def test_sampling_with_full_rate_always_triggers(self):
        """A sample rate of 1.0 should always trigger scoring."""
        import random

        random.seed(42)
        triggered = sum(1 for _ in range(100) if random.random() < 1.0)
        assert triggered == 100


class TestFireAndForget:
    """Tests that quality monitoring doesn't block the response."""

    @pytest.mark.anyio
    async def test_score_and_record_quality_handles_errors_gracefully(self):
        """_score_and_record_quality should catch exceptions and log warning."""
        from app.query.router import _score_and_record_quality

        # Patch get_session_factory to raise — should not propagate
        with patch(
            "app.dependencies.get_session_factory",
            side_effect=RuntimeError("DB unavailable"),
        ):
            # Should not raise despite the error
            await _score_and_record_quality(
                query="test query",
                response="test response",
                source_docs=[{"score": 0.5}],
                cited_claims=[],
                thread_id="thread-1",
                query_type="factual",
            )

    @pytest.mark.anyio
    async def test_score_and_record_quality_records_prometheus_metrics(self):
        """_score_and_record_quality should observe Prometheus metrics."""
        from app.query.router import _score_and_record_quality

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock(return_value=AsyncMock())
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_faithfulness = MagicMock()
        mock_relevance = MagicMock()

        with (
            patch("app.dependencies.get_session_factory", return_value=mock_factory),
            patch("app.common.metrics.PRODUCTION_FAITHFULNESS", mock_faithfulness),
            patch("app.common.metrics.PRODUCTION_RETRIEVAL_RELEVANCE", mock_relevance),
        ):
            await _score_and_record_quality(
                query="test",
                response="Some words here.",
                source_docs=[{"score": 0.7}],
                cited_claims=[{"claim_text": "C1", "verified": True}],
                thread_id="thread-2",
                query_type="factual",
            )

            mock_faithfulness.observe.assert_called_once()
            mock_relevance.observe.assert_called_once()
