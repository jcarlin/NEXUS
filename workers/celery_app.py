"""Celery application configuration and task autodiscovery."""

from celery import Celery
from kombu import Queue

from app.config import Settings

settings = Settings()

celery_app = Celery(
    "nexus",
    broker=settings.celery_broker_url or settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_concurrency=settings.celery_concurrency,
    worker_max_tasks_per_child=100,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # --- Queue definitions ---
    task_queues=[
        Queue("default"),  # user-initiated ingestion (high priority)
        Queue("bulk"),  # batch reindex, matter scans
        Queue("background"),  # entity resolution, analysis, case setup, exports
    ],
    task_default_queue="default",
    # --- Task routing ---
    task_routes={
        "app.entities.tasks.*": {"queue": "background"},
        "app.analysis.tasks.*": {"queue": "background"},
        "app.cases.tasks.*": {"queue": "background"},
        "app.exports.tasks.*": {"queue": "background"},
        "app.retention.tasks.*": {"queue": "background"},
    },
    # --- Time limits (global defaults) ---
    task_soft_time_limit=1800,  # 30 min
    task_hard_time_limit=2100,  # 35 min
    # --- Rate limits ---
    task_annotations={
        "app.analysis.tasks.scan_document_sentiment": {"rate_limit": "10/m"},
        "app.cases.tasks.run_case_setup": {"rate_limit": "2/m"},
    },
    # --- Result expiry ---
    result_expires=86400,  # 24 hours
    # --- Beat schedule (periodic tasks) ---
    beat_schedule={
        "check-retention-expirations": {
            "task": "app.retention.tasks.check_retention_expirations",
            "schedule": 86400,  # Daily
        },
        "poll-service-health": {
            "task": "app.operations.tasks.poll_service_health",
            "schedule": 60,
        },
        "recover-orphan-jobs": {
            "task": "ingestion.recover_orphan_jobs",
            "schedule": 300,  # Every 5 minutes
        },
    },
)

# Autodiscover tasks in all domains with Celery tasks.
celery_app.autodiscover_tasks(
    ["app.ingestion", "app.entities", "app.cases", "app.analysis", "app.exports", "app.retention", "app.operations"]
)
