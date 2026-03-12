"""SLA definitions and Locust event listener for automated performance validation.

Registers a request handler that tracks response times and failure rates.
At test end, validates all SLAs and fails the test if any are breached.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import locust.env
from locust import events

# ---------------------------------------------------------------------------
# SLA Definitions
# ---------------------------------------------------------------------------

P95_BROWSE_MS = 500  # Document listing / entity search
P95_QUERY_MS = 30_000  # Investigation query (non-streaming)
P95_HEALTH_MS = 200  # Health check baseline
P95_UPLOAD_MS = 5_000  # File upload
ERROR_RATE_MAX = 0.01  # 1% max error rate across all endpoints


@dataclass
class EndpointStats:
    """Tracks response times for a single endpoint pattern."""

    times: list[float] = field(default_factory=list)
    failures: int = 0
    total: int = 0

    def p95(self) -> float:
        if not self.times:
            return 0.0
        sorted_times = sorted(self.times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[min(idx, len(sorted_times) - 1)]

    def error_rate(self) -> float:
        return self.failures / self.total if self.total > 0 else 0.0


# Endpoint name -> SLA threshold (ms)
SLA_THRESHOLDS: dict[str, float] = {
    "/api/v1/documents": P95_BROWSE_MS,
    "/api/v1/entities": P95_BROWSE_MS,
    "/api/v1/query": P95_QUERY_MS,
    "/api/v1/query/stream": P95_QUERY_MS,
    "/api/v1/health": P95_HEALTH_MS,
    "/api/v1/ingest": P95_UPLOAD_MS,
}


class SLATracker:
    """Tracks per-endpoint stats and validates SLAs at test end."""

    def __init__(self) -> None:
        self.stats: dict[str, EndpointStats] = {}
        self.violations: list[str] = []

    def record(self, name: str, response_time: float, failed: bool) -> None:
        if name not in self.stats:
            self.stats[name] = EndpointStats()
        ep = self.stats[name]
        ep.total += 1
        ep.times.append(response_time)
        if failed:
            ep.failures += 1

    def validate(self) -> list[str]:
        """Check all SLAs and return list of violation messages."""
        violations: list[str] = []

        # Per-endpoint p95 checks
        for endpoint, threshold in SLA_THRESHOLDS.items():
            if endpoint in self.stats:
                p95 = self.stats[endpoint].p95()
                if p95 > threshold:
                    violations.append(f"SLA BREACH: {endpoint} p95={p95:.0f}ms > {threshold:.0f}ms")

        # Global error rate
        total_requests = sum(ep.total for ep in self.stats.values())
        total_failures = sum(ep.failures for ep in self.stats.values())
        if total_requests > 0:
            global_error_rate = total_failures / total_requests
            if global_error_rate > ERROR_RATE_MAX:
                violations.append(f"SLA BREACH: global error rate {global_error_rate:.2%} > {ERROR_RATE_MAX:.2%}")

        self.violations = violations
        return violations


# ---------------------------------------------------------------------------
# Locust event hooks
# ---------------------------------------------------------------------------

_tracker = SLATracker()


@events.request.add_listener
def on_request(
    request_type: str,
    name: str,
    response_time: float,
    response_length: int,
    exception: Exception | None = None,
    **kwargs,
) -> None:
    """Record every request for SLA tracking."""
    _tracker.record(name, response_time, failed=exception is not None)


@events.quitting.add_listener
def on_quitting(environment: locust.env.Environment, **kwargs) -> None:
    """Validate SLAs when the test ends. Set exit code on failure."""
    violations = _tracker.validate()
    if violations:
        for v in violations:
            print(f"  !! {v}")
        if environment.process_exit_code is None or environment.process_exit_code == 0:
            environment.process_exit_code = 1
