"""Google Drive adapter for the CLI bulk-import path.

This adapter downloads files from a connected Google Drive account and yields
``ImportDocument`` instances.  Unlike the API-driven flow (which dispatches
Celery tasks), this adapter is synchronous and used by the CLI orchestrator.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator

import structlog

from app.ingestion.bulk_import import ImportDocument

logger = structlog.get_logger(__name__)


class GoogleDriveAdapter:
    """Download files from Google Drive and yield them as ``ImportDocument``."""

    def __init__(
        self,
        tokens_json: str,
        folder_id: str = "root",
        *,
        client_id: str = "",
        client_secret: str = "",
    ) -> None:
        self._tokens_json = tokens_json
        self._folder_id = folder_id
        self._client_id = client_id
        self._client_secret = client_secret

    @property
    def name(self) -> str:
        return "google_drive"

    def iter_documents(self, *, limit: int | None = None) -> Iterator[ImportDocument]:
        from app.config import Settings
        from app.gdrive.service import GDriveService

        settings = Settings()
        service = GDriveService(settings)

        files = service.list_files_recursive(self._tokens_json, self._folder_id)

        count = 0
        for f in files:
            if limit is not None and count >= limit:
                return

            try:
                file_bytes, suffix = service.download_file(
                    self._tokens_json,
                    f["id"],
                    f["mime_type"],
                )
                # For the CLI adapter, we only handle text-based content
                # Binary files (PDF, etc.) get their text via the full pipeline
                text_content = ""
                try:
                    text_content = file_bytes.decode("utf-8", errors="replace")
                except Exception:
                    text_content = f"[Binary file: {f['name']}{suffix}]"

                content_hash = hashlib.sha256(file_bytes).hexdigest()

                yield ImportDocument(
                    source_id=f["id"],
                    filename=f["name"] + suffix if suffix else f["name"],
                    text=text_content,
                    content_hash=content_hash,
                    source="google_drive",
                    metadata={
                        "drive_file_id": f["id"],
                        "drive_modified_time": f.get("modified_time"),
                        "mime_type": f["mime_type"],
                    },
                )
                count += 1

            except Exception:
                logger.warning("gdrive_adapter.download_failed", file_id=f["id"], exc_info=True)
                continue
