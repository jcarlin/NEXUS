"""Epstein emails adapter — import email datasets from HuggingFace.

Supports two dataset schemas:

1. **to-be/epstein-emails** (flat): One row per message with columns
   ``from_address``, ``to_address``, ``subject``, ``message_html``, etc.

2. **notesbymuneeb/epstein-emails** (threaded): One row per thread with a
   JSON ``messages`` column containing an array of individual messages.

Both are mapped to ``ImportDocument(doc_type="email", email_headers={...})``,
which routes through the Celery pipeline for chunking, embedding, email
threading, communication analytics, and email-as-node graph creation.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import structlog

from app.ingestion.bulk_import import ImportDocument, compute_content_hash

logger = structlog.get_logger(__name__)

# Regex to strip HTML tags (matches existing pattern in parser.py)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

# Minimum body length to import (very short emails are usually noise)
_MIN_BODY_LENGTH = 20


def _strip_html(html: str) -> str:
    """Convert HTML to plain text by stripping tags and collapsing whitespace."""
    text = _HTML_TAG_RE.sub(" ", html)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _clean_sender(raw: str) -> str:
    """Extract a clean display name from sender strings like 'Name <email>' or 'Name [email]'."""
    # Remove email in angle brackets or square brackets
    name = re.sub(r"\s*[<\[][^>\]]*[>\]]", "", raw).strip()
    return name or raw.strip()


class EpsteinEmailAdapter:
    """Read Epstein email datasets from HuggingFace and yield ``ImportDocument`` instances.

    Auto-detects which schema variant is present based on column names:

    - **Flat** (``from_address`` column): ``to-be/epstein-emails``
    - **Threaded** (``messages`` column): ``notesbymuneeb/epstein-emails``
    """

    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path

    @property
    def name(self) -> str:
        return "epstein_emails"

    def iter_documents(self, *, limit: int | None = None) -> Iterator[ImportDocument]:
        suffix = self._file_path.suffix.lower()
        if suffix == ".parquet":
            df = pd.read_parquet(self._file_path)
        else:
            df = pd.read_csv(self._file_path)

        # Auto-detect schema variant
        if "from_address" in df.columns:
            yield from self._iter_flat(df, limit=limit)
        elif "messages" in df.columns:
            yield from self._iter_threaded(df, limit=limit)
        else:
            raise ValueError(
                f"Unrecognized email dataset schema. Expected 'from_address' (to-be) "
                f"or 'messages' (notesbymuneeb) column, got: {list(df.columns)}"
            )

    def _iter_flat(self, df: pd.DataFrame, *, limit: int | None = None) -> Iterator[ImportDocument]:
        """Yield documents from to-be/epstein-emails (one row = one message)."""
        count = 0
        skipped = 0

        for row in df.itertuples(index=False):
            if limit is not None and count >= limit:
                break

            # Extract body from HTML
            html = str(row.message_html) if pd.notna(row.message_html) else ""
            body = _strip_html(html)
            if len(body) < _MIN_BODY_LENGTH:
                skipped += 1
                continue

            sender = str(row.from_address) if pd.notna(row.from_address) else ""
            to = str(row.to_address) if pd.notna(row.to_address) else ""
            subject = str(row.subject) if pd.notna(row.subject) else ""
            timestamp = str(row.timestamp_iso) if pd.notna(row.timestamp_iso) else ""
            source_file = str(row.source_filename) if pd.notna(row.source_filename) else ""
            doc_id = str(row.document_id) if pd.notna(row.document_id) else ""
            msg_order = int(row.message_order) if pd.notna(row.message_order) else 0

            # Parse other_recipients (stored as string repr of list)
            other_recip_raw = str(row.other_recipients) if pd.notna(row.other_recipients) else "[]"
            try:
                other_recip = json.loads(other_recip_raw.replace("'", '"'))
            except (json.JSONDecodeError, ValueError):
                other_recip = []

            # Build recipient list
            recipients = [to] if to else []
            if isinstance(other_recip, list):
                recipients.extend(str(r) for r in other_recip if r)

            email_headers = {
                "from": sender,
                "to": ", ".join(recipients),
                "subject": subject,
                "date": timestamp,
            }

            # Use source_file + message_order as unique ID
            source_id = f"tobe:{doc_id}:{msg_order}" if doc_id else f"tobe:{source_file}:{msg_order}"
            filename = f"{doc_id or source_file}_msg{msg_order}.eml"

            content_hash = compute_content_hash(body)

            yield ImportDocument(
                source_id=source_id,
                filename=filename,
                text=body,
                content_hash=content_hash,
                source="epstein_emails_tobe",
                doc_type="email",
                page_count=1,
                metadata={
                    "source_file": source_file,
                    "document_id": doc_id,
                    "message_order": msg_order,
                    "dataset": "to-be/epstein-emails",
                },
                email_headers=email_headers,
            )
            count += 1

        logger.info(
            "epstein_emails.flat_scan_complete",
            yielded=count,
            skipped_short=skipped,
        )

    def _iter_threaded(self, df: pd.DataFrame, *, limit: int | None = None) -> Iterator[ImportDocument]:
        """Yield documents from notesbymuneeb/epstein-emails (one row = one thread)."""
        count = 0
        skipped = 0
        parse_errors = 0

        for row in df.itertuples(index=False):
            if limit is not None and count >= limit:
                break

            thread_id = str(row.thread_id) if pd.notna(row.thread_id) else ""
            source_file = str(row.source_file) if pd.notna(row.source_file) else ""
            thread_subject = str(row.subject) if pd.notna(row.subject) else ""

            # Parse messages JSON
            messages_raw = str(row.messages) if pd.notna(row.messages) else "[]"
            try:
                messages = json.loads(messages_raw)
            except (json.JSONDecodeError, ValueError):
                parse_errors += 1
                continue

            if not isinstance(messages, list):
                parse_errors += 1
                continue

            for msg_idx, msg in enumerate(messages):
                if limit is not None and count >= limit:
                    break

                body = msg.get("body", "")
                if not isinstance(body, str) or len(body.strip()) < _MIN_BODY_LENGTH:
                    skipped += 1
                    continue

                body = body.strip()
                sender_raw = msg.get("sender", "")
                sender = _clean_sender(str(sender_raw))
                recipients_raw = msg.get("recipients", [])
                recipients = [str(r) for r in recipients_raw if r] if isinstance(recipients_raw, list) else []
                timestamp = str(msg.get("timestamp", ""))
                msg_subject = str(msg.get("subject", "")) or thread_subject

                email_headers = {
                    "from": sender,
                    "to": ", ".join(recipients),
                    "subject": msg_subject,
                    "date": timestamp,
                }

                source_id = f"muneeb:{thread_id}:{msg_idx}"
                filename = f"{thread_id}_msg{msg_idx}.eml"

                content_hash = compute_content_hash(body)

                yield ImportDocument(
                    source_id=source_id,
                    filename=filename,
                    text=body,
                    content_hash=content_hash,
                    source="epstein_emails_muneeb",
                    doc_type="email",
                    page_count=1,
                    metadata={
                        "source_file": source_file,
                        "thread_id": thread_id,
                        "message_index": msg_idx,
                        "dataset": "notesbymuneeb/epstein-emails",
                    },
                    email_headers=email_headers,
                )
                count += 1

        logger.info(
            "epstein_emails.threaded_scan_complete",
            yielded=count,
            skipped_short=skipped,
            parse_errors=parse_errors,
        )
