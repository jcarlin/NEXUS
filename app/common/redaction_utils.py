"""Redaction utilities for sanitising error messages before they reach audit logs.

Legal compliance: ai_audit_log.error_message must never contain raw document text,
PII, or privileged material. This module strips quoted content (which often contains
document fragments), common PII patterns, and enforces a length cap.
"""

from __future__ import annotations

import re

import structlog

logger = structlog.get_logger(__name__)

_MAX_ERROR_LENGTH = 500

# Patterns that may contain document text fragments
_QUOTED_DOUBLE = re.compile(r'"[^"]*"')
_QUOTED_SINGLE = re.compile(r"'[^']*'")

# PII patterns
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PHONE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def redact_error_message(raw: str | None) -> str | None:
    """Sanitise an error message for safe storage in audit logs.

    - Returns None unchanged.
    - Strips quoted content (single and double quotes) which may embed document text.
    - Redacts SSN, phone number, and email patterns.
    - Truncates to 500 characters.
    """
    if raw is None:
        return None

    try:
        msg = raw
        # Strip quoted content (double quotes first, then single)
        msg = _QUOTED_DOUBLE.sub("[REDACTED]", msg)
        msg = _QUOTED_SINGLE.sub("[REDACTED]", msg)
        # Redact PII patterns
        msg = _SSN.sub("[SSN]", msg)
        msg = _PHONE.sub("[PHONE]", msg)
        msg = _EMAIL.sub("[EMAIL]", msg)
        # Truncate
        if len(msg) > _MAX_ERROR_LENGTH:
            msg = msg[: _MAX_ERROR_LENGTH - 3] + "..."
        return msg
    except Exception:
        logger.warning("redaction_utils.redact_failed", exc_info=True)
        return raw[:_MAX_ERROR_LENGTH] if len(raw) > _MAX_ERROR_LENGTH else raw
