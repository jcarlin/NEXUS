"""Celery tasks for the export pipeline.

The Celery worker runs synchronously, so all operations use sync DB
connections and direct boto3 calls for MinIO.
"""

from __future__ import annotations

import json
import traceback
from datetime import UTC, datetime

import structlog
from celery import shared_task
from sqlalchemy import create_engine, text

from workers.celery_app import celery_app  # noqa: F401 — ensures @shared_task binds to our app

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Sync DB helpers (Celery tasks use the sync Postgres URL)
# ---------------------------------------------------------------------------


def _get_sync_engine(settings=None):
    """Create a disposable sync SQLAlchemy engine for the current task."""
    if settings is None:
        from app.config import Settings

        settings = Settings()
    return create_engine(settings.postgres_url_sync, pool_pre_ping=True)


def _update_export_job(engine, job_id: str, **kwargs) -> None:
    """Update fields on an export_jobs row."""
    set_parts = []
    params: dict = {"job_id": job_id}
    for key, value in kwargs.items():
        if key == "parameters" and isinstance(value, dict):
            set_parts.append(f"{key} = CAST(:{key} AS jsonb)")
            params[key] = json.dumps(value)
        else:
            set_parts.append(f"{key} = :{key}")
            params[key] = value

    if not set_parts:
        return

    sql = f"UPDATE export_jobs SET {', '.join(set_parts)} WHERE id = :job_id"
    with engine.connect() as conn:
        conn.execute(text(sql), params)
        conn.commit()

    logger.info("export_job.updated", job_id=job_id, fields=list(kwargs.keys()))


def _get_minio_client():
    """Create a sync boto3 S3 client pointed at MinIO."""
    import boto3
    from botocore.config import Config as BotoConfig

    from app.config import Settings

    settings = Settings()
    scheme = "https" if settings.minio_use_ssl else "http"
    endpoint_url = f"{scheme}://{settings.minio_endpoint}"

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    ), settings.minio_bucket


# ---------------------------------------------------------------------------
# Export task
# ---------------------------------------------------------------------------


@shared_task(bind=True, name="exports.run_export")
def run_export(self, export_job_id: str) -> None:
    """Run an export job: read parameters, dispatch to generator, upload result."""
    from app.config import Settings
    from app.feature_flags.service import load_overrides_sync_safe

    settings = Settings()
    engine = _get_sync_engine(settings)
    load_overrides_sync_safe(settings, engine)

    try:
        # Read the export job
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT id, matter_id, export_type, export_format, parameters
                    FROM export_jobs
                    WHERE id = :job_id
                """),
                {"job_id": export_job_id},
            )
            row = result.first()

        if row is None:
            logger.error("export_job.not_found", job_id=export_job_id)
            return

        job = dict(row._mapping)
        matter_id = str(job["matter_id"])
        export_type = job["export_type"]
        export_format = job["export_format"]
        params = job["parameters"] if isinstance(job["parameters"], dict) else {}

        # Mark as processing
        _update_export_job(engine, export_job_id, status="processing")

        # Parse document_ids from parameters if present
        doc_ids = params.get("document_ids")
        production_set_id = params.get("production_set_id")

        # Dispatch to the appropriate generator
        from app.exports.generators import (
            generate_court_ready,
            generate_edrm_package,
            generate_privilege_log,
            generate_result_set,
        )

        if export_type == "court_ready":
            data = generate_court_ready(engine, matter_id, doc_ids, production_set_id)
        elif export_type == "edrm_xml":
            data = generate_edrm_package(engine, matter_id, doc_ids)
        elif export_type == "privilege_log":
            fmt = "csv" if export_format == "csv" else "csv"
            data = generate_privilege_log(engine, matter_id, production_set_id, fmt=fmt)
        elif export_type == "result_set":
            fmt = "csv" if export_format == "csv" else "csv"
            data = generate_result_set(engine, matter_id, doc_ids, fmt=fmt)
        else:
            raise ValueError(f"Unknown export type: {export_type}")

        # Upload to MinIO
        output_key = f"exports/{matter_id}/{export_job_id}.{export_format}"
        s3_client, bucket = _get_minio_client()
        s3_client.put_object(
            Bucket=bucket,
            Key=output_key,
            Body=data,
            ContentType="application/octet-stream",
        )

        # Mark as complete
        _update_export_job(
            engine,
            export_job_id,
            status="complete",
            output_path=output_key,
            file_size_bytes=len(data),
            completed_at=datetime.now(UTC),
        )

        logger.info(
            "export_job.completed",
            job_id=export_job_id,
            export_type=export_type,
            size_bytes=len(data),
        )

    except Exception:
        tb = traceback.format_exc()
        logger.error("export_job.failed", job_id=export_job_id, error=tb)
        _update_export_job(
            engine,
            export_job_id,
            status="failed",
            error=tb[:2000],
        )

    finally:
        engine.dispose()
