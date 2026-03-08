"""Celery tasks for Google Drive file download and ingestion.

Tasks run synchronously in the Celery worker.  Async operations use
``asyncio.run()`` wrappers.  Each task creates its own sync DB engine.
"""

from __future__ import annotations

import hashlib
import json
import uuid

import structlog
from celery import shared_task
from sqlalchemy import create_engine, text

from workers.celery_app import celery_app  # noqa: F401 — ensure task registration

logger = structlog.get_logger(__name__)


def _get_sync_engine():
    """Create a disposable sync SQLAlchemy engine for the current task."""
    from app.config import Settings

    settings = Settings()
    return create_engine(settings.postgres_url_sync, pool_pre_ping=True)


def _get_settings():
    from app.config import Settings

    return Settings()


def _update_stage(engine, job_id: str, stage: str, status: str, error: str | None = None) -> None:
    """Update a job's stage and status."""
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                UPDATE jobs
                SET stage = :stage, status = :status, error = :error, updated_at = now()
                WHERE id = :job_id
                """
            ),
            {"job_id": job_id, "stage": stage, "status": status, "error": error},
        )
        conn.commit()


@shared_task(name="gdrive.sync_folder", bind=True, max_retries=2)
def sync_gdrive_folder(
    self,
    job_id: str,
    connection_id: str,
    matter_id: str,
    file_ids: list[str],
    dataset_id: str | None = None,
) -> dict:
    """Download files from Google Drive and dispatch ingestion tasks.

    For each file:
    1. Check sync state — skip if unchanged
    2. Download (or export Google-native → PDF)
    3. Upload to MinIO at ``raw/{job_id}/{filename}``
    4. Dispatch ``process_document`` Celery task
    5. Update sync state
    """
    engine = _get_sync_engine()
    settings = _get_settings()

    try:
        _update_stage(engine, job_id, "downloading", "processing")

        # Build service (sync context — instantiate directly)
        from app.gdrive.service import GDriveService

        service = GDriveService(settings)

        # Decrypt tokens
        tokens_json = _get_connection_tokens_sync(engine, connection_id, matter_id, settings.gdrive_encryption_key)

        # Get existing sync map for change detection
        sync_map = _get_sync_map(engine, connection_id)

        # Get MinIO client
        from app.common.storage import StorageClient

        storage = StorageClient(settings)

        processed = 0
        skipped = 0
        errors = 0

        for file_id in file_ids:
            try:
                # Get file metadata from Drive
                file_meta = _get_file_metadata(service, tokens_json, file_id)
                if file_meta is None:
                    logger.warning("gdrive.file_not_found", file_id=file_id)
                    errors += 1
                    continue

                fname = file_meta["name"]
                mime_type = file_meta["mimeType"]
                modified_time = file_meta.get("modifiedTime")

                # Check if file has changed
                existing = sync_map.get(file_id)
                if existing and existing.get("drive_modified_time") == modified_time:
                    logger.info("gdrive.file_unchanged", file_id=file_id, name=fname)
                    skipped += 1
                    continue

                # Download or export
                file_bytes, suffix = service.download_file(tokens_json, file_id, mime_type)
                effective_name = fname + suffix if suffix else fname
                content_hash = hashlib.sha256(file_bytes).hexdigest()

                # Upload to MinIO
                minio_path = f"raw/{job_id}/{effective_name}"
                storage._client.put_object(
                    Bucket=storage._bucket,
                    Key=minio_path,
                    Body=file_bytes,
                )

                # Create a child job for this file
                child_job_id = str(uuid.uuid4())
                with engine.connect() as conn:
                    conn.execute(
                        text(
                            """
                            INSERT INTO jobs (id, filename, status, stage, parent_job_id, matter_id,
                                              dataset_id, metadata_, created_at, updated_at)
                            VALUES (:id, :filename, 'pending', 'uploading', :parent_job_id, :matter_id,
                                    :dataset_id, :metadata_, now(), now())
                            """
                        ),
                        {
                            "id": child_job_id,
                            "filename": effective_name,
                            "parent_job_id": job_id,
                            "matter_id": matter_id,
                            "dataset_id": dataset_id,
                            "metadata_": json.dumps({"minio_path": minio_path, "gdrive_file_id": file_id}),
                        },
                    )
                    conn.commit()

                # Dispatch process_document
                from app.ingestion.tasks import process_document

                process_document.delay(child_job_id, minio_path)

                # Update sync state
                _upsert_sync_state(
                    engine,
                    connection_id,
                    matter_id,
                    file_id,
                    fname,
                    modified_time,
                    content_hash,
                )

                processed += 1
                logger.info("gdrive.file_processed", file_id=file_id, name=effective_name, child_job_id=child_job_id)

            except Exception:
                logger.error("gdrive.file_error", file_id=file_id, exc_info=True)
                errors += 1

        # Update parent job
        final_status = "complete" if errors == 0 else "complete"
        error_msg = f"{errors} files failed" if errors > 0 else None
        _update_stage(engine, job_id, "complete", final_status, error=error_msg)

        result = {"processed": processed, "skipped": skipped, "errors": errors}
        logger.info("gdrive.sync_complete", job_id=job_id, **result)
        return result

    except Exception as exc:
        logger.error("gdrive.sync_failed", job_id=job_id, exc_info=True)
        _update_stage(engine, job_id, "complete", "failed", error=str(exc))
        raise


# ---------------------------------------------------------------------------
# Sync helpers (all sync — for Celery worker context)
# ---------------------------------------------------------------------------


def _get_connection_tokens_sync(
    engine,
    connection_id: str,
    matter_id: str,
    encryption_key: str,
) -> str:
    """Fetch and decrypt tokens from the DB (sync)."""
    from app.gdrive.crypto import decrypt_tokens

    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT encrypted_tokens
                FROM google_drive_connections
                WHERE id = :id AND matter_id = :matter_id AND is_active = true
                """
            ),
            {"id": connection_id, "matter_id": matter_id},
        )
        row = result.first()
        if row is None:
            raise ValueError(f"Connection {connection_id} not found or inactive")
        return decrypt_tokens(row.encrypted_tokens, encryption_key)


