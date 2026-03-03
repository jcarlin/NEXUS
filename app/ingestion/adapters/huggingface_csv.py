"""HuggingFace CSV/Parquet adapter — import pre-OCR'd text datasets."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import structlog

from app.ingestion.bulk_import import ImportDocument, compute_content_hash

logger = structlog.get_logger(__name__)

# Regex to extract Bates number components from filenames like:
#   TEXT/HOUSE_OVERSIGHT_020367.txt
#   TEXT/DOJ_RELEASE_001234_2.txt
_BATES_RE = re.compile(r"^(?:TEXT|IMAGES)/([A-Z_]+?)_(\d{4,})(?:_\d+)?\.(?:txt|jpg|png)$")

# Release source mapping from Bates prefix
_RELEASE_SOURCES: dict[str, str] = {
    "HOUSE_OVERSIGHT": "House Oversight Nov 2025",
    "DOJ": "Department of Justice",
    "FBI": "Federal Bureau of Investigation",
    "CBP": "Customs and Border Protection",
    "BOP": "Bureau of Prisons",
}

# Control characters to strip (keep \n=0x0A, \t=0x09)
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# 3+ consecutive blank lines → 2
_MULTI_BLANK_RE = re.compile(r"\n{4,}")


def _clean_ocr_text(text: str) -> str:
    """Lightweight OCR text cleaning.

    - Strip control characters (keep newlines and tabs)
    - Collapse 3+ consecutive blank lines to 2
    """
    text = _CONTROL_CHAR_RE.sub("", text)
    text = _MULTI_BLANK_RE.sub("\n\n\n", text)
    return text.strip()


def _parse_bates_metadata(filename: str) -> dict[str, str]:
    """Extract Bates number metadata from a filename.

    Returns dict with ``bates_prefix``, ``bates_number``,
    ``release_source``, and ``original_path`` if the filename matches
    the expected pattern.  Otherwise returns only ``original_path``.
    """
    meta: dict[str, str] = {"original_path": filename}
    match = _BATES_RE.match(filename)
    if match:
        prefix, number = match.group(1), match.group(2)
        meta["bates_prefix"] = prefix
        meta["bates_number"] = number
        meta["release_source"] = _RELEASE_SOURCES.get(prefix, prefix)
    return meta


class HuggingFaceCSVAdapter:
    """Read a HuggingFace CSV or Parquet file and yield ``ImportDocument`` instances.

    Expected columns: ``filename`` and ``text``.  Rows where
    ``filename`` starts with ``IMAGES/`` are skipped (image-only OCR
    entries have no useful text).  Documents with fewer than 50
    characters after cleaning are also skipped.
    """

    _MIN_TEXT_LENGTH = 50

    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path

    @property
    def name(self) -> str:
        return "huggingface_csv"

    def iter_documents(self, *, limit: int | None = None) -> Iterator[ImportDocument]:
        suffix = self._file_path.suffix.lower()
        if suffix == ".parquet":
            df = pd.read_parquet(self._file_path)
        else:
            df = pd.read_csv(self._file_path)

        if "filename" not in df.columns or "text" not in df.columns:
            raise ValueError(f"Dataset must have 'filename' and 'text' columns, " f"got: {list(df.columns)}")

        count = 0
        skipped_images = 0
        skipped_short = 0

        for row in df.itertuples(index=False):
            if limit is not None and count >= limit:
                break

            filename: str = str(row.filename)
            raw_text: str = str(row.text) if pd.notna(row.text) else ""

            # Skip image-only rows
            if filename.startswith("IMAGES/"):
                skipped_images += 1
                continue

            # Clean OCR text
            cleaned = _clean_ocr_text(raw_text)
            if len(cleaned) < self._MIN_TEXT_LENGTH:
                skipped_short += 1
                continue

            metadata = _parse_bates_metadata(filename)
            content_hash = compute_content_hash(cleaned)

            # Use the leaf filename (strip TEXT/ prefix)
            leaf_name = filename.split("/", 1)[-1] if "/" in filename else filename

            yield ImportDocument(
                source_id=filename,
                filename=leaf_name,
                text=cleaned,
                content_hash=content_hash,
                source="huggingface_csv",
                doc_type="document",
                page_count=1,
                metadata=metadata,
            )
            count += 1

        logger.info(
            "huggingface_csv.scan_complete",
            yielded=count,
            skipped_images=skipped_images,
            skipped_short=skipped_short,
        )
