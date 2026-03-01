"""Tests for the document parser routing and plaintext backend."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.ingestion.parser import PARSER_ROUTES, DocumentParser


def test_parser_routes_cover_expected_extensions():
    """All expected file types should have a routing entry."""
    expected = {".pdf", ".docx", ".xlsx", ".pptx", ".html", ".txt", ".eml", ".zip"}
    assert expected.issubset(set(PARSER_ROUTES.keys()))


def test_parse_plaintext():
    """Parsing a .txt file should return the file content."""
    parser = DocumentParser()
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write("This is a test document.\nWith two lines.")
        f.flush()
        tmp_path = Path(f.name)

    try:
        result = parser.parse(tmp_path, "test.txt")
        assert "This is a test document." in result.text
        assert result.page_count == 1
        assert len(result.pages) == 1
        assert result.pages[0].page_number == 1
        assert result.metadata["format"] == ".txt"
    finally:
        tmp_path.unlink(missing_ok=True)


def test_parse_missing_file_raises():
    parser = DocumentParser()
    with pytest.raises(FileNotFoundError):
        parser.parse(Path("/nonexistent/file.txt"), "file.txt")


def test_parse_unsupported_extension_raises():
    parser = DocumentParser()
    with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
        tmp_path = Path(f.name)

    try:
        with pytest.raises(ValueError, match="Unrecognised file extension"):
            parser.parse(tmp_path, "file.xyz")
    finally:
        tmp_path.unlink(missing_ok=True)


def test_parse_unsupported_doc_format_raises():
    """Legacy .doc format should raise with a clear message."""
    parser = DocumentParser()
    with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as f:
        f.write(b"fake doc content")
        tmp_path = Path(f.name)

    try:
        with pytest.raises(ValueError, match="not supported"):
            parser.parse(tmp_path, "legacy.doc")
    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Edge-case: corrupted / zero-byte / timeout failures (Sprint 8 L4)
# ---------------------------------------------------------------------------


def test_parse_corrupted_pdf_raises():
    """A file with .pdf extension but invalid content should raise, not return empty text."""
    parser = DocumentParser()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"not a pdf")
        tmp_path = Path(f.name)

    try:
        with pytest.raises(Exception):
            parser.parse(tmp_path, "corrupted.pdf")
    finally:
        tmp_path.unlink(missing_ok=True)


def test_parse_zero_byte_file_raises():
    """A 0-byte file should raise an exception, not silently return empty text."""
    parser = DocumentParser()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        # Write nothing — 0 bytes
        tmp_path = Path(f.name)

    try:
        with pytest.raises(Exception):
            parser.parse(tmp_path, "empty.pdf")
    finally:
        tmp_path.unlink(missing_ok=True)


def test_parse_docling_timeout_propagates():
    """A TimeoutError from Docling's convert() should propagate, not be caught silently."""
    parser = DocumentParser()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"fake pdf content")
        tmp_path = Path(f.name)

    try:
        with patch.object(parser, "_get_converter") as mock_converter:
            mock_converter.return_value.convert.side_effect = TimeoutError("Docling timed out")
            with pytest.raises(TimeoutError, match="Docling timed out"):
                parser.parse(tmp_path, "slow.pdf")
    finally:
        tmp_path.unlink(missing_ok=True)
