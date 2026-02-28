"""Concordance DAT adapter — import documents from a Concordance load file."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import structlog

from app.edrm.loadfile_parser import LoadFileParser
from app.ingestion.bulk_import import ImportDocument, compute_content_hash

logger = structlog.get_logger(__name__)

# Common field names for file paths in Concordance DAT files
_FILE_PATH_FIELDS = ("TEXTPATH", "TEXT_PATH", "FilePath", "PATH", "File_Path", "NATIVE_FILE")

# Common field names for email headers
_EMAIL_HEADER_MAP = {
    "FROM": "from",
    "TO": "to",
    "SUBJECT": "subject",
    "DATE_SENT": "date",
    "MESSAGEID": "message_id",
    "MESSAGE_ID": "message_id",
    "IN_REPLY_TO": "in_reply_to",
    "REFERENCES": "references",
}


class ConcordanceDATAdapter:
    """Parse a Concordance DAT load file and yield ``ImportDocument`` instances."""

    def __init__(self, dat_path: Path, content_dir: Path | None = None) -> None:
        self._dat_path = dat_path
        self._content_dir = content_dir or dat_path.parent

    @property
    def name(self) -> str:
        return "concordance_dat"

    def iter_documents(self, *, limit: int | None = None) -> Iterator[ImportDocument]:
        dat_content = self._dat_path.read_text(encoding="utf-8", errors="replace")
        records = LoadFileParser.parse_dat(dat_content)

        count = 0
        for record in records:
            if limit is not None and count >= limit:
                return

            # Resolve file path from fields
            text = ""
            file_path = self._resolve_file_path(record.fields)
            if file_path and file_path.exists():
                try:
                    text = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    logger.warning(
                        "concordance_dat.read_failed",
                        doc_id=record.doc_id,
                        path=str(file_path),
                        exc_info=True,
                    )
                    continue
            elif not file_path:
                logger.debug("concordance_dat.no_file_path", doc_id=record.doc_id)
                continue
            else:
                logger.warning(
                    "concordance_dat.file_not_found",
                    doc_id=record.doc_id,
                    path=str(file_path),
                )
                continue

            if not text.strip():
                continue

            # Extract email headers if present
            email_headers = self._extract_email_headers(record.fields)

            content_hash = compute_content_hash(text)
            filename = file_path.name if file_path else f"{record.doc_id}.txt"

            yield ImportDocument(
                source_id=record.doc_id,
                filename=filename,
                text=text,
                content_hash=content_hash,
                source="concordance_dat",
                metadata=record.fields,
                email_headers=email_headers if email_headers else None,
            )
            count += 1

    def _resolve_file_path(self, fields: dict[str, str]) -> Path | None:
        """Find the text file path from DAT record fields."""
        for field_name in _FILE_PATH_FIELDS:
            if field_name in fields and fields[field_name]:
                candidate = self._content_dir / fields[field_name]
                return candidate
        return None

    @staticmethod
    def _extract_email_headers(fields: dict[str, str]) -> dict[str, str]:
        """Map Concordance field names to normalized email header keys."""
        headers: dict[str, str] = {}
        for dat_key, header_key in _EMAIL_HEADER_MAP.items():
            if dat_key in fields and fields[dat_key]:
                headers[header_key] = fields[dat_key]
        return headers
