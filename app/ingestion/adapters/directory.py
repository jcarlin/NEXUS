"""Directory adapter — recursively import text files from a local directory."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import structlog

from app.ingestion.bulk_import import ImportDocument, compute_content_hash

logger = structlog.get_logger(__name__)

# Extensions the directory adapter will read as plain text.
_TEXT_EXTENSIONS = {".txt", ".csv", ".tsv", ".md"}

# OS artifacts to skip (same patterns as process_zip in tasks.py).
_SKIP_PATTERNS = {"__MACOSX", ".DS_Store", "Thumbs.db", ".gitkeep"}


class DirectoryAdapter:
    """Recursively walk a directory and yield text files as ``ImportDocument``."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    @property
    def name(self) -> str:
        return "directory"

    def iter_documents(self, *, limit: int | None = None) -> Iterator[ImportDocument]:
        count = 0
        for path in sorted(self._data_dir.rglob("*")):
            if limit is not None and count >= limit:
                return

            # Skip directories
            if path.is_dir():
                continue

            # Skip OS artifacts
            if any(part in _SKIP_PATTERNS for part in path.parts):
                continue
            if path.name.startswith("."):
                continue

            # Only process known text extensions
            if path.suffix.lower() not in _TEXT_EXTENSIONS:
                logger.debug("directory.skip_extension", path=str(path), ext=path.suffix)
                continue

            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                logger.warning("directory.read_failed", path=str(path), exc_info=True)
                continue

            if not text.strip():
                continue

            content_hash = compute_content_hash(text)
            yield ImportDocument(
                source_id=str(path.relative_to(self._data_dir)),
                filename=path.name,
                text=text,
                content_hash=content_hash,
                source="directory",
                metadata={"relative_path": str(path.relative_to(self._data_dir))},
            )
            count += 1
