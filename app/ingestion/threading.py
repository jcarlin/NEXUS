"""Email threading via RFC 5322 headers.

Implements a simplified JWZ-style threading algorithm:
1. Check References header (most reliable per RFC 5322)
2. Fall back to In-Reply-To header
3. Fall back to normalized subject matching (strip Re:/Fwd: prefixes)

Thread assignment is inline in the pipeline (called from tasks.py).
Inclusive email detection is a post-batch Celery task.
"""

from __future__ import annotations

import hashlib
import re

import structlog

logger = structlog.get_logger(__name__)

# Pattern to strip Re:/Fwd: prefixes from subjects
_SUBJECT_PREFIX_RE = re.compile(
    r"^(re|fwd?|fw)\s*:\s*",
    re.IGNORECASE,
)


def _normalize_subject(subject: str) -> str:
    """Strip Re:/Fwd:/Fw: prefixes and normalize whitespace."""
    result = subject.strip()
    while _SUBJECT_PREFIX_RE.match(result):
        result = _SUBJECT_PREFIX_RE.sub("", result, count=1).strip()
    return result.lower()


def _make_thread_id(seed: str) -> str:
    """Generate a deterministic thread_id from a seed string."""
    return hashlib.sha256(seed.encode()).hexdigest()[:16]


class EmailThreader:
    """Assign thread IDs to email documents based on RFC 5322 headers.

    Usage from Celery task (inline, not async):
        threader = EmailThreader()
        thread_id, position = threader.assign_thread(engine, doc_id, headers, matter_id)
    """

    @staticmethod
    def assign_thread(
        engine,
        doc_id: str,
        headers: dict[str, str],
        matter_id: str | None = None,
    ) -> tuple[str, int]:
        """Determine thread_id and position for an email document.

        Tries, in order:
        1. References header — first message-id is the thread root
        2. In-Reply-To header — the referenced message is the parent
        3. Normalized subject match — find existing thread by subject

        Returns (thread_id, thread_position).
        """
        from sqlalchemy import text

        message_id = headers.get("message_id", "").strip()
        in_reply_to = headers.get("in_reply_to", "").strip()
        references = headers.get("references", "").strip()
        subject = headers.get("subject", "")

        thread_id = ""
        thread_position = 0

        with engine.connect() as conn:
            # Strategy 1: References header (most reliable)
            if references:
                # Extract first message-id from References (the thread root)
                ref_ids = references.split()
                root_ref = ref_ids[0].strip()
                thread_id = _make_thread_id(root_ref)
                thread_position = len(ref_ids)

                logger.info(
                    "threading.by_references",
                    doc_id=doc_id,
                    thread_id=thread_id,
                    ref_count=len(ref_ids),
                )

            # Strategy 2: In-Reply-To header
            elif in_reply_to:
                # Check if the parent message exists and has a thread
                matter_clause = ""
                params: dict = {"in_reply_to": in_reply_to.strip()}
                if matter_id:
                    matter_clause = " AND matter_id = :matter_id"
                    params["matter_id"] = matter_id

                result = conn.execute(
                    text(
                        f"SELECT thread_id, thread_position FROM documents "
                        f"WHERE message_id = :in_reply_to{matter_clause} "
                        f"LIMIT 1"
                    ),
                    params,
                )
                parent = result.first()

                if parent and parent.thread_id:
                    thread_id = parent.thread_id
                    thread_position = (parent.thread_position or 0) + 1
                else:
                    thread_id = _make_thread_id(in_reply_to)
                    thread_position = 1

                logger.info(
                    "threading.by_in_reply_to",
                    doc_id=doc_id,
                    thread_id=thread_id,
                    parent_found=parent is not None,
                )

            # Strategy 3: Subject fallback
            elif subject:
                normalized = _normalize_subject(subject)
                if normalized:
                    matter_clause = ""
                    params = {"normalized": normalized}
                    if matter_id:
                        matter_clause = " AND matter_id = :matter_id"
                        params["matter_id"] = matter_id

                    result = conn.execute(
                        text(
                            f"SELECT thread_id, MAX(thread_position) as max_pos "
                            f"FROM documents "
                            f"WHERE thread_id IS NOT NULL{matter_clause} "
                            f"AND lower(filename) LIKE '%%.eml' OR lower(filename) LIKE '%%.msg' "
                            f"GROUP BY thread_id "
                            f"HAVING bool_or("
                            f"  lower(regexp_replace(filename, '^(re|fwd?|fw)\\s*:\\s*', '', 'gi')) "
                            f"  ILIKE :normalized_pattern"
                            f") "
                            f"LIMIT 1"
                        ),
                        {**params, "normalized_pattern": f"%{normalized}%"},
                    )
                    existing = result.first()

                    if existing:
                        thread_id = existing.thread_id
                        thread_position = (existing.max_pos or 0) + 1
                    else:
                        thread_id = _make_thread_id(normalized)
                        thread_position = 0

                    logger.info(
                        "threading.by_subject",
                        doc_id=doc_id,
                        thread_id=thread_id,
                        existing_found=existing is not None,
                    )

            # If we still have no thread_id, use the message_id itself
            if not thread_id:
                if message_id:
                    thread_id = _make_thread_id(message_id)
                else:
                    thread_id = _make_thread_id(f"{doc_id}_{subject}")
                thread_position = 0

            # Update the document record
            conn.execute(
                text(
                    """
                    UPDATE documents
                    SET thread_id = :thread_id,
                        thread_position = :thread_position,
                        message_id = :message_id,
                        in_reply_to = :in_reply_to,
                        references_ = :references_,
                        updated_at = now()
                    WHERE id = :doc_id
                    """
                ),
                {
                    "doc_id": doc_id,
                    "thread_id": thread_id,
                    "thread_position": thread_position,
                    "message_id": message_id or None,
                    "in_reply_to": in_reply_to or None,
                    "references_": references or None,
                },
            )
            conn.commit()

        logger.info(
            "threading.assigned",
            doc_id=doc_id,
            thread_id=thread_id,
            position=thread_position,
        )
        return thread_id, thread_position

    @staticmethod
    def detect_inclusive_emails(engine, matter_id: str | None = None) -> int:
        """Mark inclusive emails in each thread.

        An inclusive email is the one with the longest body and latest date
        in its thread (heuristic: it includes the full conversation).

        Returns the number of emails marked as inclusive.
        """
        from sqlalchemy import text

        matter_clause = ""
        params: dict = {}
        if matter_id:
            matter_clause = " AND d.matter_id = :matter_id"
            params["matter_id"] = matter_id

        with engine.connect() as conn:
            # Reset existing inclusive flags
            conn.execute(
                text(
                    f"UPDATE documents SET is_inclusive = false "
                    f"WHERE thread_id IS NOT NULL"
                    f"{matter_clause.replace('d.', '')}"
                ),
                params,
            )

            # Mark the email with the latest date per thread as inclusive
            result = conn.execute(
                text(
                    f"""
                    UPDATE documents
                    SET is_inclusive = true, updated_at = now()
                    WHERE id IN (
                        SELECT DISTINCT ON (d.thread_id) d.id
                        FROM documents d
                        WHERE d.thread_id IS NOT NULL
                        AND d.document_type = 'email'
                        {matter_clause}
                        ORDER BY d.thread_id, d.created_at DESC
                    )
                    """
                ),
                params,
            )
            inclusive_count = result.rowcount
            conn.commit()

        logger.info(
            "threading.inclusive_detected",
            inclusive_count=inclusive_count,
            matter_id=matter_id,
        )
        return inclusive_count
