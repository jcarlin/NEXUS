"""Tests for the Prometheus metrics module (app.common.metrics)."""

from __future__ import annotations

import time

import pytest

from app.common.metrics import (
    CITATION_VERIFICATION_TOTAL,
    CONTEXT_WINDOW_USAGE,
    EMBEDDING_CALLS_TOTAL,
    EMBEDDING_DURATION,
    INGESTION_DURATION,
    INGESTION_JOBS_TOTAL,
    LLM_CALLS_TOTAL,
    LLM_DURATION,
    LLM_TOKENS_TOTAL,
    QUERY_DURATION,
    QUERY_TOTAL,
    RETRIEVAL_CHUNKS_TOTAL,
    track_duration,
)

# ---------------------------------------------------------------------------
# Metric object creation
# ---------------------------------------------------------------------------


class TestMetricDefinitions:
    """Verify that all metric objects are created with correct types and labels."""

    def test_query_duration_is_histogram(self):
        assert QUERY_DURATION._type == "histogram"

    def test_query_total_is_counter(self):
        assert QUERY_TOTAL._type == "counter"

    def test_llm_calls_total_is_counter(self):
        assert LLM_CALLS_TOTAL._type == "counter"

    def test_llm_duration_is_histogram(self):
        assert LLM_DURATION._type == "histogram"

    def test_llm_tokens_total_is_counter(self):
        assert LLM_TOKENS_TOTAL._type == "counter"

    def test_ingestion_jobs_total_is_counter(self):
        assert INGESTION_JOBS_TOTAL._type == "counter"

    def test_ingestion_duration_is_histogram(self):
        assert INGESTION_DURATION._type == "histogram"

    def test_embedding_calls_total_is_counter(self):
        assert EMBEDDING_CALLS_TOTAL._type == "counter"

    def test_embedding_duration_is_histogram(self):
        assert EMBEDDING_DURATION._type == "histogram"

    def test_retrieval_chunks_total_is_counter(self):
        assert RETRIEVAL_CHUNKS_TOTAL._type == "counter"

    def test_citation_verification_total_is_counter(self):
        assert CITATION_VERIFICATION_TOTAL._type == "counter"

    def test_context_window_usage_is_histogram(self):
        assert CONTEXT_WINDOW_USAGE._type == "histogram"


# ---------------------------------------------------------------------------
# Label validation
# ---------------------------------------------------------------------------


class TestMetricLabels:
    """Verify metrics accept the expected label sets."""

    def test_query_duration_accepts_tier(self):
        QUERY_DURATION.labels(tier="fast").observe(0.5)

    def test_query_total_accepts_tier_and_status(self):
        QUERY_TOTAL.labels(tier="fast", status="success").inc()

    def test_llm_calls_total_accepts_provider_and_model(self):
        LLM_CALLS_TOTAL.labels(provider="anthropic", model="claude-3").inc()

    def test_llm_duration_accepts_provider_and_model(self):
        LLM_DURATION.labels(provider="anthropic", model="claude-3").observe(1.2)

    def test_llm_tokens_total_accepts_provider_model_type(self):
        LLM_TOKENS_TOTAL.labels(provider="anthropic", model="claude-3", type="input").inc(100)
        LLM_TOKENS_TOTAL.labels(provider="anthropic", model="claude-3", type="output").inc(50)

    def test_ingestion_jobs_total_accepts_status(self):
        INGESTION_JOBS_TOTAL.labels(status="completed").inc()

    def test_embedding_calls_total_accepts_provider(self):
        EMBEDDING_CALLS_TOTAL.labels(provider="openai").inc()

    def test_embedding_duration_accepts_provider(self):
        EMBEDDING_DURATION.labels(provider="openai").observe(0.3)

    def test_retrieval_chunks_total_accepts_source(self):
        RETRIEVAL_CHUNKS_TOTAL.labels(source="text").inc()
        RETRIEVAL_CHUNKS_TOTAL.labels(source="graph").inc()
        RETRIEVAL_CHUNKS_TOTAL.labels(source="visual").inc()

    def test_citation_verification_total_accepts_status(self):
        CITATION_VERIFICATION_TOTAL.labels(status="verified").inc()
        CITATION_VERIFICATION_TOTAL.labels(status="flagged").inc()
        CITATION_VERIFICATION_TOTAL.labels(status="unverified").inc()

    def test_context_window_usage_accepts_no_labels(self):
        CONTEXT_WINDOW_USAGE.observe(0.75)


# ---------------------------------------------------------------------------
# track_duration context manager
# ---------------------------------------------------------------------------


class TestTrackDuration:
    """Verify the track_duration helper context manager."""

    def test_track_duration_observes_time(self):
        """track_duration should record elapsed time on the histogram."""
        before_count = QUERY_DURATION.labels(tier="test_track")._sum.get()

        with track_duration(QUERY_DURATION, tier="test_track"):
            time.sleep(0.01)

        after_count = QUERY_DURATION.labels(tier="test_track")._sum.get()
        elapsed = after_count - before_count
        assert elapsed >= 0.01

    def test_track_duration_with_no_sleep(self):
        """track_duration should record near-zero time for instant blocks."""
        before_count = EMBEDDING_DURATION.labels(provider="test_instant")._sum.get()

        with track_duration(EMBEDDING_DURATION, provider="test_instant"):
            pass

        after_count = EMBEDDING_DURATION.labels(provider="test_instant")._sum.get()
        elapsed = after_count - before_count
        assert elapsed >= 0
        assert elapsed < 1.0  # Should be nearly instant

    def test_track_duration_propagates_exception(self):
        """track_duration should not swallow exceptions."""
        with pytest.raises(ValueError, match="boom"):
            with track_duration(LLM_DURATION, provider="test_err", model="test"):
                raise ValueError("boom")


# ---------------------------------------------------------------------------
# Counter increment verification
# ---------------------------------------------------------------------------


class TestCounterIncrements:
    """Verify counters actually increment when inc() is called."""

    def test_llm_calls_counter_increments(self):
        before = LLM_CALLS_TOTAL.labels(provider="test_inc", model="test")._value.get()
        LLM_CALLS_TOTAL.labels(provider="test_inc", model="test").inc()
        after = LLM_CALLS_TOTAL.labels(provider="test_inc", model="test")._value.get()
        assert after == before + 1

    def test_llm_tokens_counter_increments_by_amount(self):
        before = LLM_TOKENS_TOTAL.labels(provider="test_tok", model="test", type="input")._value.get()
        LLM_TOKENS_TOTAL.labels(provider="test_tok", model="test", type="input").inc(500)
        after = LLM_TOKENS_TOTAL.labels(provider="test_tok", model="test", type="input")._value.get()
        assert after == before + 500

    def test_embedding_calls_counter_increments(self):
        before = EMBEDDING_CALLS_TOTAL.labels(provider="test_emb")._value.get()
        EMBEDDING_CALLS_TOTAL.labels(provider="test_emb").inc()
        after = EMBEDDING_CALLS_TOTAL.labels(provider="test_emb")._value.get()
        assert after == before + 1
