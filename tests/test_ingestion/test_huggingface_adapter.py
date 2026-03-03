"""Tests for the HuggingFace CSV/Parquet adapter."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.ingestion.adapters.huggingface_csv import (
    HuggingFaceCSVAdapter,
    _clean_ocr_text,
    _parse_bates_metadata,
)
from app.ingestion.bulk_import import DatasetAdapter

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    """Write a CSV fixture and return its path."""
    df = pd.DataFrame(rows)
    csv_path = path / "test_dataset.csv"
    df.to_csv(csv_path, index=False)
    return csv_path


def _make_parquet(path: Path, rows: list[dict[str, str]]) -> Path:
    """Write a Parquet fixture and return its path."""
    df = pd.DataFrame(rows)
    pq_path = path / "test_dataset.parquet"
    df.to_parquet(pq_path, index=False)
    return pq_path


_SAMPLE_ROWS = [
    {
        "filename": "TEXT/HOUSE_OVERSIGHT_020367.txt",
        "text": "Deposition of John Doe taken on January 15, 2008 at the offices of Smith & Associates.",
    },
    {
        "filename": "TEXT/HOUSE_OVERSIGHT_020368.txt",
        "text": "Flight manifest record showing departure from Teterboro Airport on March 3, 2005.",
    },
    {
        "filename": "TEXT/DOJ_RELEASE_001234.txt",
        "text": "Federal Bureau of Investigation interview summary regarding subject activities in Palm Beach County.",
    },
    {"filename": "IMAGES/HOUSE_OVERSIGHT_020369.jpg", "text": ""},
    {"filename": "TEXT/HOUSE_OVERSIGHT_020370.txt", "text": "Short"},
]


# ---------------------------------------------------------------------------
# 1. Protocol compliance
# ---------------------------------------------------------------------------


def test_adapter_satisfies_protocol(tmp_path: Path) -> None:
    """HuggingFaceCSVAdapter should satisfy the DatasetAdapter protocol."""
    csv_path = _make_csv(tmp_path, _SAMPLE_ROWS)
    adapter = HuggingFaceCSVAdapter(file_path=csv_path)
    assert isinstance(adapter, DatasetAdapter)
    assert adapter.name == "huggingface_csv"


# ---------------------------------------------------------------------------
# 2. Reads CSV
# ---------------------------------------------------------------------------


def test_reads_csv(tmp_path: Path) -> None:
    """Adapter should read CSV files and yield ImportDocument instances."""
    csv_path = _make_csv(tmp_path, _SAMPLE_ROWS)
    adapter = HuggingFaceCSVAdapter(file_path=csv_path)

    docs = list(adapter.iter_documents())

    # 5 rows: 3 TEXT with sufficient length, 1 IMAGES (skipped), 1 short (skipped)
    assert len(docs) == 3
    assert docs[0].source == "huggingface_csv"
    assert docs[0].doc_type == "document"
    assert docs[0].page_count == 1
    assert docs[0].filename == "HOUSE_OVERSIGHT_020367.txt"
    assert "Deposition" in docs[0].text


# ---------------------------------------------------------------------------
# 3. Reads Parquet
# ---------------------------------------------------------------------------


def test_reads_parquet(tmp_path: Path) -> None:
    """Adapter should read Parquet files and yield ImportDocument instances."""
    pq_path = _make_parquet(tmp_path, _SAMPLE_ROWS)
    adapter = HuggingFaceCSVAdapter(file_path=pq_path)

    docs = list(adapter.iter_documents())
    assert len(docs) == 3
    assert docs[1].filename == "HOUSE_OVERSIGHT_020368.txt"


# ---------------------------------------------------------------------------
# 4. Skips image rows
# ---------------------------------------------------------------------------


def test_skips_image_rows(tmp_path: Path) -> None:
    """Rows with IMAGES/ prefix should be filtered out."""
    rows = [
        {
            "filename": "IMAGES/HOUSE_OVERSIGHT_020369.jpg",
            "text": "Some OCR noise from an image that somehow has text.",
        },
        {
            "filename": "IMAGES/HOUSE_OVERSIGHT_020370.png",
            "text": "Another image row with enough text to pass length check.",
        },
        {
            "filename": "TEXT/HOUSE_OVERSIGHT_020371.txt",
            "text": "This is a real text document with sufficient content for the adapter to process.",
        },
    ]
    csv_path = _make_csv(tmp_path, rows)
    adapter = HuggingFaceCSVAdapter(file_path=csv_path)

    docs = list(adapter.iter_documents())
    assert len(docs) == 1
    assert docs[0].filename == "HOUSE_OVERSIGHT_020371.txt"


# ---------------------------------------------------------------------------
# 5. Skips short text
# ---------------------------------------------------------------------------


def test_skips_short_text(tmp_path: Path) -> None:
    """Documents with fewer than 50 chars after cleaning should be skipped."""
    rows = [
        {"filename": "TEXT/DOC_001.txt", "text": "Too short"},
        {"filename": "TEXT/DOC_002.txt", "text": ""},
        {"filename": "TEXT/DOC_003.txt", "text": "A" * 49},
        {
            "filename": "TEXT/DOC_004.txt",
            "text": "This document has enough text to pass the minimum length threshold for import.",
        },
    ]
    csv_path = _make_csv(tmp_path, rows)
    adapter = HuggingFaceCSVAdapter(file_path=csv_path)

    docs = list(adapter.iter_documents())
    assert len(docs) == 1
    assert docs[0].filename == "DOC_004.txt"


# ---------------------------------------------------------------------------
# 6. Extracts Bates metadata
# ---------------------------------------------------------------------------


def test_extracts_bates_metadata() -> None:
    """_parse_bates_metadata should extract prefix, number, and release source."""
    meta = _parse_bates_metadata("TEXT/HOUSE_OVERSIGHT_020367.txt")
    assert meta["bates_prefix"] == "HOUSE_OVERSIGHT"
    assert meta["bates_number"] == "020367"
    assert meta["release_source"] == "House Oversight Nov 2025"
    assert meta["original_path"] == "TEXT/HOUSE_OVERSIGHT_020367.txt"

    # DOJ prefix
    meta_doj = _parse_bates_metadata("TEXT/DOJ_RELEASE_001234.txt")
    assert meta_doj["bates_prefix"] == "DOJ_RELEASE"
    assert meta_doj["bates_number"] == "001234"

    # Unknown prefix — falls back to prefix string
    meta_unknown = _parse_bates_metadata("TEXT/CUSTOM_PREFIX_009999.txt")
    assert meta_unknown["bates_prefix"] == "CUSTOM_PREFIX"
    assert meta_unknown["release_source"] == "CUSTOM_PREFIX"

    # Non-matching filename — only original_path
    meta_plain = _parse_bates_metadata("some_random_file.txt")
    assert "bates_prefix" not in meta_plain
    assert meta_plain["original_path"] == "some_random_file.txt"


# ---------------------------------------------------------------------------
# 7. Cleans OCR text
# ---------------------------------------------------------------------------


def test_cleans_ocr_text() -> None:
    """_clean_ocr_text should strip control chars and collapse blank lines."""
    # Control characters stripped
    text_with_control = "Hello\x00World\x07Test\x1fEnd"
    cleaned = _clean_ocr_text(text_with_control)
    assert "\x00" not in cleaned
    assert "\x07" not in cleaned
    assert "\x1f" not in cleaned
    assert "HelloWorldTestEnd" == cleaned

    # Newlines and tabs preserved
    text_with_whitespace = "Line 1\nLine 2\tTabbed"
    cleaned = _clean_ocr_text(text_with_whitespace)
    assert "\n" in cleaned
    assert "\t" in cleaned

    # 4+ blank lines collapsed to 2 (3 newlines = 2 blank lines)
    text_with_blanks = "Para 1\n\n\n\n\n\nPara 2"
    cleaned = _clean_ocr_text(text_with_blanks)
    assert "\n\n\n\n" not in cleaned
    assert "Para 1\n\n\nPara 2" == cleaned


# ---------------------------------------------------------------------------
# 8. Respects limit
# ---------------------------------------------------------------------------


def test_respects_limit(tmp_path: Path) -> None:
    """limit=N should yield exactly N documents from a larger dataset."""
    rows = [
        {
            "filename": f"TEXT/DOC_{i:04d}.txt",
            "text": f"Document number {i} with enough text to pass the minimum length threshold for import processing.",
        }
        for i in range(20)
    ]
    csv_path = _make_csv(tmp_path, rows)
    adapter = HuggingFaceCSVAdapter(file_path=csv_path)

    docs = list(adapter.iter_documents(limit=5))
    assert len(docs) == 5

    # Without limit, all 20 should be returned
    all_docs = list(adapter.iter_documents())
    assert len(all_docs) == 20
