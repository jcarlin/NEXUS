"""Tests for the Epstein emails adapter (both flat and threaded schemas)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app.ingestion.adapters.epstein_emails import (
    EpsteinEmailAdapter,
    _clean_sender,
    _strip_html,
)
from app.ingestion.bulk_import import DatasetAdapter

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_FLAT_ROWS = [
    {
        "id": 1,
        "email_document_id": 1,
        "source_filename": "HOUSE_OVERSIGHT_012102.txt",
        "subject": "Re: Meeting",
        "message_order": 0,
        "from_address": "Jeffrey Epstein",
        "to_address": "Nicholas Ribis",
        "other_recipients": "[]",
        "timestamp_raw": "5/7/2019 4:29:00 AM",
        "timestamp_iso": "20190507042900",
        "message_html": "<p>Here is the <b>article</b> I mentioned. Please review it at your earliest convenience.</p>",
        "document_id": "HOUSE_OVERSIGHT_012102",
    },
    {
        "id": 2,
        "email_document_id": 1,
        "source_filename": "HOUSE_OVERSIGHT_012102.txt",
        "subject": "Re: Meeting",
        "message_order": 1,
        "from_address": "Nicholas Ribis",
        "to_address": "Jeffrey Epstein",
        "other_recipients": "['John Smith', 'Jane Doe']",
        "timestamp_raw": "5/7/2019 5:15:00 AM",
        "timestamp_iso": "20190507051500",
        "message_html": "<div>Thanks for sending. I will review and get back to you by end of week.</div>",
        "document_id": "HOUSE_OVERSIGHT_012102",
    },
    {
        "id": 3,
        "email_document_id": 2,
        "source_filename": "HOUSE_OVERSIGHT_012103.txt",
        "subject": "Dinner plans",
        "message_order": 0,
        "from_address": "Jeffrey Epstein",
        "to_address": "Ghislaine Maxwell",
        "other_recipients": "[]",
        "timestamp_raw": "6/1/2019 8:00:00 PM",
        "timestamp_iso": "20190601200000",
        "message_html": "<p>ok</p>",  # Too short after stripping
        "document_id": "HOUSE_OVERSIGHT_012103",
    },
]

_THREADED_ROWS = [
    {
        "thread_id": "TEXT-001-HOUSE_OVERSIGHT_031683.txt_2",
        "source_file": "TEXT-001-HOUSE_OVERSIGHT_031683.txt",
        "subject": "Re: Discussion about the project",
        "messages": json.dumps(
            [
                {
                    "sender": "J [jeevacation@gmail.com]",
                    "recipients": ["Michael Wolff"],
                    "timestamp": "5/30/2019 5:29 PM",
                    "subject": "Re: Discussion",
                    "body": "Is it a coincidence that the same person bought the house in Palm Beach and knows everything?",
                },
                {
                    "sender": "Michael Wolff",
                    "recipients": [],
                    "timestamp": "5/30/2019 5:33 PM",
                    "subject": "Re: Discussion",
                    "body": "So MBS was paying him off? Why? Ideas?",
                },
                {
                    "sender": "J [jeevacation@gmail.com]",
                    "recipients": ["Michael Wolff"],
                    "timestamp": "5/30/2019 9:34:38 PM",
                    "subject": "Re: Discussion",
                    "body": "Maybe as a favor. In exchange for support on the issue. Smells doesn't it?",
                },
            ]
        ),
        "message_count": 3,
    },
    {
        "thread_id": "TEXT-002-HOUSE_OVERSIGHT_022827.txt_12",
        "source_file": "TEXT-002-HOUSE_OVERSIGHT_022827.txt",
        "subject": "Briefing notes",
        "messages": json.dumps(
            [
                {
                    "sender": "Robert Kuhn",
                    "recipients": ["jeffrey E. <jeevacation@gmail.com>"],
                    "timestamp": "Wed, Feb 15, 2017 at 1:27 AM",
                    "subject": "Briefing notes",
                    "body": "ok",  # Too short
                },
            ]
        ),
        "message_count": 1,
    },
]


def _make_flat_parquet(path: Path, rows: list[dict] | None = None) -> Path:
    df = pd.DataFrame(rows or _FLAT_ROWS)
    pq = path / "tobe_emails.parquet"
    df.to_parquet(pq, index=False)
    return pq


def _make_threaded_parquet(path: Path, rows: list[dict] | None = None) -> Path:
    df = pd.DataFrame(rows or _THREADED_ROWS)
    pq = path / "muneeb_emails.parquet"
    df.to_parquet(pq, index=False)
    return pq


# ---------------------------------------------------------------------------
# 1. Protocol compliance
# ---------------------------------------------------------------------------


def test_adapter_satisfies_protocol(tmp_path: Path) -> None:
    pq = _make_flat_parquet(tmp_path)
    adapter = EpsteinEmailAdapter(file_path=pq)
    assert isinstance(adapter, DatasetAdapter)
    assert adapter.name == "epstein_emails"


# ---------------------------------------------------------------------------
# 2. Flat schema (to-be/epstein-emails)
# ---------------------------------------------------------------------------


def test_flat_reads_messages(tmp_path: Path) -> None:
    """Flat adapter yields one ImportDocument per row with sufficient body text."""
    pq = _make_flat_parquet(tmp_path)
    adapter = EpsteinEmailAdapter(file_path=pq)

    docs = list(adapter.iter_documents())

    # 3 rows: 2 with enough text, 1 too short ("ok")
    assert len(docs) == 2
    assert docs[0].doc_type == "email"
    assert docs[0].source == "epstein_emails_tobe"
    assert docs[0].email_headers is not None
    assert docs[0].email_headers["from"] == "Jeffrey Epstein"
    assert docs[0].email_headers["to"] == "Nicholas Ribis"
    assert docs[0].email_headers["subject"] == "Re: Meeting"
    assert "article" in docs[0].text  # HTML stripped
    assert "<p>" not in docs[0].text  # No HTML tags


def test_flat_strips_html(tmp_path: Path) -> None:
    """HTML tags should be stripped from message_html."""
    pq = _make_flat_parquet(tmp_path)
    adapter = EpsteinEmailAdapter(file_path=pq)

    docs = list(adapter.iter_documents())
    assert "<b>" not in docs[0].text
    assert "<p>" not in docs[0].text
    assert "article" in docs[0].text


def test_flat_parses_other_recipients(tmp_path: Path) -> None:
    """other_recipients should be parsed and included in the 'to' header."""
    pq = _make_flat_parquet(tmp_path)
    adapter = EpsteinEmailAdapter(file_path=pq)

    docs = list(adapter.iter_documents())
    # Second message has other_recipients: ['John Smith', 'Jane Doe']
    assert "John Smith" in docs[1].email_headers["to"]
    assert "Jane Doe" in docs[1].email_headers["to"]


def test_flat_content_hash(tmp_path: Path) -> None:
    """Each document should have a content hash for dedup."""
    pq = _make_flat_parquet(tmp_path)
    adapter = EpsteinEmailAdapter(file_path=pq)

    docs = list(adapter.iter_documents())
    assert docs[0].content_hash
    assert docs[1].content_hash
    assert docs[0].content_hash != docs[1].content_hash


def test_flat_metadata(tmp_path: Path) -> None:
    """Metadata should include source file and dataset identifier."""
    pq = _make_flat_parquet(tmp_path)
    adapter = EpsteinEmailAdapter(file_path=pq)

    docs = list(adapter.iter_documents())
    assert docs[0].metadata["dataset"] == "to-be/epstein-emails"
    assert docs[0].metadata["source_file"] == "HOUSE_OVERSIGHT_012102.txt"
    assert docs[0].metadata["message_order"] == 0


# ---------------------------------------------------------------------------
# 3. Threaded schema (notesbymuneeb/epstein-emails)
# ---------------------------------------------------------------------------


def test_threaded_flattens_messages(tmp_path: Path) -> None:
    """Each message in a thread should become a separate ImportDocument."""
    pq = _make_threaded_parquet(tmp_path)
    adapter = EpsteinEmailAdapter(file_path=pq)

    docs = list(adapter.iter_documents())

    # Thread 1: 3 messages (all have enough text)
    # Thread 2: 1 message (too short — "ok")
    assert len(docs) == 3
    assert all(d.doc_type == "email" for d in docs)
    assert all(d.source == "epstein_emails_muneeb" for d in docs)


def test_threaded_email_headers(tmp_path: Path) -> None:
    """Email headers should be extracted from each message."""
    pq = _make_threaded_parquet(tmp_path)
    adapter = EpsteinEmailAdapter(file_path=pq)

    docs = list(adapter.iter_documents())
    # First message: sender is "J [jeevacation@gmail.com]" → cleaned to "J"
    assert docs[0].email_headers["from"] == "J"
    assert docs[0].email_headers["to"] == "Michael Wolff"
    assert docs[0].email_headers["date"] == "5/30/2019 5:29 PM"


def test_threaded_metadata(tmp_path: Path) -> None:
    """Metadata should include thread_id and dataset identifier."""
    pq = _make_threaded_parquet(tmp_path)
    adapter = EpsteinEmailAdapter(file_path=pq)

    docs = list(adapter.iter_documents())
    assert docs[0].metadata["dataset"] == "notesbymuneeb/epstein-emails"
    assert docs[0].metadata["thread_id"] == "TEXT-001-HOUSE_OVERSIGHT_031683.txt_2"
    assert docs[0].metadata["message_index"] == 0
    assert docs[1].metadata["message_index"] == 1


def test_threaded_content_hash_unique(tmp_path: Path) -> None:
    """Different messages should produce different content hashes."""
    pq = _make_threaded_parquet(tmp_path)
    adapter = EpsteinEmailAdapter(file_path=pq)

    docs = list(adapter.iter_documents())
    hashes = {d.content_hash for d in docs}
    assert len(hashes) == len(docs)


def test_threaded_malformed_json(tmp_path: Path) -> None:
    """Rows with unparseable messages JSON should be skipped, not crash."""
    rows = [
        {
            "thread_id": "bad-thread",
            "source_file": "bad.txt",
            "subject": "Bad JSON",
            "messages": "this is not json",
            "message_count": 1,
        },
        {
            "thread_id": "good-thread",
            "source_file": "good.txt",
            "subject": "Good thread",
            "messages": json.dumps(
                [
                    {
                        "sender": "Alice",
                        "recipients": ["Bob"],
                        "timestamp": "1/1/2020",
                        "subject": "Hello",
                        "body": "This is a valid message with enough text for the adapter to accept it.",
                    }
                ]
            ),
            "message_count": 1,
        },
    ]
    pq = _make_threaded_parquet(tmp_path, rows)
    adapter = EpsteinEmailAdapter(file_path=pq)

    docs = list(adapter.iter_documents())
    assert len(docs) == 1
    assert docs[0].email_headers["from"] == "Alice"


# ---------------------------------------------------------------------------
# 4. Schema auto-detection
# ---------------------------------------------------------------------------


def test_auto_detects_flat_schema(tmp_path: Path) -> None:
    """Adapter should auto-detect flat schema by presence of 'from_address' column."""
    pq = _make_flat_parquet(tmp_path)
    adapter = EpsteinEmailAdapter(file_path=pq)

    docs = list(adapter.iter_documents())
    assert all(d.source == "epstein_emails_tobe" for d in docs)


def test_auto_detects_threaded_schema(tmp_path: Path) -> None:
    """Adapter should auto-detect threaded schema by presence of 'messages' column."""
    pq = _make_threaded_parquet(tmp_path)
    adapter = EpsteinEmailAdapter(file_path=pq)

    docs = list(adapter.iter_documents())
    assert all(d.source == "epstein_emails_muneeb" for d in docs)


def test_unknown_schema_raises(tmp_path: Path) -> None:
    """Adapter should raise ValueError for unrecognized column layout."""
    df = pd.DataFrame({"col_a": [1], "col_b": ["text"]})
    pq = tmp_path / "unknown.parquet"
    df.to_parquet(pq, index=False)

    adapter = EpsteinEmailAdapter(file_path=pq)
    try:
        list(adapter.iter_documents())
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert "Unrecognized email dataset schema" in str(exc)


# ---------------------------------------------------------------------------
# 5. Limit
# ---------------------------------------------------------------------------


def test_respects_limit(tmp_path: Path) -> None:
    """limit=N should yield at most N documents."""
    pq = _make_flat_parquet(tmp_path)
    adapter = EpsteinEmailAdapter(file_path=pq)

    docs = list(adapter.iter_documents(limit=1))
    assert len(docs) == 1


def test_threaded_limit_across_threads(tmp_path: Path) -> None:
    """Limit should apply across threads, not per thread."""
    pq = _make_threaded_parquet(tmp_path)
    adapter = EpsteinEmailAdapter(file_path=pq)

    docs = list(adapter.iter_documents(limit=2))
    assert len(docs) == 2


# ---------------------------------------------------------------------------
# 6. Helper functions
# ---------------------------------------------------------------------------


def test_strip_html() -> None:
    assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"
    assert _strip_html("plain text") == "plain text"
    assert _strip_html("<div>  spaced  </div>") == "spaced"


def test_clean_sender() -> None:
    assert _clean_sender("J [jeevacation@gmail.com]") == "J"
    assert _clean_sender("jeffrey E. <jeevacation@gmail.com>") == "jeffrey E."
    assert _clean_sender("Michael Wolff <:MM11>") == "Michael Wolff"
    assert _clean_sender("Plain Name") == "Plain Name"
    assert _clean_sender("") == ""


# ---------------------------------------------------------------------------
# 7. CSV format
# ---------------------------------------------------------------------------


def test_reads_csv_format(tmp_path: Path) -> None:
    """Adapter should handle CSV files as well as Parquet."""
    df = pd.DataFrame(_FLAT_ROWS)
    csv_path = tmp_path / "emails.csv"
    df.to_csv(csv_path, index=False)

    adapter = EpsteinEmailAdapter(file_path=csv_path)
    docs = list(adapter.iter_documents())
    assert len(docs) == 2
