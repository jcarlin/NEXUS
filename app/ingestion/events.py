"""Pipeline event recorder.

Provides a sync ``record_event`` function for use in Celery tasks and signal
handlers.  Events are fire-and-forget — failures are logged but never break
the main pipeline.
"""

from __future__ import annotations

import json

import structlog
from sqlalchemy import text

logger = structlog.get_logger(__name__)


def record_event(
    engine,
    job_id: str | None,
    event_type: str,
    worker: str | None = None,
    detail: dict | None = None,
    duration_ms: int | None = None,
) -> None:
    """Insert a pipeline event row (sync — called from Celery tasks)."""
    try:
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO pipeline_events (job_id, event_type, worker, detail, duration_ms)
                    VALUES (:job_id, :event_type, :worker, CAST(:detail AS jsonb), :duration_ms)
                """),
                {
                    "job_id": job_id,
                    "event_type": event_type,
                    "worker": worker,
                    "detail": json.dumps(detail or {}),
                    "duration_ms": duration_ms,
                },
            )
            conn.commit()
    except Exception:
        logger.warning(
            "pipeline_event.record_failed",
            event_type=event_type,
            job_id=job_id,
            exc_info=True,
        )
