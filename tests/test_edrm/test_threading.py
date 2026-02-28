"""Tests for email threading (RFC 5322 header-based + subject fallback)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.ingestion.threading import EmailThreader, _make_thread_id, _normalize_subject


# ---------------------------------------------------------------------------
# Subject normalization helper tests
# ---------------------------------------------------------------------------

def test_normalize_subject_strips_re():
    """Re: prefix should be stripped."""
    assert _normalize_subject("Re: Contract Review") == "contract review"


def test_normalize_subject_strips_fwd():
    """Fwd: prefix should be stripped."""
    assert _normalize_subject("Fwd: Contract Review") == "contract review"


def test_normalize_subject_strips_multiple():
    """Multiple Re:/Fwd: prefixes should all be stripped."""
    assert _normalize_subject("Re: Re: Fwd: Meeting Notes") == "meeting notes"


# ---------------------------------------------------------------------------
# Threading by References header (1)
# ---------------------------------------------------------------------------

def test_thread_by_references():
    """Documents with References header should be threaded by the root message-id."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    headers = {
        "message_id": "<msg3@example.com>",
        "in_reply_to": "<msg2@example.com>",
        "references": "<msg1@example.com> <msg2@example.com>",
        "subject": "Re: Project Update",
    }

    thread_id, position = EmailThreader.assign_thread(
        mock_engine, "doc-123", headers, "matter-1"
    )

    # Thread ID should be based on first reference (root message)
    expected_thread_id = _make_thread_id("<msg1@example.com>")
    assert thread_id == expected_thread_id
    assert position == 2  # Two references = position 2

    # Should have called UPDATE on the document
    mock_conn.execute.assert_called()
    mock_conn.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Threading by In-Reply-To header (1)
# ---------------------------------------------------------------------------

def test_thread_by_in_reply_to():
    """Documents with In-Reply-To but no References should check parent in DB."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    # Simulate parent NOT found in DB
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_conn.execute.return_value = mock_result

    headers = {
        "message_id": "<msg2@example.com>",
        "in_reply_to": "<msg1@example.com>",
        "references": "",
        "subject": "Re: Budget Discussion",
    }

    thread_id, position = EmailThreader.assign_thread(
        mock_engine, "doc-456", headers, "matter-1"
    )

    # Should create thread from in_reply_to
    expected_thread_id = _make_thread_id("<msg1@example.com>")
    assert thread_id == expected_thread_id
    assert position == 1


# ---------------------------------------------------------------------------
# Subject fallback threading (1)
# ---------------------------------------------------------------------------

def test_thread_by_subject_fallback():
    """Documents with no References/In-Reply-To should fall back to subject matching."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    # Simulate no existing thread found by subject
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_conn.execute.return_value = mock_result

    headers = {
        "message_id": "<msg1@example.com>",
        "in_reply_to": "",
        "references": "",
        "subject": "Weekly Status Meeting",
    }

    thread_id, position = EmailThreader.assign_thread(
        mock_engine, "doc-789", headers, "matter-1"
    )

    # Should create new thread from normalized subject
    expected_thread_id = _make_thread_id("weekly status meeting")
    assert thread_id == expected_thread_id
    assert position == 0  # First message in new thread


# ---------------------------------------------------------------------------
# Inclusive email detection (1)
# ---------------------------------------------------------------------------

def test_detect_inclusive_emails():
    """Inclusive detection should UPDATE documents and return a count."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    # First execute: reset inclusive flags (UPDATE)
    # Second execute: mark inclusive (UPDATE with subquery)
    mock_reset_result = MagicMock()
    mock_inclusive_result = MagicMock()
    mock_inclusive_result.rowcount = 5
    mock_conn.execute.side_effect = [mock_reset_result, mock_inclusive_result]

    count = EmailThreader.detect_inclusive_emails(mock_engine, "matter-1")

    assert count == 5
    assert mock_conn.execute.call_count == 2
    mock_conn.commit.assert_called_once()
