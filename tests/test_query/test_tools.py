"""Tests for LangGraph tool wrappers in app/query/tools.py."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.query.tools import (
    case_context,
    document_retrieval,
    entity_lookup,
    graph_query,
    temporal_search,
    vector_search,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MATTER_ID = "00000000-0000-0000-0000-000000000001"

_SAMPLE_STATE = {
    "_filters": {"matter_id": _MATTER_ID},
    "_exclude_privilege": ["privileged", "work_product"],
    "_term_map": {},
}


def _retriever_results(n: int = 2) -> list[dict]:
    return [
        {
            "id": f"chunk-{i}",
            "source_file": f"doc{i}.pdf",
            "page_number": i + 1,
            "chunk_text": f"Sample text from chunk {i}",
            "score": round(0.9 - i * 0.1, 4),
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_vector_search_calls_retriever():
    """vector_search delegates to retriever.retrieve_text with correct filters."""
    mock_retriever = AsyncMock()
    mock_retriever.retrieve_text.return_value = _retriever_results()

    with patch("app.dependencies.get_retriever", return_value=mock_retriever):
        raw = await vector_search.ainvoke({"query": "contract breach", "limit": 10, "state": _SAMPLE_STATE})

    mock_retriever.retrieve_text.assert_called_once_with(
        "contract breach",
        limit=10,
        filters={"matter_id": _MATTER_ID},
        exclude_privilege_statuses=["privileged", "work_product"],
        dataset_doc_ids=None,
        hyde_vector=None,
    )
    parsed = json.loads(raw)
    assert len(parsed) == 2
    assert parsed[0]["filename"] == "doc0.pdf"


async def test_graph_query_calls_graph_service():
    """graph_query delegates to graph_service.get_entity_connections."""
    mock_gs = AsyncMock()
    mock_gs.get_entity_connections.return_value = [
        {"source": "John Doe", "relationship_type": "EMPLOYED_BY", "target": "Acme Corp"},
    ]

    with patch("app.dependencies.get_graph_service", return_value=mock_gs):
        raw = await graph_query.ainvoke({"entity_name": "John Doe", "state": _SAMPLE_STATE})

    mock_gs.get_entity_connections.assert_called_once_with(
        "John Doe",
        limit=20,
        exclude_privilege_statuses=["privileged", "work_product"],
        matter_id=_MATTER_ID,
    )
    parsed = json.loads(raw)
    assert len(parsed) == 1
    assert parsed[0]["target"] == "Acme Corp"


async def test_temporal_search_injects_date_filters():
    """temporal_search merges date_from/date_to into the Qdrant filters."""
    mock_retriever = AsyncMock()
    mock_retriever.retrieve_text.return_value = _retriever_results(1)

    with patch("app.dependencies.get_retriever", return_value=mock_retriever):
        await temporal_search.ainvoke(
            {
                "query": "board meeting",
                "date_from": "2020-01-01",
                "date_to": "2020-03-31",
                "state": _SAMPLE_STATE,
            }
        )

    call_kwargs = mock_retriever.retrieve_text.call_args.kwargs
    assert call_kwargs["filters"]["matter_id"] == _MATTER_ID
    assert call_kwargs["filters"]["date_from"] == "2020-01-01"
    assert call_kwargs["filters"]["date_to"] == "2020-03-31"
    assert call_kwargs["exclude_privilege_statuses"] == ["privileged", "work_product"]


async def test_entity_lookup_resolves_aliases():
    """entity_lookup uses the _term_map to resolve aliases before lookup."""
    mock_gs = AsyncMock()
    mock_gs.get_entity_by_name.return_value = {
        "name": "Jane Smith",
        "type": "person",
    }
    mock_gs.get_entity_connections.return_value = []

    state_with_alias = {
        **_SAMPLE_STATE,
        "_term_map": {"defendant a": "Jane Smith"},
    }

    with patch("app.dependencies.get_graph_service", return_value=mock_gs):
        raw = await entity_lookup.ainvoke({"name": "Defendant A", "state": state_with_alias})

    # Should have called get_entity_by_name with the resolved alias
    mock_gs.get_entity_by_name.assert_any_call("Jane Smith")
    parsed = json.loads(raw)
    assert parsed["name"] == "Jane Smith"


async def test_document_retrieval_filters_by_doc_id():
    """document_retrieval adds document_id to the filter dict."""
    mock_retriever = AsyncMock()
    mock_retriever.retrieve_text.return_value = _retriever_results(3)

    with patch("app.dependencies.get_retriever", return_value=mock_retriever):
        raw = await document_retrieval.ainvoke({"document_id": "doc-123", "state": _SAMPLE_STATE})

    call_kwargs = mock_retriever.retrieve_text.call_args.kwargs
    assert call_kwargs["filters"]["document_id"] == "doc-123"
    assert call_kwargs["filters"]["matter_id"] == _MATTER_ID
    # Empty query string for full-doc retrieval
    assert mock_retriever.retrieve_text.call_args.args[0] == ""
    parsed = json.loads(raw)
    assert len(parsed) == 3


async def test_case_context_returns_full_context():
    """case_context fetches case context from CaseService via DB session."""
    mock_db = AsyncMock()
    mock_ctx = {
        "claims": [{"id": 1, "text": "Breach of contract"}],
        "parties": [{"name": "Plaintiff Inc."}],
        "defined_terms": [{"term": "Agreement", "definition": "The MSA"}],
        "timeline": [{"date": "2020-01-15", "event": "Contract signed"}],
    }

    # Mock get_db to yield a fake session
    async def _fake_get_db():
        yield mock_db

    with (
        patch("app.dependencies.get_db", _fake_get_db),
        patch(
            "app.cases.service.CaseService.get_full_context", new_callable=AsyncMock, return_value=mock_ctx
        ) as mock_full_ctx,
    ):
        raw = await case_context.ainvoke({"aspect": "all", "state": _SAMPLE_STATE})

    mock_full_ctx.assert_called_once_with(mock_db, _MATTER_ID)
    parsed = json.loads(raw)
    assert "claims" in parsed
    assert "parties" in parsed
    assert "defined_terms" in parsed
    assert "timeline" in parsed


async def test_vector_search_returns_error_on_failure():
    """vector_search returns error JSON instead of raising when retriever fails."""
    mock_retriever = AsyncMock()
    mock_retriever.retrieve_text.side_effect = ConnectionError("Qdrant unavailable")

    with patch("app.dependencies.get_retriever", return_value=mock_retriever):
        raw = await vector_search.ainvoke({"query": "test", "state": _SAMPLE_STATE})

    parsed = json.loads(raw)
    assert "error" in parsed
    assert "ConnectionError" in parsed["error"]


async def test_graph_query_returns_error_on_failure():
    """graph_query returns error JSON instead of raising when Neo4j fails."""
    mock_gs = AsyncMock()
    mock_gs.get_entity_connections.side_effect = RuntimeError("Neo4j connection refused")

    with patch("app.dependencies.get_graph_service", return_value=mock_gs):
        raw = await graph_query.ainvoke({"entity_name": "Test", "state": _SAMPLE_STATE})

    parsed = json.loads(raw)
    assert "error" in parsed
    assert "RuntimeError" in parsed["error"]


async def test_temporal_search_returns_error_on_failure():
    """temporal_search returns error JSON instead of raising when retriever fails."""
    mock_retriever = AsyncMock()
    mock_retriever.retrieve_text.side_effect = TimeoutError("Request timed out")

    with patch("app.dependencies.get_retriever", return_value=mock_retriever):
        raw = await temporal_search.ainvoke({"query": "board meeting", "state": _SAMPLE_STATE})

    parsed = json.loads(raw)
    assert "error" in parsed
    assert "TimeoutError" in parsed["error"]


async def test_entity_lookup_returns_error_on_failure():
    """entity_lookup returns error JSON instead of raising when graph service fails."""
    mock_gs = AsyncMock()
    mock_gs.get_entity_by_name.side_effect = ConnectionError("Neo4j unavailable")

    with patch("app.dependencies.get_graph_service", return_value=mock_gs):
        raw = await entity_lookup.ainvoke({"name": "John", "state": _SAMPLE_STATE})

    parsed = json.loads(raw)
    assert "error" in parsed
    assert "ConnectionError" in parsed["error"]


async def test_document_retrieval_returns_error_on_failure():
    """document_retrieval returns error JSON instead of raising when retriever fails."""
    mock_retriever = AsyncMock()
    mock_retriever.retrieve_text.side_effect = RuntimeError("Service unavailable")

    with patch("app.dependencies.get_retriever", return_value=mock_retriever):
        raw = await document_retrieval.ainvoke({"document_id": "doc-1", "state": _SAMPLE_STATE})

    parsed = json.loads(raw)
    assert "error" in parsed
    assert "RuntimeError" in parsed["error"]


async def test_communication_matrix_error_returns_json():
    """communication_matrix returns error JSON instead of raising on failure."""
    from app.query.tools import communication_matrix

    async def _fake_get_db():
        yield AsyncMock()

    with (
        patch("app.dependencies.get_db", _fake_get_db),
        patch(
            "app.analytics.service.AnalyticsService.get_communication_matrix",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Neo4j connection refused"),
        ),
    ):
        raw = await communication_matrix.ainvoke({"state": _SAMPLE_STATE})

    parsed = json.loads(raw)
    assert "error" in parsed
    assert "RuntimeError" in parsed["error"]


async def test_topic_cluster_error_returns_json():
    """topic_cluster returns error JSON instead of raising on retriever failure."""
    from app.query.tools import topic_cluster

    mock_settings = AsyncMock()
    mock_settings.enable_topic_clustering = True

    mock_retriever = AsyncMock()
    mock_retriever.retrieve_text.side_effect = ConnectionError("Qdrant unavailable")

    with (
        patch("app.dependencies.get_settings", return_value=mock_settings),
        patch("app.dependencies.get_retriever", return_value=mock_retriever),
    ):
        raw = await topic_cluster.ainvoke({"query": "test topic", "state": _SAMPLE_STATE})

    parsed = json.loads(raw)
    assert "error" in parsed
    assert "ConnectionError" in parsed["error"]


async def test_network_analysis_error_returns_json():
    """network_analysis returns error JSON instead of raising on failure."""
    from app.query.tools import network_analysis

    mock_settings = AsyncMock()
    mock_settings.enable_graph_centrality = True

    with (
        patch("app.dependencies.get_settings", return_value=mock_settings),
        patch(
            "app.dependencies.get_graph_service",
            return_value=AsyncMock(),
        ),
        patch(
            "app.analytics.service.AnalyticsService.get_network_centrality",
            new_callable=AsyncMock,
            side_effect=RuntimeError("no such procedure"),
        ),
    ):
        raw = await network_analysis.ainvoke({"metric": "degree", "state": _SAMPLE_STATE})

    parsed = json.loads(raw)
    assert "error" in parsed
    assert "RuntimeError" in parsed["error"]


async def test_case_context_error_returns_json():
    """case_context returns error JSON when DB raises."""
    from app.query.tools import case_context

    async def _broken_get_db():
        raise RuntimeError("DB connection failed")
        yield  # noqa: unreachable — makes this an async generator

    with patch("app.dependencies.get_db", _broken_get_db):
        raw = await case_context.ainvoke({"aspect": "all", "state": _SAMPLE_STATE})

    parsed = json.loads(raw)
    assert "error" in parsed
    assert "RuntimeError" in parsed["error"]


async def test_sentiment_search_error_returns_json():
    """sentiment_search returns error JSON when DB raises."""
    from app.query.tools import sentiment_search

    async def _broken_get_db():
        raise RuntimeError("DB connection failed")
        yield  # noqa: unreachable

    with patch("app.dependencies.get_db", _broken_get_db):
        raw = await sentiment_search.ainvoke({"query": "pressure", "dimension": "pressure", "state": _SAMPLE_STATE})

    parsed = json.loads(raw)
    assert "error" in parsed
    assert "RuntimeError" in parsed["error"]


async def test_hot_doc_search_error_returns_json():
    """hot_doc_search returns error JSON when DB raises."""
    from app.query.tools import hot_doc_search

    async def _broken_get_db():
        raise RuntimeError("DB connection failed")
        yield  # noqa: unreachable

    with patch("app.dependencies.get_db", _broken_get_db):
        raw = await hot_doc_search.ainvoke({"state": _SAMPLE_STATE})

    parsed = json.loads(raw)
    assert "error" in parsed
    assert "RuntimeError" in parsed["error"]


async def test_context_gap_search_error_returns_json():
    """context_gap_search returns error JSON when DB raises."""
    from app.query.tools import context_gap_search

    async def _broken_get_db():
        raise RuntimeError("DB connection failed")
        yield  # noqa: unreachable

    with patch("app.dependencies.get_db", _broken_get_db):
        raw = await context_gap_search.ainvoke({"state": _SAMPLE_STATE})

    parsed = json.loads(raw)
    assert "error" in parsed
    assert "RuntimeError" in parsed["error"]


async def test_tool_db_session_cleanup():
    """_tool_db_session properly closes the generator even on success."""
    from app.query.tools import _tool_db_session

    mock_db = AsyncMock()
    aclose_called = False

    async def _fake_get_db():
        nonlocal aclose_called
        try:
            yield mock_db
        finally:
            aclose_called = True

    with patch("app.dependencies.get_db", _fake_get_db):
        async with _tool_db_session() as db:
            assert db is mock_db

    assert aclose_called


async def test_stub_tools_in_investigation_tools():
    """Stub/feature-flagged tools are listed in INVESTIGATION_TOOLS."""
    from app.query.tools import INVESTIGATION_TOOLS

    tool_names = [t.name for t in INVESTIGATION_TOOLS]
    assert "communication_matrix" in tool_names
    assert "topic_cluster" in tool_names
    assert "network_analysis" in tool_names
    assert "structured_query" in tool_names


async def test_structured_query_disabled_returns_info():
    """structured_query returns info message when feature flag is disabled."""
    from app.query.tools import structured_query

    mock_settings = AsyncMock()
    mock_settings.enable_text_to_sql = False

    with patch("app.dependencies.get_settings", return_value=mock_settings):
        raw = await structured_query.ainvoke({"question": "How many documents?", "state": _SAMPLE_STATE})

    parsed = json.loads(raw)
    assert "info" in parsed
    assert "not enabled" in parsed["info"]


async def test_structured_query_executes_safe_sql():
    """structured_query generates, validates, and executes SQL when enabled."""
    from app.query.sql_generator import SQLQuery
    from app.query.tools import structured_query

    mock_settings = AsyncMock()
    mock_settings.enable_text_to_sql = True

    mock_sql_result = SQLQuery(
        sql="SELECT document_type, COUNT(*) AS cnt FROM documents WHERE matter_id = :matter_id GROUP BY document_type LIMIT 50",
        explanation="Count documents by type",
        tables_used=["documents"],
    )

    mock_rows = [
        {"document_type": "pdf", "cnt": 42},
        {"document_type": "docx", "cnt": 7},
    ]

    with (
        patch("app.dependencies.get_settings", return_value=mock_settings),
        patch("app.dependencies.get_llm", return_value=AsyncMock()),
        patch(
            "app.query.sql_generator.generate_sql",
            new_callable=AsyncMock,
            return_value=mock_sql_result,
        ) as mock_gen,
        patch(
            "app.query.sql_generator.validate_sql_safety",
            return_value=(True, ""),
        ),
        patch(
            "app.query.sql_generator.execute_sql",
            new_callable=AsyncMock,
            return_value=mock_rows,
        ) as mock_exec,
    ):
        raw = await structured_query.ainvoke({"question": "How many documents by type?", "state": _SAMPLE_STATE})

    mock_gen.assert_called_once()
    mock_exec.assert_called_once()
    parsed = json.loads(raw)
    assert "results" in parsed
    assert len(parsed["results"]) == 2
    assert parsed["results"][0]["document_type"] == "pdf"
    assert parsed["explanation"] == "Count documents by type"


async def test_structured_query_rejects_unsafe_sql():
    """structured_query returns error when generated SQL fails validation."""
    from app.query.sql_generator import SQLQuery
    from app.query.tools import structured_query

    mock_settings = AsyncMock()
    mock_settings.enable_text_to_sql = True

    mock_sql_result = SQLQuery(
        sql="DELETE FROM documents WHERE matter_id = :matter_id LIMIT 10",
        explanation="Delete documents",
        tables_used=["documents"],
    )

    with (
        patch("app.dependencies.get_settings", return_value=mock_settings),
        patch("app.dependencies.get_llm", return_value=AsyncMock()),
        patch(
            "app.query.sql_generator.generate_sql",
            new_callable=AsyncMock,
            return_value=mock_sql_result,
        ),
        patch(
            "app.query.sql_generator.validate_sql_safety",
            return_value=(False, "Write operation detected: DELETE"),
        ),
    ):
        raw = await structured_query.ainvoke({"question": "delete all documents", "state": _SAMPLE_STATE})

    parsed = json.loads(raw)
    assert "error" in parsed
    assert "safety validation" in parsed["error"]


async def test_structured_query_error_returns_json():
    """structured_query returns error JSON when LLM call fails."""
    from app.query.tools import structured_query

    mock_settings = AsyncMock()
    mock_settings.enable_text_to_sql = True

    with (
        patch("app.dependencies.get_settings", return_value=mock_settings),
        patch(
            "app.dependencies.get_llm",
            side_effect=RuntimeError("LLM unavailable"),
        ),
    ):
        raw = await structured_query.ainvoke({"question": "count docs", "state": _SAMPLE_STATE})

    parsed = json.loads(raw)
    assert "error" in parsed
    assert "RuntimeError" in parsed["error"]


# ---------------------------------------------------------------------------
# Verify all flag-gated tools use get_settings() (not Settings())
# ---------------------------------------------------------------------------

_TOOLS_FILE = Path(__file__).resolve().parent.parent.parent / "app" / "query" / "tools.py"


def test_no_direct_settings_instantiation():
    """All tools must use get_settings() instead of Settings() for runtime flag overrides."""
    source = _TOOLS_FILE.read_text()
    tree = ast.parse(source)

    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Settings":
            violations.append(f"line {node.lineno}: Settings() called directly")

    assert not violations, "app/query/tools.py uses Settings() directly instead of get_settings():\n" + "\n".join(
        violations
    )


def test_no_import_settings_from_config():
    """tools.py should not import Settings from app.config (should use get_settings from dependencies)."""
    source = _TOOLS_FILE.read_text()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.config":
            imported_names = [alias.name for alias in node.names]
            assert "Settings" not in imported_names, (
                f"line {node.lineno}: 'from app.config import Settings' found — "
                "tools should use 'from app.dependencies import get_settings' instead"
            )
