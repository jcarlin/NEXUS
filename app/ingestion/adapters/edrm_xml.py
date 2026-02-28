"""EDRM XML adapter — import documents from an EDRM XML load file."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import structlog

from app.edrm.loadfile_parser import LoadFileParser
from app.ingestion.bulk_import import ImportDocument, compute_content_hash

logger = structlog.get_logger(__name__)

# Common field names for file paths in EDRM XML
_FILE_PATH_FIELDS = ("File_Path", "File_FilePath", "FilePath", "PATH", "TEXTPATH")

# Common field names for email headers
_EMAIL_HEADER_MAP = {
    "From": "from",
    "To": "to",
    "Subject": "subject",
    "Date": "date",
    "MessageID": "message_id",
    "Message-ID": "message_id",
    "InReplyTo": "in_reply_to",
    "In-Reply-To": "in_reply_to",
    "References": "references",
}


class EDRMXMLAdapter:
    """Parse an EDRM XML load file and yield ``ImportDocument`` instances."""

    def __init__(self, xml_path: Path, content_dir: Path | None = None) -> None:
        self._xml_path = xml_path
        self._content_dir = content_dir or xml_path.parent

    @property
    def name(self) -> str:
        return "edrm_xml"

    def iter_documents(self, *, limit: int | None = None) -> Iterator[ImportDocument]:
        xml_content = self._xml_path.read_text(encoding="utf-8", errors="replace")
        records = LoadFileParser.parse_edrm_xml(xml_content)

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
                        "edrm_xml.read_failed",
                        doc_id=record.doc_id,
                        path=str(file_path),
                        exc_info=True,
                    )
                    continue
            elif not file_path:
                # No file path found; skip record
                logger.debug("edrm_xml.no_file_path", doc_id=record.doc_id)
                continue
            else:
                logger.warning("edrm_xml.file_not_found", doc_id=record.doc_id, path=str(file_path))
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
                source="edrm_xml",
                metadata=record.fields,
                email_headers=email_headers if email_headers else None,
            )
            count += 1

    def _resolve_file_path(self, fields: dict[str, str]) -> Path | None:
        """Find the text file path from EDRM record fields."""
        for field_name in _FILE_PATH_FIELDS:
            if field_name in fields and fields[field_name]:
                candidate = self._content_dir / fields[field_name]
                return candidate
        return None

    @staticmethod
    def _extract_email_headers(fields: dict[str, str]) -> dict[str, str]:
        """Map EDRM tag names to normalized email header keys."""
        headers: dict[str, str] = {}
        for edrm_key, header_key in _EMAIL_HEADER_MAP.items():
            if edrm_key in fields and fields[edrm_key]:
                headers[header_key] = fields[edrm_key]
        return headers