def _get_sync_map(engine, connection_id: str) -> dict[str, dict]:
    """Get existing sync state as a dict keyed by drive_file_id."""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT drive_file_id, drive_modified_time, content_hash, sync_status
                FROM google_drive_sync_state
                WHERE connection_id = :connection_id
                """
            ),
            {"connection_id": connection_id},
        )
        return {row.drive_file_id: dict(row._mapping) for row in result.fetchall()}


def _get_file_metadata(service, tokens_json: str, file_id: str) -> dict | None:
    """Get metadata for a single file from Drive."""

    creds = service._creds_from_tokens(tokens_json)
    drive = service._build_drive(creds)
    try:
        return drive.files().get(fileId=file_id, fields="id,name,mimeType,size,modifiedTime").execute()
    except Exception:
        logger.warning("gdrive.metadata_fetch_failed", file_id=file_id, exc_info=True)
        return None


def _upsert_sync_state(
    engine,
    connection_id: str,
    matter_id: str,
    drive_file_id: str,
    drive_file_name: str,
    drive_modified_time: str | None,
    content_hash: str | None,
) -> None:
    """Insert or update sync state (sync version for Celery tasks)."""
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO google_drive_sync_state
                    (connection_id, matter_id, drive_file_id, drive_file_name,
                     drive_modified_time, content_hash, sync_status, last_synced_at)
                VALUES
                    (:connection_id, :matter_id, :drive_file_id, :drive_file_name,
                     :drive_modified_time, :content_hash, 'synced', now())
                ON CONFLICT (connection_id, drive_file_id) DO UPDATE SET
                    drive_file_name = EXCLUDED.drive_file_name,
                    drive_modified_time = EXCLUDED.drive_modified_time,
                    content_hash = EXCLUDED.content_hash,
                    sync_status = 'synced',
                    last_synced_at = now()
                """
            ),
            {
                "connection_id": connection_id,
                "matter_id": matter_id,
                "drive_file_id": drive_file_id,
                "drive_file_name": drive_file_name,
                "drive_modified_time": drive_modified_time,
                "content_hash": content_hash,
            },
        )
        conn.commit()
