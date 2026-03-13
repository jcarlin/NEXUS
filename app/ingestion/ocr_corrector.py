"""OCR error correction for post-parse text cleanup.

Applies regex-based corrections for common OCR misrecognitions
(ligatures, digit/letter confusion, broken words). Optionally uses
LLM for high-value documents when enabled.
"""

from __future__ import annotations

import re

import structlog

logger = structlog.get_logger(__name__)

# Common OCR substitution patterns: (wrong_pattern, replacement)
# Order matters — more specific patterns first.
_OCR_PATTERNS: list[tuple[str, str]] = [
    # Ligature artifacts
    (r"ﬁ", "fi"),
    (r"ﬂ", "fl"),
    (r"ﬀ", "ff"),
    (r"ﬃ", "ffi"),
    (r"ﬄ", "ffl"),
    # Common digit/letter confusion
    (r"\bl\b(?=\d)", "1"),  # standalone 'l' before digits → '1'
    (r"(?<=\d)O(?=\d)", "0"),  # 'O' between digits → '0'
    (r"(?<=\d)l(?=\d)", "1"),  # 'l' between digits → '1'
    (r"(?<=\d)S(?=\d)", "5"),  # 'S' between digits → '5'
    # Broken words (line-end hyphenation artifacts)
    (r"(\w+)-\s*\n\s*(\w+)", r"\1\2"),
    # Multiple spaces → single space
    (r"[ \t]{2,}", " "),
    # Common legal OCR errors
    (r"\bPlaintitf\b", "Plaintiff"),
    (r"\bDefendanr\b", "Defendant"),
    (r"\bAttomey\b", "Attorney"),
    (r"\bJudgrnent\b", "Judgment"),
    (r"\bExhibii\b", "Exhibit"),
    (r"\bTestirnony\b", "Testimony"),
    (r"\bDeposiiion\b", "Deposition"),
    (r"\bAffidavii\b", "Affidavit"),
    (r"\bSubpcena\b", "Subpoena"),
    (r"\bStatuie\b", "Statute"),
]

# Pre-compile patterns for performance
_COMPILED_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(pattern), replacement) for pattern, replacement in _OCR_PATTERNS
]


class OCRCorrector:
    """Corrects common OCR errors in parsed document text.

    Two correction modes:
    1. **Regex-based** (default): Fast, deterministic pattern matching for
       known OCR misrecognitions. Always applied.
    2. **LLM-assisted** (optional): Uses the configured LLM to fix remaining
       errors in high-value documents. Only when ``use_llm=True``.
    """

    def __init__(self, use_llm: bool = False) -> None:
        self._use_llm = use_llm

    def correct(self, text: str) -> tuple[str, int]:
        """Apply OCR corrections to text.

        Returns:
            Tuple of (corrected_text, correction_count).
        """
        if not text:
            return text, 0

        corrected = text
        total_corrections = 0

        for pattern, replacement in _COMPILED_PATTERNS:
            corrected, count = pattern.subn(replacement, corrected)
            total_corrections += count

        if total_corrections > 0:
            logger.info(
                "ocr_corrector.regex_corrections",
                correction_count=total_corrections,
                text_length=len(text),
            )

        return corrected, total_corrections

    async def correct_with_llm(self, text: str, chunk_size: int = 2000) -> str:
        """Use LLM to fix OCR errors in text chunks.

        Splits text into chunks, sends each to the LLM for correction,
        and reassembles. Only called when ``use_llm=True`` in constructor.
        """
        if not self._use_llm or not text:
            return text

        from app.dependencies import get_llm
        from app.ingestion.prompts import OCR_CORRECTION_PROMPT

        llm = get_llm()

        # Process in chunks to stay within context limits
        chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
        corrected_chunks = []

        for chunk in chunks:
            prompt = OCR_CORRECTION_PROMPT.format(chunk=chunk)
            result = await llm.complete(
                [{"role": "user", "content": prompt}],
                max_tokens=len(chunk) + 200,
                temperature=0.0,
                node_name="ocr_correction",
            )
            corrected_chunks.append(result.strip())

        return "".join(corrected_chunks)
