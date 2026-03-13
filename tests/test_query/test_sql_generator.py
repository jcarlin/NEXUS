"""Tests for T2-10: Text-to-SQL generation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.query.sql_generator import (
    ALLOWED_TABLES,
    SQLQuery,
    _parse_sql_response,
    ensure_limit,
    ensure_matter_id,
    generate_sql,
    validate_sql_safety,
)


@pytest.fixture
def mock_llm():
    return AsyncMock()


class TestGenerateSQL:
    @pytest.mark.asyncio
    async def test_basic_generation(self, mock_llm):
        """Verify generate_sql produces a SQLQuery."""
        mock_llm.complete = AsyncMock(
            return_value=json.dumps(
                {
                    "sql": "SELECT filename, document_type, COUNT(*) FROM documents WHERE matter_id = :matter_id GROUP BY filename, document_type LIMIT 50",
                    "explanation": "Count documents by type",
                    "tables_used": ["documents"],
                }
            )
        )

        result = await generate_sql("How many documents by type?", "matter-123", mock_llm)

        assert isinstance(result, SQLQuery)
        assert "SELECT" in result.sql
        assert "documents" in result.tables_used

    @pytest.mark.asyncio
    async def test_uses_correct_node_name(self, mock_llm):
        """Verify the LLM call uses the correct node_name."""
        mock_llm.complete = AsyncMock(
            return_value=json.dumps(
                {
                    "sql": "SELECT COUNT(*) FROM documents WHERE matter_id = :matter_id LIMIT 1",
                    "explanation": "test",
                    "tables_used": ["documents"],
                }
            )
        )

        await generate_sql("count docs", "matter-123", mock_llm)

        call_kwargs = mock_llm.complete.call_args[1]
        assert call_kwargs.get("node_name") == "text_to_sql"


class TestValidateSQLSafety:
    def test_rejects_insert(self):
        is_safe, reason = validate_sql_safety("INSERT INTO documents VALUES ('a')")
        assert not is_safe
        assert "Write operation" in reason

    def test_rejects_update(self):
        is_safe, reason = validate_sql_safety(
            "UPDATE documents SET filename = 'x' WHERE matter_id = :matter_id LIMIT 1"
        )
        assert not is_safe
        assert "Write operation" in reason

    def test_rejects_delete(self):
        is_safe, reason = validate_sql_safety("DELETE FROM documents WHERE matter_id = :matter_id LIMIT 1")
        assert not is_safe
        assert "Write operation" in reason

    def test_rejects_drop(self):
        is_safe, reason = validate_sql_safety("DROP TABLE documents")
        assert not is_safe

    def test_rejects_alter(self):
        is_safe, reason = validate_sql_safety("ALTER TABLE documents ADD COLUMN x TEXT")
        assert not is_safe

    def test_rejects_truncate(self):
        is_safe, reason = validate_sql_safety("TRUNCATE documents")
        assert not is_safe

    def test_rejects_create(self):
        is_safe, reason = validate_sql_safety("CREATE TABLE evil (id INT)")
        assert not is_safe

    def test_rejects_forbidden_tables(self):
        is_safe, reason = validate_sql_safety("SELECT * FROM users WHERE matter_id = :matter_id LIMIT 10")
        assert not is_safe
        assert "Forbidden table" in reason

    def test_rejects_audit_log(self):
        is_safe, reason = validate_sql_safety("SELECT * FROM audit_log WHERE matter_id = :matter_id LIMIT 10")
        assert not is_safe

    def test_rejects_ai_audit_log(self):
        is_safe, reason = validate_sql_safety("SELECT * FROM ai_audit_log WHERE matter_id = :matter_id LIMIT 10")
        assert not is_safe

    def test_requires_matter_id(self):
        is_safe, reason = validate_sql_safety("SELECT * FROM documents LIMIT 10")
        assert not is_safe
        assert "matter_id" in reason

    def test_requires_limit(self):
        is_safe, reason = validate_sql_safety("SELECT * FROM documents WHERE matter_id = :matter_id")
        assert not is_safe
        assert "LIMIT" in reason

    def test_accepts_valid_query(self):
        is_safe, reason = validate_sql_safety(
            "SELECT filename, document_type FROM documents WHERE matter_id = :matter_id LIMIT 50"
        )
        assert is_safe
        assert reason == ""

    def test_accepts_complex_valid_query(self):
        is_safe, reason = validate_sql_safety(
            "SELECT d.filename, COUNT(a.id) FROM documents d "
            "JOIN annotations a ON d.id = a.document_id "
            "WHERE d.matter_id = :matter_id "
            "GROUP BY d.filename ORDER BY COUNT(a.id) DESC LIMIT 20"
        )
        assert is_safe


class TestEnsureLimit:
    def test_injects_limit_when_missing(self):
        sql = "SELECT * FROM documents WHERE matter_id = :matter_id"
        result = ensure_limit(sql, max_limit=100)
        assert "LIMIT 100" in result

    def test_caps_excessive_limit(self):
        sql = "SELECT * FROM documents LIMIT 5000"
        result = ensure_limit(sql, max_limit=100)
        assert "LIMIT 100" in result
        assert "LIMIT 5000" not in result

    def test_keeps_reasonable_limit(self):
        sql = "SELECT * FROM documents LIMIT 20"
        result = ensure_limit(sql, max_limit=100)
        assert "LIMIT 20" in result


class TestEnsureMatterId:
    def test_noop_when_present(self):
        sql = "SELECT * FROM documents WHERE matter_id = :matter_id LIMIT 10"
        result = ensure_matter_id(sql)
        assert result == sql

    def test_injects_into_existing_where(self):
        sql = "SELECT * FROM documents WHERE filename = 'test.pdf' LIMIT 10"
        result = ensure_matter_id(sql)
        assert ":matter_id" in result

    def test_injects_before_limit(self):
        sql = "SELECT * FROM documents LIMIT 10"
        result = ensure_matter_id(sql)
        assert "matter_id = :matter_id" in result
        assert "WHERE" in result


class TestParseSQLResponse:
    def test_parses_json(self):
        raw = json.dumps(
            {
                "sql": "SELECT * FROM documents WHERE matter_id = :matter_id LIMIT 10",
                "explanation": "test",
                "tables_used": ["documents"],
            }
        )
        result = _parse_sql_response(raw)
        assert "SELECT" in result.sql
        assert result.tables_used == ["documents"]

    def test_parses_json_in_text(self):
        raw = (
            "Here is the query:\n"
            '{"sql": "SELECT COUNT(*) FROM documents WHERE matter_id = :matter_id LIMIT 1", '
            '"explanation": "count", "tables_used": ["documents"]}\n'
        )
        result = _parse_sql_response(raw)
        assert "SELECT" in result.sql

    def test_raw_fallback(self):
        raw = "SELECT * FROM documents WHERE matter_id = :matter_id LIMIT 10"
        result = _parse_sql_response(raw)
        assert "SELECT" in result.sql


class TestAllowedTables:
    def test_documents_is_allowed(self):
        assert "documents" in ALLOWED_TABLES

    def test_annotations_is_allowed(self):
        assert "annotations" in ALLOWED_TABLES

    def test_memos_is_allowed(self):
        assert "memos" in ALLOWED_TABLES

    def test_communication_pairs_is_allowed(self):
        assert "communication_pairs" in ALLOWED_TABLES

    def test_users_is_not_allowed(self):
        assert "users" not in ALLOWED_TABLES

    def test_audit_log_is_not_allowed(self):
        assert "audit_log" not in ALLOWED_TABLES

    def test_ai_audit_log_is_not_allowed(self):
        assert "ai_audit_log" not in ALLOWED_TABLES

    def test_llm_providers_is_not_allowed(self):
        assert "llm_providers" not in ALLOWED_TABLES


class TestValidateForbiddenTables:
    def test_rejects_google_drive_connections(self):
        is_safe, reason = validate_sql_safety(
            "SELECT * FROM google_drive_connections WHERE matter_id = :matter_id LIMIT 10"
        )
        assert not is_safe
        assert "Forbidden table" in reason

    def test_rejects_agent_audit_log(self):
        is_safe, reason = validate_sql_safety("SELECT * FROM agent_audit_log WHERE matter_id = :matter_id LIMIT 10")
        assert not is_safe
        assert "Forbidden table" in reason

    def test_rejects_feature_flag_overrides(self):
        is_safe, reason = validate_sql_safety(
            "SELECT * FROM feature_flag_overrides WHERE matter_id = :matter_id LIMIT 10"
        )
        assert not is_safe
        assert "Forbidden table" in reason

    def test_rejects_retention_policies(self):
        is_safe, reason = validate_sql_safety("SELECT * FROM retention_policies WHERE matter_id = :matter_id LIMIT 10")
        assert not is_safe
        assert "Forbidden table" in reason


class TestExecuteSQL:
    @pytest.mark.asyncio
    async def test_execute_sql_returns_rows(self):
        """execute_sql executes query and returns list of dicts."""
        from unittest.mock import MagicMock, patch

        from app.query.sql_generator import execute_sql

        mock_row = MagicMock()
        mock_row._mapping = {"filename": "test.pdf", "cnt": 5}

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        async def _fake_get_db():
            yield mock_db

        with patch("app.dependencies.get_db", _fake_get_db):
            rows = await execute_sql(
                "SELECT filename, COUNT(*) AS cnt FROM documents WHERE matter_id = :matter_id GROUP BY filename LIMIT 10",
                "matter-123",
            )

        assert len(rows) == 1
        assert rows[0]["filename"] == "test.pdf"
        assert rows[0]["cnt"] == 5

    @pytest.mark.asyncio
    async def test_execute_sql_injects_matter_id(self):
        """execute_sql ensures matter_id parameter is present."""
        from unittest.mock import MagicMock, patch

        from app.query.sql_generator import execute_sql

        mock_result = MagicMock()
        mock_result.all.return_value = []

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        async def _fake_get_db():
            yield mock_db

        with patch("app.dependencies.get_db", _fake_get_db):
            await execute_sql(
                "SELECT COUNT(*) FROM documents LIMIT 10",
                "matter-456",
            )

        # The SQL should have had matter_id injected
        call_args = mock_db.execute.call_args
        executed_sql = str(call_args[0][0])
        assert "matter_id" in executed_sql
        assert call_args[0][1]["matter_id"] == "matter-456"
