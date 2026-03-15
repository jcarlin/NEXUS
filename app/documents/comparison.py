"""Document text comparison using difflib.

Computes line-level diffs between two document texts using
``difflib.SequenceMatcher``.  Results are returned as a list of
``DiffBlock`` dicts suitable for serialisation via the schemas module.
"""

from __future__ import annotations

import difflib

import structlog

from app.common.storage import StorageClient

logger = structlog.get_logger(__name__)

MAX_DIFF_CHARS = 50_000  # Limit to 50K chars per document to avoid memory issues


def compute_text_diff(text_a: str, text_b: str) -> tuple[list[dict], bool]:
    """Compute diff blocks between two texts using ``SequenceMatcher``.

    Returns ``(blocks, truncated)`` where *blocks* is a list of dicts with
    keys ``op``, ``left_start``, ``left_end``, ``right_start``, ``right_end``,
    ``left_text``, ``right_text``.

    When either text exceeds ``MAX_DIFF_CHARS`` it is truncated and
    *truncated* is set to ``True``.
    """
    truncated = len(text_a) > MAX_DIFF_CHARS or len(text_b) > MAX_DIFF_CHARS
    text_a = text_a[:MAX_DIFF_CHARS]
    text_b = text_b[:MAX_DIFF_CHARS]

    lines_a = text_a.splitlines(keepends=True)
    lines_b = text_b.splitlines(keepends=True)

    matcher = difflib.SequenceMatcher(None, lines_a, lines_b)
    blocks: list[dict] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        blocks.append(
            {
                "op": tag,
                "left_start": i1,
                "left_end": i2,
                "right_start": j1,
                "right_end": j2,
                "left_text": "".join(lines_a[i1:i2]),
                "right_text": "".join(lines_b[j1:j2]),
            }
        )

    return blocks, truncated


async def extract_document_text(
    job_id: str,
    filename: str,
    storage: StorageClient,
) -> str:
    """Read parsed text for a document from MinIO.

    Documents are stored after parsing at ``parsed/{job_id}/{filename}.md``
    (Docling markdown output).  Falls back to ``.txt`` if markdown is
    unavailable.

    Raises ``FileNotFoundError`` if no parsed text is found.
    """
    base = filename.rsplit(".", 1)[0] if "." in filename else filename

    # Try markdown first (Docling output), then plain text
    for ext in ("md", "txt"):
        key = f"parsed/{job_id}/{base}.{ext}"
        try:
            data = await storage.download_bytes(key)
            return data.decode("utf-8", errors="replace")
        except Exception:
            logger.debug("comparison.text_variant_unavailable", key=key, exc_info=True)
            continue

    raise FileNotFoundError(f"No parsed text found for job {job_id}")
