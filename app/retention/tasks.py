"""Celery tasks for data retention lifecycle management."""

from __future__ import annotations

import asyncio
import traceback

import structlog
from celery import shared_task
from sqlalchemy import create_engine, text

from workers.celery_app import celery_app  # noqa: F401 — ensures @shared_task binds to our app

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Sync DB helpers
# ---------------------------------------------------------------------------


def _get_sync_engine(settings=None):
    """Create a disposable sync SQLAlchemy engine for the current task."""
    if settings is None:
        from app.config import Settings

        settings = Settings()
    return create_engine(settings.postgres_url_sync, pool_pre_ping=True)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@shared_task(name="app.retention.tasks.execute_scheduled_purge")
def execute_scheduled_purge(matter_id: str) -> dict:
    """Execute a scheduled purge for a single matter.

    Runs as a Celery task with sync-to-async bridge.
    """
    from app.config import Settings
    from app.feature_flags.service import load_overrides_sync_safe

    settings = Settings()
    _engine = _get_sync_engine(settings)
    load_overrides_sync_safe(settings, _engine)
    _engine.dispose()

    logger.info("retention.task.purge_start", matter_id=matter_id)

    async def _run() -> dict:
        from uuid import UUID

        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.common.storage import StorageClient
        from app.common.vector_store import VectorStoreClient
        from app.config import Settings
        from app.retention.service import RetentionService

        settings = Settings()
        engine = create_async_engine(settings.postgres_url, pool_pre_ping=True)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        qdrant = VectorStoreClient(settings)

        from neo4j import AsyncGraphDatabase

        neo4j_driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

        minio = StorageClient(settings)

        try:
            async with session_factory() as db:
                result = await RetentionService.execute_purge(
                    db=db,
                    matter_id=UUID(matter_id),
                    qdrant_client=qdrant,
                    neo4j_driver=neo4j_driver,
                    minio_client=minio,
                )
                return result
        finally:
            await neo4j_driver.close()
            await engine.dispose()

    try:
        result = asyncio.run(_run())
        logger.info("retention.task.purge_complete", matter_id=matter_id)
        return result
    except Exception:
        logger.error("retention.task.purge_failed", matter_id=matter_id, error=traceback.format_exc())
        raise


@shared_task(name="app.retention.tasks.check_retention_expirations")
def check_retention_expirations() -> dict:
    """Periodic task: find expired policies and schedule purge tasks."""
    from app.config import Settings
    from app.feature_flags.service import load_overrides_sync_safe

    settings = Settings()
    logger.info("retention.task.check_expirations_start")

    engine = _get_sync_engine(settings)
    load_overrides_sync_safe(settings, engine)
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT matter_id FROM retention_policies
                    WHERE status = 'active'
                      AND purge_scheduled_at <= NOW()
                """)
            )
            expired = [str(row[0]) for row in result.fetchall()]

        scheduled = []
        for mid in expired:
            execute_scheduled_purge.delay(mid)
            scheduled.append(mid)
            logger.info("retention.task.purge_scheduled", matter_id=mid)

        logger.info("retention.task.check_expirations_done", expired_count=len(scheduled))
        return {"expired_count": len(scheduled), "scheduled_matter_ids": scheduled}
    finally:
        engine.dispose()
