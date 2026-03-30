"""Tests for the document parser routing and plaintext backend."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

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


# ---------------------------------------------------------------------------
# OCR auto-detection (ENABLE_DOCLING_OCR=auto)
# ---------------------------------------------------------------------------


class TestHasTextLayer:
    """Tests for _has_text_layer pre-flight check."""

    def test_returns_true_for_text_pdf(self, tmp_path):
        """A PDF with embedded text should return True."""
        parser = DocumentParser()
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=2)

        mock_textpage = MagicMock()
        mock_textpage.get_text_range.return_value = "A" * 200  # plenty of text
        mock_page = MagicMock()
        mock_page.get_textpage.return_value = mock_textpage
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)

        with patch("app.ingestion.parser.pdfium", create=True) as mock_pdfium:
            # Patch at module level since _has_text_layer imports pypdfium2
            with patch.dict("sys.modules", {"pypdfium2": mock_pdfium}):
                mock_pdfium.PdfDocument.return_value = mock_doc
                result = parser._has_text_layer(tmp_path / "test.pdf")
        assert result is True

    def test_returns_false_for_scanned_pdf(self, tmp_path):
        """A PDF with no text layer should return False."""
        parser = DocumentParser()
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=2)

        mock_textpage = MagicMock()
        mock_textpage.get_text_range.return_value = ""  # no text
        mock_page = MagicMock()
        mock_page.get_textpage.return_value = mock_textpage
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)

        with patch.dict("sys.modules", {"pypdfium2": MagicMock()}) as mock_modules:
            mock_pdfium = mock_modules["pypdfium2"]
            mock_pdfium.PdfDocument.return_value = mock_doc
            result = parser._has_text_layer(tmp_path / "scan.pdf")
        assert result is False

    def test_returns_false_on_exception(self, tmp_path):
        """If pypdfium2 can't read the file, fall back to False (needs OCR)."""
        parser = DocumentParser()
        with patch.dict("sys.modules", {"pypdfium2": MagicMock()}) as mock_modules:
            mock_pdfium = mock_modules["pypdfium2"]
            mock_pdfium.PdfDocument.side_effect = RuntimeError("corrupt")
            result = parser._has_text_layer(tmp_path / "bad.pdf")
        assert result is False


class TestResolveOcr:
    """Tests for _resolve_ocr routing logic."""

    def test_auto_mode_skips_ocr_for_text_pdf(self):
        parser = DocumentParser()
        with (
            patch("app.config.Settings") as mock_settings,
            patch.object(parser, "_has_text_layer", return_value=True),
        ):
            mock_settings.return_value.enable_docling_ocr = "auto"
            assert parser._resolve_ocr(Path("test.pdf"), ".pdf") is False

    def test_auto_mode_enables_ocr_for_scanned_pdf(self):
        parser = DocumentParser()
        with (
            patch("app.config.Settings") as mock_settings,
            patch.object(parser, "_has_text_layer", return_value=False),
        ):
            mock_settings.return_value.enable_docling_ocr = "auto"
            assert parser._resolve_ocr(Path("scan.pdf"), ".pdf") is True

    def test_auto_mode_no_ocr_for_non_pdf(self):
        parser = DocumentParser()
        with patch("app.config.Settings") as mock_settings:
            mock_settings.return_value.enable_docling_ocr = "auto"
            assert parser._resolve_ocr(Path("doc.docx"), ".docx") is False

    def test_true_forces_ocr(self):
        parser = DocumentParser()
        with patch("app.config.Settings") as mock_settings:
            mock_settings.return_value.enable_docling_ocr = "true"
            assert parser._resolve_ocr(Path("test.pdf"), ".pdf") is True

    def test_false_disables_ocr(self):
        parser = DocumentParser()
        with patch("app.config.Settings") as mock_settings:
            mock_settings.return_value.enable_docling_ocr = "false"
            assert parser._resolve_ocr(Path("test.pdf"), ".pdf") is False

    def test_bool_true_from_db_override(self):
        parser = DocumentParser()
        with patch("app.config.Settings") as mock_settings:
            mock_settings.return_value.enable_docling_ocr = True
            assert parser._resolve_ocr(Path("test.pdf"), ".pdf") is True

    def test_bool_false_from_db_override(self):
        parser = DocumentParser()
        with patch("app.config.Settings") as mock_settings:
            mock_settings.return_value.enable_docling_ocr = False
            assert parser._resolve_ocr(Path("test.pdf"), ".pdf") is False


class TestConverterCache:
    """Tests for two-converter cache keying."""

    def test_separate_converters_for_ocr_modes(self):
        parser = DocumentParser()
        with patch("app.ingestion.parser.DocumentConverter", create=True):
            # Patch the imports inside _get_converter
            mock_converter_cls = MagicMock()
            with patch.dict(
                "sys.modules",
                {
                    "docling.datamodel.base_models": MagicMock(),
                    "docling.datamodel.pipeline_options": MagicMock(),
                    "docling.document_converter": MagicMock(
                        DocumentConverter=mock_converter_cls,
                        PdfFormatOption=MagicMock(),
                    ),
                },
            ):
                parser._get_converter(with_ocr=False)
                parser._get_converter(with_ocr=True)
                assert "ocr" in parser._converters
                assert "no_ocr" in parser._converters
                assert mock_converter_cls.call_count == 2

    def test_converter_cached_on_second_call(self):
        parser = DocumentParser()
        mock_converter_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "docling.datamodel.base_models": MagicMock(),
                "docling.datamodel.pipeline_options": MagicMock(),
                "docling.document_converter": MagicMock(
                    DocumentConverter=mock_converter_cls,
                    PdfFormatOption=MagicMock(),
                ),
            },
        ):
            parser._get_converter(with_ocr=False)
            parser._get_converter(with_ocr=False)
            assert mock_converter_cls.call_count == 1
