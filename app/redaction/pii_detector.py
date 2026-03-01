"""Regex-based PII/PHI detection for document text.

Fast pattern matching for structured PII (SSN, phone, email, DOB) and
medical keyword detection.  No external models or service calls.
"""

from __future__ import annotations

import re

from app.redaction.schemas import PIICategory, PIIDetection

# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")

_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")

# MM/DD/YYYY or MM-DD-YYYY
_DOB_RE = re.compile(r"\b(?:0[1-9]|1[0-2])[/\-](?:0[1-9]|[12]\d|3[01])[/\-](?:19|20)\d{2}\b")

# ISO format YYYY-MM-DD
_DOB_ISO_RE = re.compile(r"\b(?:19|20)\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])\b")

# Medical / HIPAA keywords (case-insensitive substring match)
_MEDICAL_KEYWORDS: list[str] = [
    "diagnosis",
    "prognosis",
    "prescription",
    "hipaa",
    "patient",
    "medical record",
    "treatment plan",
    "icd-10",
    "icd-9",
    "medication",
    "clinical",
    "psychiatric",
    "psychological",
    "substance abuse",
    "hiv",
    "std",
    "disability",
    "blood type",
    "allergies",
    "health insurance",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_pii(text: str) -> list[PIIDetection]:
    """Run all PII patterns against *text* and return detections.

    Returns a list of ``PIIDetection`` instances sorted by start offset.
    Regex matches get confidence=1.0; keyword matches get confidence=0.9.
    """
    detections: list[PIIDetection] = []

    # --- Regex-based patterns (confidence = 1.0) ---
    for match in _SSN_RE.finditer(text):
        detections.append(
            PIIDetection(
                text=match.group(),
                category=PIICategory.SSN,
                confidence=1.0,
                start=match.start(),
                end=match.end(),
            )
        )

    for match in _PHONE_RE.finditer(text):
        detections.append(
            PIIDetection(
                text=match.group(),
                category=PIICategory.PHONE,
                confidence=1.0,
                start=match.start(),
                end=match.end(),
            )
        )

    for match in _EMAIL_RE.finditer(text):
        detections.append(
            PIIDetection(
                text=match.group(),
                category=PIICategory.EMAIL,
                confidence=1.0,
                start=match.start(),
                end=match.end(),
            )
        )

    for match in _DOB_RE.finditer(text):
        detections.append(
            PIIDetection(
                text=match.group(),
                category=PIICategory.DOB,
                confidence=1.0,
                start=match.start(),
                end=match.end(),
            )
        )

    for match in _DOB_ISO_RE.finditer(text):
        detections.append(
            PIIDetection(
                text=match.group(),
                category=PIICategory.DOB,
                confidence=1.0,
                start=match.start(),
                end=match.end(),
            )
        )

    # --- Keyword-based medical detection (confidence = 0.9) ---
    text_lower = text.lower()
    for keyword in _MEDICAL_KEYWORDS:
        start = 0
        while True:
            idx = text_lower.find(keyword, start)
            if idx == -1:
                break
            detections.append(
                PIIDetection(
                    text=text[idx : idx + len(keyword)],
                    category=PIICategory.MEDICAL,
                    confidence=0.9,
                    start=idx,
                    end=idx + len(keyword),
                )
            )
            start = idx + len(keyword)

    # Sort by start offset for deterministic output
    detections.sort(key=lambda d: d.start)
    return detections
