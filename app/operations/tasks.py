"""Celery periodic tasks for service health polling."""

from __future__ import annotations

import time

import structlog
from celery import shared_task
from sqlalchemy import text

from app.ingestion.tasks import _get_sync_engine

logger = structlog.get_logger(__name__)


@shared_task(name="app.operations.tasks.poll_service_health")
def poll_service_health() -> dict[str, str]:
    """Poll all 5 backing services and store health records.

    Runs every 60s via Celery Beat. Cleans up records older than 31 days.
    """
    engine = _get_sync_engine()
    results: list[tuple[str, str, int, str | None]] = []

    # --- PostgreSQL ---
    start = time.perf_counter()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        latency = round((time.perf_counter() - start) * 1000)
        results.append(("postgres", "ok", latency, None))
    except Exception as e:
        latency = round((time.perf_counter() - start) * 1000)
        results.append(("postgres", "error", latency, str(e)))

    # --- Redis ---
    import redis

    from app.config import Settings

    settings = Settings()
    start = time.perf_counter()
    try:
        r = redis.from_url(settings.redis_url)
        r.ping()
        r.close()
        latency = round((time.perf_counter() - start) * 1000)
        results.append(("redis", "ok", latency, None))
    except Exception as e:
        latency = round((time.perf_counter() - start) * 1000)
        results.append(("redis", "error", latency, str(e)))

    # --- Qdrant ---
    from qdrant_client import QdrantClient

    start = time.perf_counter()
    try:
        qc = QdrantClient(url=settings.qdrant_url, timeout=5)
        qc.get_collections()
        qc.close()
        latency = round((time.perf_counter() - start) * 1000)
        results.append(("qdrant", "ok", latency, None))
    except Exception as e:
        latency = round((time.perf_counter() - start) * 1000)
        results.append(("qdrant", "error", latency, str(e)))

    # --- Neo4j ---
    from neo4j import GraphDatabase

    start = time.perf_counter()
    try:
        driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
        with driver.session() as session:
            session.run("RETURN 1").consume()
        driver.close()
        latency = round((time.perf_counter() - start) * 1000)
        results.append(("neo4j", "ok", latency, None))
    except Exception as e:
        latency = round((time.perf_counter() - start) * 1000)
        results.append(("neo4j", "error", latency, str(e)))

    # --- MinIO ---
    import urllib.request

    start = time.perf_counter()
    try:
        protocol = "https" if settings.minio_use_ssl else "http"
        url = f"{protocol}://{settings.minio_endpoint}/minio/health/live"
        urllib.request.urlopen(url, timeout=5)  # noqa: S310
        latency = round((time.perf_counter() - start) * 1000)
        results.append(("minio", "ok", latency, None))
    except Exception as e:
        latency = round((time.perf_counter() - start) * 1000)
        results.append(("minio", "error", latency, str(e)))

    # --- Insert results ---
    with engine.connect() as conn:
        for service_name, status, latency_ms, error_message in results:
            conn.execute(
                text("""
                    INSERT INTO service_health_history (service_name, status, latency_ms, error_message)
                    VALUES (:service_name, :status, :latency_ms, :error_message)
                """),
                {
                    "service_name": service_name,
                    "status": status,
                    "latency_ms": latency_ms,
                    "error_message": error_message,
                },
            )
        # Clean up old records (>31 days)
        conn.execute(text("DELETE FROM service_health_history WHERE checked_at < NOW() - INTERVAL '31 days'"))
        conn.commit()

    logger.info(
        "poll_service_health.complete",
        results={r[0]: r[1] for r in results},
    )
    return {r[0]: r[1] for r in results}


@shared_task(name="app.operations.tasks.sync_bulk_import_counters")
def sync_bulk_import_counters() -> int:
    """Sync bulk_import_jobs counters from actual job status.

    Runs every 30s via Celery Beat.  Reconciles the
    ``processed_documents`` / ``failed_documents`` counters with
    a ``count(*) FILTER`` over the ``jobs`` table so the polling
    endpoint (which reads the counter columns directly) stays accurate.
    """
    engine = _get_sync_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                UPDATE bulk_import_jobs bi SET
                    processed_documents = LEAST(sub.done, bi.total_documents),
                    failed_documents = LEAST(sub.failed, bi.total_documents),
                    updated_at = now()
                FROM (
                    SELECT bulk_import_job_id,
                        count(*) FILTER (WHERE status = 'complete') AS done,
                        count(*) FILTER (WHERE status = 'failed') AS failed
                    FROM jobs
                    WHERE bulk_import_job_id IS NOT NULL
                    GROUP BY bulk_import_job_id
                ) sub
                WHERE bi.id = sub.bulk_import_job_id
                  AND bi.status = 'processing'
            """)
        )
        conn.commit()
        updated = result.rowcount
    if updated:
        logger.info("sync_bulk_import_counters.updated", count=updated)
    return updated
