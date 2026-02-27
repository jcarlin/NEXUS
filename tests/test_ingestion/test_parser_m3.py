"""Tests for M3 parsers: EML, MSG, CSV/TSV, RTF, and updated routing."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.ingestion.parser import DocumentParser, PARSER_ROUTES


# ---------------------------------------------------------------------------
# EML tests (4)
# ---------------------------------------------------------------------------

def _make_eml(content: bytes, suffix: str = ".eml") -> Path:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(content)
        return Path(f.name)


def test_parse_eml_basic():
    """Parse a simple plaintext EML file."""
    eml_bytes = (
        b"From: alice@example.com\r\n"
        b"To: bob@example.com\r\n"
        b"Subject: Test email\r\n"
        b"Date: Mon, 1 Jan 2024 12:00:00 +0000\r\n"
        b"Content-Type: text/plain\r\n"
        b"\r\n"
        b"Hello Bob,\r\n\r\nThis is a test email.\r\n"
    )
    path = _make_eml(eml_bytes)
    try:
        parser = DocumentParser()
        result = parser.parse(path, "test.eml")
        assert "alice@example.com" in result.text
        assert "bob@example.com" in result.text
        assert "Test email" in result.text
        assert "Hello Bob" in result.text
        assert result.metadata["document_type"] == "email"
        assert result.metadata["from"] == "alice@example.com"
        assert result.metadata["subject"] == "Test email"
        assert result.page_count == 1
    finally:
        path.unlink(missing_ok=True)


def test_parse_eml_html_fallback():
    """Parse an HTML-only EML (no plaintext part)."""
    eml_bytes = (
        b"From: sender@test.com\r\n"
        b"To: receiver@test.com\r\n"
        b"Subject: HTML only\r\n"
        b"Content-Type: text/html\r\n"
        b"\r\n"
        b"<html><body><p>Hello <b>World</b></p></body></html>\r\n"
    )
    path = _make_eml(eml_bytes)
    try:
        parser = DocumentParser()
        result = parser.parse(path, "html_email.eml")
        # HTML tags should be stripped
        assert "Hello" in result.text
        assert "<html>" not in result.text
    finally:
        path.unlink(missing_ok=True)


def test_parse_eml_with_attachment():
    """Parse an EML with an attachment — attachment_data should be in metadata."""
    eml_bytes = (
        b"From: alice@example.com\r\n"
        b"To: bob@example.com\r\n"
        b"Subject: With attachment\r\n"
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="boundary123"\r\n'
        b"\r\n"
        b"--boundary123\r\n"
        b"Content-Type: text/plain\r\n"
        b"\r\n"
        b"See attached file.\r\n"
        b"--boundary123\r\n"
        b"Content-Type: application/pdf\r\n"
        b'Content-Disposition: attachment; filename="doc.pdf"\r\n'
        b"Content-Transfer-Encoding: base64\r\n"
        b"\r\n"
        b"JVBERi0xLjQK\r\n"
        b"--boundary123--\r\n"
    )
    path = _make_eml(eml_bytes)
    try:
        parser = DocumentParser()
        result = parser.parse(path, "with_attachment.eml")
        assert "See attached file" in result.text
        assert result.metadata.get("attachment_count") == 1
        assert len(result.metadata["attachment_data"]) == 1
        assert result.metadata["attachment_data"][0]["filename"] == "doc.pdf"
    finally:
        path.unlink(missing_ok=True)


def test_parse_eml_cc_header():
    """CC header should be included in metadata when present."""
    eml_bytes = (
        b"From: a@test.com\r\n"
        b"To: b@test.com\r\n"
        b"Cc: c@test.com\r\n"
        b"Subject: CC test\r\n"
        b"Content-Type: text/plain\r\n"
        b"\r\n"
        b"Body\r\n"
    )
    path = _make_eml(eml_bytes)
    try:
        parser = DocumentParser()
        result = parser.parse(path, "cc.eml")
        assert result.metadata["cc"] == "c@test.com"
        assert "Cc: c@test.com" in result.text
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# MSG tests (2)
# ---------------------------------------------------------------------------

def test_parse_msg_routing():
    """MSG files should route to the 'msg' backend."""
    assert PARSER_ROUTES[".msg"] == "msg"


def test_parse_msg_import():
    """extract_msg should be importable (dependency present)."""
    import extract_msg  # noqa: F401


# ---------------------------------------------------------------------------
# CSV tests (3)
# ---------------------------------------------------------------------------

def test_parse_csv_basic():
    """Parse a simple CSV into a markdown table."""
    csv_content = "Name,Age,City\nAlice,30,NYC\nBob,25,LA\n"
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as f:
        f.write(csv_content)
        path = Path(f.name)

    try:
        parser = DocumentParser()
        result = parser.parse(path, "data.csv")
        assert "| Name | Age | City |" in result.text
        assert "| Alice | 30 | NYC |" in result.text
        assert "| Bob | 25 | LA |" in result.text
        assert result.metadata["row_count"] == 2
        assert result.metadata["column_count"] == 3
        assert result.metadata["truncated"] is False
    finally:
        path.unlink(missing_ok=True)


def test_parse_csv_empty():
    """An empty CSV should return a placeholder."""
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as f:
        f.write("")
        path = Path(f.name)

    try:
        parser = DocumentParser()
        result = parser.parse(path, "empty.csv")
        assert result.metadata["row_count"] == 0
    finally:
        path.unlink(missing_ok=True)


def test_parse_tsv():
    """TSV files should be parsed using the CSV backend."""
    tsv_content = "Name\tScore\nAlice\t95\n"
    with tempfile.NamedTemporaryFile(suffix=".tsv", mode="w", delete=False) as f:
        f.write(tsv_content)
        path = Path(f.name)

    try:
        parser = DocumentParser()
        result = parser.parse(path, "data.tsv")
        assert "Name" in result.text
        assert "Alice" in result.text
        assert result.metadata["format"] == ".tsv"
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# RTF tests (2)
# ---------------------------------------------------------------------------

def test_parse_rtf():
    """Parse a simple RTF document."""
    rtf_content = r"{\rtf1\ansi Hello RTF World!}"
    with tempfile.NamedTemporaryFile(suffix=".rtf", mode="w", delete=False) as f:
        f.write(rtf_content)
        path = Path(f.name)

    try:
        parser = DocumentParser()
        result = parser.parse(path, "document.rtf")
        assert "Hello RTF World!" in result.text
        assert result.metadata["format"] == ".rtf"
        assert result.page_count == 1
    finally:
        path.unlink(missing_ok=True)


def test_parse_rtf_routing():
    """RTF should route to the 'rtf' backend."""
    assert PARSER_ROUTES[".rtf"] == "rtf"


# ---------------------------------------------------------------------------
# Routing tests (3)
# ---------------------------------------------------------------------------

def test_eml_route_is_eml():
    """EML should route to 'eml', not 'unsupported'."""
    assert PARSER_ROUTES[".eml"] == "eml"


def test_csv_route_is_csv():
    """CSV should route to 'csv', not 'unsupported'."""
    assert PARSER_ROUTES[".csv"] == "csv"


def test_doc_remains_unsupported():
    """Legacy .doc format should remain 'unsupported'."""
    assert PARSER_ROUTES[".doc"] == "unsupported"
