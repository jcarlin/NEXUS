"""Celery application configuration and task autodiscovery."""

from celery import Celery

from app.config import Settings

settings = Settings()

celery_app = Celery(
    "nexus",
    broker=settings.redis_url,
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
)

# Autodiscover tasks in all domains with Celery tasks.
celery_app.autodiscover_tasks(["app.ingestion", "app.entities", "app.cases", "app.analysis"])
