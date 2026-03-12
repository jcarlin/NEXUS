"""Verify load test SLA constants are defined and reasonable."""

import pytest

pytest.importorskip("locust", reason="locust not installed — skipping load test config tests")

from load_tests.sla import (  # noqa: E402
    ERROR_RATE_MAX,
    P95_BROWSE_MS,
    P95_HEALTH_MS,
    P95_QUERY_MS,
    P95_UPLOAD_MS,
    SLA_THRESHOLDS,
    SLATracker,
)


def test_sla_constants_defined():
    assert P95_BROWSE_MS > 0
    assert P95_QUERY_MS > 0
    assert P95_HEALTH_MS > 0
    assert P95_UPLOAD_MS > 0
    assert 0 < ERROR_RATE_MAX < 1.0


def test_sla_thresholds_cover_endpoints():
    expected = {"/api/v1/documents", "/api/v1/entities", "/api/v1/query", "/api/v1/health"}
    assert expected.issubset(SLA_THRESHOLDS.keys())


def test_sla_tracker_no_violations_when_fast():
    tracker = SLATracker()
    for _ in range(100):
        tracker.record("/api/v1/health", 50.0, failed=False)
    violations = tracker.validate()
    assert len(violations) == 0


def test_sla_tracker_detects_slow_endpoint():
    tracker = SLATracker()
    for _ in range(100):
        tracker.record("/api/v1/health", 300.0, failed=False)
    violations = tracker.validate()
    assert any("/api/v1/health" in v for v in violations)


def test_sla_tracker_detects_high_error_rate():
    tracker = SLATracker()
    for _ in range(50):
        tracker.record("/api/v1/health", 50.0, failed=False)
    for _ in range(10):
        tracker.record("/api/v1/health", 50.0, failed=True)
    violations = tracker.validate()
    assert any("error rate" in v for v in violations)
