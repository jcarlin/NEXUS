"""Tests for scripts/backfill_document_dates.py — three-phase document_date backfill."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scripts.backfill_document_dates import (
    backfill_postgres,
    backfill_qdrant,
)


def _make_engine_with_rows(batches: list[list[SimpleNamespace]]) -> MagicMock:
    """Build a mock engine whose ``connect().execute().fetchall()`` returns
    successive batches from *batches*, terminated by an empty list.
    """
    engine = MagicMock()
    conn = MagicMock()

    # Each call to execute(SELECT ...) returns a result whose fetchall yields
    # the next batch; execute(UPDATE ...) returns a no-op result.
    select_batches = list(batches) + [[]]
    select_results = []
    for rows in select_batches:
        res = MagicMock()
        res.fetchall.return_value = rows
        select_results.append(res)

    def execute_side_effect(stmt, params=None):
        # SELECT queries: pop the next batch result
        # UPDATE queries: return a MagicMock (ignored)
        stmt_sql = str(stmt).upper()
        if "SELECT" in stmt_sql:
            return select_results.pop(0)
        return MagicMock()

    conn.execute.side_effect = execute_side_effect
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)
    engine.connect.return_value = conn
    return engine


def test_backfill_postgres_parses_and_updates():
    """Phase 1 should parse metadata_->>'date' rows and issue UPDATEs."""
    rows = [
        SimpleNamespace(id="d1", raw_date="Wed, 12 Feb 2025 16:10:00 +0000"),
        SimpleNamespace(id="d2", raw_date="2020-03-15T10:00:00Z"),
    ]
    engine = _make_engine_with_rows([rows])

    parsed, unparsable = backfill_postgres(
        engine,
        matter_id=None,
        batch=100,
        dry_run=False,
        tracker=None,
    )

    assert parsed == 2
    assert unparsable == 0
    # Commit should have been invoked after a batch with updates
    conn = engine.connect.return_value
    assert conn.commit.called


def test_backfill_postgres_skips_unparsable():
    """Unparseable raw dates should increment ``unparsable`` and stay NULL (no update)."""
    rows = [
        SimpleNamespace(id="d1", raw_date="not a real date"),
        SimpleNamespace(id="d2", raw_date="also garbage"),
    ]
    engine = _make_engine_with_rows([rows])

    parsed, unparsable = backfill_postgres(
        engine,
        matter_id=None,
        batch=100,
        dry_run=False,
        tracker=None,
    )

    assert parsed == 0
    assert unparsable == 2


def test_backfill_postgres_dry_run_does_not_commit():
    """Dry run should count rows but never call conn.commit()."""
    rows = [
        SimpleNamespace(id="d1", raw_date="2025-02-12T16:10:00+00:00"),
    ]
    engine = _make_engine_with_rows([rows])

    parsed, _ = backfill_postgres(
        engine,
        matter_id=None,
        batch=100,
        dry_run=True,
        tracker=None,
    )

    assert parsed == 1
    conn = engine.connect.return_value
    assert not conn.commit.called


def test_backfill_postgres_empty_corpus_terminates_cleanly():
    """No rows → both counters zero, no infinite loop."""
    engine = _make_engine_with_rows([])  # immediately empty

    parsed, unparsable = backfill_postgres(
        engine,
        matter_id=None,
        batch=100,
        dry_run=False,
        tracker=None,
    )

    assert parsed == 0
    assert unparsable == 0


def test_backfill_qdrant_issues_one_set_payload_per_doc():
    """Phase 3 should call ``set_payload`` once per doc with the correct
    ``doc_id`` FieldCondition + ``document_date`` ISO string."""
    rows = [
        SimpleNamespace(id="d1", document_date=datetime(2020, 2, 15, 10, 0, tzinfo=UTC)),
        SimpleNamespace(id="d2", document_date=datetime(2020, 3, 15, 11, 0, tzinfo=UTC)),
    ]
    engine = _make_engine_with_rows([rows])

    mock_client = MagicMock()
    mock_settings = MagicMock()
    mock_settings.qdrant_url = "http://localhost:6333"

    with (
        patch("app.config.Settings", return_value=mock_settings),
        patch("qdrant_client.QdrantClient", return_value=mock_client),
    ):
        updated, failed = backfill_qdrant(
            engine,
            matter_id=None,
            batch=100,
            dry_run=False,
            tracker=None,
        )

    assert updated == 2
    assert failed == 0
    assert mock_client.set_payload.call_count == 2
    first_call = mock_client.set_payload.call_args_list[0]
    assert first_call.kwargs["payload"]["document_date"] == "2020-02-15T10:00:00+00:00"
    # Filter shape: must=[FieldCondition(key="doc_id", match=MatchValue(value="d1"))]
    qfilter = first_call.kwargs["points"]
    assert qfilter.must[0].key == "doc_id"
    assert qfilter.must[0].match.value == "d1"


def test_backfill_qdrant_dry_run_no_set_payload():
    """Dry run must increment counter but not call the Qdrant client."""
    rows = [
        SimpleNamespace(id="d1", document_date=datetime(2020, 2, 15, 10, 0, tzinfo=UTC)),
    ]
    engine = _make_engine_with_rows([rows])
    mock_client = MagicMock()
    mock_settings = MagicMock()
    mock_settings.qdrant_url = "http://localhost:6333"

    with (
        patch("app.config.Settings", return_value=mock_settings),
        patch("qdrant_client.QdrantClient", return_value=mock_client),
    ):
        updated, _ = backfill_qdrant(
            engine,
            matter_id=None,
            batch=100,
            dry_run=True,
            tracker=None,
        )

    assert updated == 1
    assert mock_client.set_payload.call_count == 0


def test_backfill_qdrant_continues_on_per_doc_failure():
    """A set_payload exception for one doc must not abort the whole phase."""
    rows = [
        SimpleNamespace(id="d1", document_date=datetime(2020, 2, 15, 10, 0, tzinfo=UTC)),
        SimpleNamespace(id="d2", document_date=datetime(2020, 3, 15, 11, 0, tzinfo=UTC)),
    ]
    engine = _make_engine_with_rows([rows])
    mock_client = MagicMock()
    mock_client.set_payload.side_effect = [RuntimeError("boom"), None]
    mock_settings = MagicMock()
    mock_settings.qdrant_url = "http://localhost:6333"

    with (
        patch("app.config.Settings", return_value=mock_settings),
        patch("qdrant_client.QdrantClient", return_value=mock_client),
    ):
        updated, failed = backfill_qdrant(
            engine,
            matter_id=None,
            batch=100,
            dry_run=False,
            tracker=None,
        )

    assert updated == 1
    assert failed == 1
