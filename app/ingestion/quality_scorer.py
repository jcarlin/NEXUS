"""Heuristic chunk quality scoring for ingestion pipeline.

Scores each chunk on coherence, information density, completeness, and
length — all via fast heuristics (~5ms/chunk, no LLM, no external calls).

Feature-flagged: ``ENABLE_CHUNK_QUALITY_SCORING`` (default ``false``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Boilerplate patterns common in legal documents
# ---------------------------------------------------------------------------

_BOILERPLATE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bCONFIDENTIAL\b", re.IGNORECASE),
    re.compile(r"\bPRIVILEGED AND CONFIDENTIAL\b", re.IGNORECASE),
    re.compile(r"Page\s+\d+\s+of\s+\d+", re.IGNORECASE),
    re.compile(r"\bEXHIBIT\s+[A-Z0-9]+\b"),
    re.compile(r"\bTABLE OF CONTENTS\b", re.IGNORECASE),
    re.compile(r"\bATTORNEY.CLIENT PRIVILEGE\b", re.IGNORECASE),
    re.compile(r"\bWORK PRODUCT\b", re.IGNORECASE),
    re.compile(r"\bDO NOT DISTRIBUTE\b", re.IGNORECASE),
    re.compile(r"\bFOR INTERNAL USE ONLY\b", re.IGNORECASE),
    re.compile(r"^\s*[-_=]{10,}\s*$", re.MULTILINE),
]

# Markdown table line pattern
_TABLE_LINE_RE = re.compile(r"^\s*\|", re.MULTILINE)


@dataclass
class ChunkQualityScore:
    """Quality assessment for a single chunk."""

    overall: float  # 0.0–1.0 composite
    coherence: float  # Sentence structure quality
    information_density: float  # Substantive vs boilerplate ratio
    completeness: float  # No truncated sentences/tables
    length_score: float  # Reasonable token count


def score_chunk(
    text: str,
    token_count: int,
    entity_count: int = 0,
) -> ChunkQualityScore:
    """Score chunk quality using fast heuristics.

    Parameters
    ----------
    text:
        The chunk text.
    token_count:
        Pre-computed token count for the chunk.
    entity_count:
        Number of named entities found in this chunk (0 if unavailable).

    Returns
    -------
    ChunkQualityScore with per-dimension and composite scores.
    """
    if not text or not text.strip():
        return ChunkQualityScore(
            overall=0.0,
            coherence=0.0,
            information_density=0.0,
            completeness=0.0,
            length_score=0.0,
        )

    coherence = _score_coherence(text)
    information_density = _score_information_density(text, entity_count)
    completeness = _score_completeness(text)
    length_score = _score_length(token_count)

    overall = 0.30 * coherence + 0.35 * information_density + 0.20 * completeness + 0.15 * length_score

    return ChunkQualityScore(
        overall=round(overall, 4),
        coherence=round(coherence, 4),
        information_density=round(information_density, 4),
        completeness=round(completeness, 4),
        length_score=round(length_score, 4),
    )


# ---------------------------------------------------------------------------
# Dimension scorers
# ---------------------------------------------------------------------------


def _score_coherence(text: str) -> float:
    """Score sentence structure quality (0.0–1.0).

    - Multiple well-formed sentences → high score
    - Single sentence → moderate score
    - No sentence endings → low score
    - Very short avg sentence length (<5 words) suggests list/index
    - Very long avg sentence length (>50 words) suggests OCR run-on
    """
    sentences = re.split(r"[.!?]\s", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return 0.1

    n_sentences = len(sentences)
    avg_words = sum(len(s.split()) for s in sentences) / max(n_sentences, 1)

    # Sentence count score: 1 sentence = 0.4, 2 = 0.6, 3+ = 0.8-1.0
    if n_sentences >= 5:
        count_score = 1.0
    elif n_sentences >= 3:
        count_score = 0.8
    elif n_sentences >= 2:
        count_score = 0.6
    else:
        count_score = 0.4

    # Average sentence length score
    if avg_words < 3:
        length_score = 0.2  # Fragments / list items
    elif avg_words < 5:
        length_score = 0.4  # Short / index-like
    elif avg_words <= 50:
        length_score = 1.0  # Good range
    elif avg_words <= 80:
        length_score = 0.6  # Getting long
    else:
        length_score = 0.3  # OCR run-on

    return 0.6 * count_score + 0.4 * length_score


def _score_information_density(text: str, entity_count: int = 0) -> float:
    """Score substantive content vs boilerplate (0.0–1.0).

    Checks for boilerplate patterns, table-only content, and entity density.
    """
    text_stripped = text.strip()
    total_chars = len(text_stripped)

    if total_chars == 0:
        return 0.0

    # Count boilerplate matches
    boilerplate_chars = 0
    for pattern in _BOILERPLATE_PATTERNS:
        for match in pattern.finditer(text):
            boilerplate_chars += len(match.group())

    boilerplate_ratio = min(boilerplate_chars / total_chars, 1.0)

    # Table-only detection: if >80% of lines are table lines
    lines = text_stripped.split("\n")
    non_empty_lines = [ln for ln in lines if ln.strip()]
    if non_empty_lines:
        table_lines = sum(1 for ln in non_empty_lines if _TABLE_LINE_RE.match(ln))
        table_ratio = table_lines / len(non_empty_lines)
    else:
        table_ratio = 0.0

    # Base score from boilerplate ratio
    base_score = 1.0 - boilerplate_ratio

    # Penalize table-only chunks (moderate, tables still have value)
    if table_ratio > 0.8:
        base_score *= 0.6

    # Entity density bonus (if available)
    if entity_count > 0:
        # Normalize: 1 entity = small bonus, 3+ = max bonus
        entity_bonus = min(entity_count / 3.0, 1.0) * 0.2
        base_score = min(base_score + entity_bonus, 1.0)

    return max(base_score, 0.0)


def _score_completeness(text: str) -> float:
    """Score whether the chunk has complete sentences (0.0–1.0).

    Penalizes chunks that start or end mid-sentence.
    """
    text_stripped = text.strip()
    if not text_stripped:
        return 0.0

    score = 1.0

    # Check if text ends with sentence-ending punctuation
    if not re.search(r"[.!?:;)\]\"']\s*$", text_stripped):
        score -= 0.3  # Truncated ending

    # Check if text starts with a lowercase letter (mid-sentence start)
    first_char = text_stripped[0]
    if first_char.islower():
        score -= 0.2  # Mid-sentence start

    # Check for truncated tables (odd number of | delimiters on last line)
    last_line = text_stripped.split("\n")[-1].strip()
    if last_line.startswith("|") and not last_line.endswith("|"):
        score -= 0.3  # Truncated table row

    return max(score, 0.0)


def _score_length(token_count: int) -> float:
    """Score chunk length (0.0–1.0).

    Very short chunks (<50 tokens) are likely fragments.
    Very long chunks (>600 tokens) may contain too much.
    Ideal range: 100-512 tokens.
    """
    if token_count < 20:
        return 0.1
    if token_count < 50:
        return 0.3
    if token_count < 100:
        return 0.6
    if token_count <= 512:
        return 1.0
    if token_count <= 600:
        return 0.8
    return 0.5
