"""Tests for error classification in the pipeline."""

from __future__ import annotations

import pytest

from app.ingestion.tasks import _classify_error


@pytest.mark.parametrize(
    "error_text,expected_category",
    [
        # TIMEOUT
        ("Task timed out (soft time limit exceeded)", "TIMEOUT"),
        ("SoftTimeLimitExceeded: 1800s", "TIMEOUT"),
        ("deadline exceeded waiting for response", "TIMEOUT"),
        # OOM
        ("MemoryError: unable to allocate 2.5 GiB", "OOM"),
        ("Cannot allocate memory", "OOM"),
        ("Process killed by OOM killer", "OOM"),
        # PARSE_ERROR
        ("PDFSyntaxError: invalid stream", "PARSE_ERROR"),
        ("ParseError: expected token", "PARSE_ERROR"),
        ("Invalid PDF structure at byte 1024", "PARSE_ERROR"),
        ("UnicodeDecodeError: 'utf-8' codec can't decode", "PARSE_ERROR"),
        ("File appears to be corrupt", "PARSE_ERROR"),
        # NETWORK
        ("ConnectionError: [Errno 111] Connection refused", "NETWORK"),
        ("TimeoutError: read timed out", "TIMEOUT"),  # "timed out" matches TIMEOUT first
        ("RemoteDisconnected: peer closed connection", "NETWORK"),
        ("ECONNREFUSED on port 6333", "NETWORK"),
        # LLM_API
        ("openai.RateLimitError: rate_limit exceeded", "LLM_API"),
        ("anthropic.APIError: server error", "LLM_API"),
        ("insufficient_quota: you have exceeded your usage", "LLM_API"),
        ("Service overloaded, please retry", "LLM_API"),
        # VALIDATION
        ("ValidationError: 3 validation errors for ChunkSchema", "VALIDATION"),
        ("pydantic.core._pydantic_core.ValidationError", "VALIDATION"),
        ("TypeError: expected str, got NoneType", "VALIDATION"),
        ("ValueError: invalid literal for int()", "VALIDATION"),
        # STORAGE
        ("NoSuchKey: The specified key does not exist", "STORAGE"),
        ("NoSuchBucket: bucket not found", "STORAGE"),
        ("S3Error: operation failed", "STORAGE"),
        ("minio.error.ServerError: internal error", "STORAGE"),
        # UNKNOWN
        ("KeyError: 'some_field'", "UNKNOWN"),
        ("unexpected error occurred", "UNKNOWN"),
        ("", "UNKNOWN"),
    ],
)
def test_classify_error(error_text: str, expected_category: str):
    assert _classify_error(error_text) == expected_category


def test_classify_error_case_insensitive():
    """Classification should be case-insensitive."""
    assert _classify_error("MEMORYERROR") == "OOM"
    assert _classify_error("connectionerror") == "NETWORK"


def test_classify_error_first_match_wins():
    """When multiple patterns match, the first category wins."""
    # "timed out" matches TIMEOUT before "TimeoutError" matches NETWORK
    assert _classify_error("Task timed out") == "TIMEOUT"
