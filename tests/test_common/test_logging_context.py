"""Tests for structured logging context consistency.

Validates that bound contextvars appear in log output without needing
to be passed as explicit keyword arguments.
"""

from __future__ import annotations

import structlog
from structlog.testing import CapturingLogger


class TestLoggingContextVars:
    """Verify that structlog contextvars propagate to log output."""

    def setup_method(self):
        """Configure structlog with merge_contextvars for each test."""
        self._cap = CapturingLogger()
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.dev.ConsoleRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(0),
            context_class=dict,
            logger_factory=lambda: self._cap,
            cache_logger_on_first_use=False,
        )
        structlog.contextvars.clear_contextvars()

    def teardown_method(self):
        structlog.contextvars.clear_contextvars()
        structlog.reset_defaults()

    def test_bound_context_appears_without_explicit_kwargs(self):
        """When job_id is bound via contextvars, it appears in log output."""
        structlog.contextvars.bind_contextvars(job_id="job-123")

        structlog.get_logger().info("test.event", extra="data")

        # CapturingLogger stores (method_name, event_dict) tuples in .calls
        assert len(self._cap.calls) >= 1
        # ConsoleRenderer produces a single string, so check the raw call
        rendered = self._cap.calls[-1]
        # The rendered output should contain job_id since it was merged
        assert "job-123" in str(rendered)

    def test_multiple_bound_vars_all_appear(self):
        """Multiple bound context vars all appear in log output."""
        structlog.contextvars.bind_contextvars(
            task_id="task-abc",
            job_id="job-456",
            matter_id="matter-789",
        )

        structlog.get_logger().warning("test.warn")

        rendered = str(self._cap.calls[-1])
        assert "task-abc" in rendered
        assert "job-456" in rendered
        assert "matter-789" in rendered

    def test_clear_contextvars_removes_bound_context(self):
        """After clearing contextvars, previously bound vars should not appear."""
        structlog.contextvars.bind_contextvars(job_id="job-999")
        structlog.contextvars.clear_contextvars()

        structlog.get_logger().info("test.after_clear")

        rendered = str(self._cap.calls[-1])
        assert "job-999" not in rendered
