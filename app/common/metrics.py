"""Prometheus metrics for NEXUS platform.

All metric definitions live here. Import and use in instrumented modules.
Feature-gated by ENABLE_PROMETHEUS_METRICS — when disabled, metrics are
no-ops (prometheus_client handles this gracefully; the /metrics endpoint
simply won't be exposed).
"""

from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager

from prometheus_client import Counter, Histogram

# ---------------------------------------------------------------------------
# Query pipeline metrics
# ---------------------------------------------------------------------------

QUERY_DURATION = Histogram(
    "nexus_query_duration_seconds",
    "End-to-end query pipeline latency",
    labelnames=["tier"],
)

QUERY_TOTAL = Counter(
    "nexus_query_total",
    "Total queries processed",
    labelnames=["tier", "status"],
)

# ---------------------------------------------------------------------------
# LLM metrics
# ---------------------------------------------------------------------------

LLM_CALLS_TOTAL = Counter(
    "nexus_llm_calls_total",
    "Total LLM API calls",
    labelnames=["provider", "model"],
)

LLM_DURATION = Histogram(
    "nexus_llm_duration_seconds",
    "LLM call latency",
    labelnames=["provider", "model"],
)

LLM_TOKENS_TOTAL = Counter(
    "nexus_llm_tokens_total",
    "Total LLM tokens consumed",
    labelnames=["provider", "model", "type"],
)

# ---------------------------------------------------------------------------
# Ingestion metrics
# ---------------------------------------------------------------------------

INGESTION_JOBS_TOTAL = Counter(
    "nexus_ingestion_jobs_total",
    "Total ingestion jobs by final status",
    labelnames=["status"],
)

INGESTION_DURATION = Histogram(
    "nexus_ingestion_duration_seconds",
    "Ingestion job wall-clock duration",
)

# ---------------------------------------------------------------------------
# Embedding metrics
# ---------------------------------------------------------------------------

EMBEDDING_CALLS_TOTAL = Counter(
    "nexus_embedding_calls_total",
    "Total embedding API calls",
    labelnames=["provider"],
)

EMBEDDING_DURATION = Histogram(
    "nexus_embedding_duration_seconds",
    "Embedding call latency",
    labelnames=["provider"],
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


@contextmanager
def track_duration(histogram: Histogram, **labels: str) -> Generator[None, None, None]:
    """Context manager that observes elapsed time on a Histogram.

    Usage::

        with track_duration(LLM_DURATION, provider="anthropic", model="claude-3"):
            result = await llm.complete(...)
    """
    start = time.perf_counter()
    yield
    histogram.labels(**labels).observe(time.perf_counter() - start)
