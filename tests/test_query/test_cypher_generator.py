"""Tests for T1-2: Text-to-Cypher generation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.query.cypher_generator import (
    CypherQuery,
    _parse_cypher_response,
    ensure_limit,
    generate_cypher,
    validate_cypher_safety,
)


@pytest.fixture
def mock_llm():
    return AsyncMock()


class TestGenerateCypher:
    @pytest.mark.asyncio
    async def test_basic_generation(self, mock_llm):
        """Verify generate_cypher produces a CypherQuery."""
        mock_llm.complete = AsyncMock(
            return_value=json.dumps(
                {
                    "cypher": "MATCH (e:Entity) WHERE e.matter_id = $matter_id RETURN e.name LIMIT 20",
                    "params": {},
                    "explanation": "Find all entities in the matter",
                }
            )
        )

        result = await generate_cypher("Show me all entities", "matter-123", mock_llm)

        assert isinstance(result, CypherQuery)
        assert "MATCH" in result.cypher
        assert result.params["matter_id"] == "matter-123"


class TestValidateCypherSafety:
    def test_rejects_create(self):
        is_safe, reason = validate_cypher_safety("CREATE (n:Node {name: 'test'})")
        assert not is_safe
        assert "Write operation" in reason

    def test_rejects_delete(self):
        is_safe, reason = validate_cypher_safety("MATCH (n) WHERE n.matter_id = $matter_id DELETE n LIMIT 10")
        assert not is_safe
        assert "Write operation" in reason

    def test_rejects_set(self):
        is_safe, reason = validate_cypher_safety("MATCH (n) WHERE n.matter_id = $matter_id SET n.name = 'x' LIMIT 10")
        assert not is_safe

    def test_rejects_merge(self):
        is_safe, reason = validate_cypher_safety("MERGE (n:Entity {name: 'test', matter_id: $matter_id}) LIMIT 10")
        assert not is_safe

    def test_rejects_drop(self):
        is_safe, reason = validate_cypher_safety("DROP INDEX index_name")
        assert not is_safe

    def test_requires_matter_id(self):
        is_safe, reason = validate_cypher_safety("MATCH (n:Entity) RETURN n.name LIMIT 10")
        assert not is_safe
        assert "matter_id" in reason

    def test_requires_limit(self):
        is_safe, reason = validate_cypher_safety("MATCH (n:Entity) WHERE n.matter_id = $matter_id RETURN n.name")
        assert not is_safe
        assert "LIMIT" in reason

    def test_accepts_valid_query(self):
        is_safe, reason = validate_cypher_safety(
            "MATCH (e:Entity)-[:RELATED_TO]-(e2:Entity) WHERE e.matter_id = $matter_id RETURN e.name, e2.name LIMIT 20"
        )
        assert is_safe
        assert reason == ""


class TestEnsureLimit:
    def test_injects_limit_when_missing(self):
        cypher = "MATCH (n) RETURN n"
        result = ensure_limit(cypher, max_limit=50)
        assert "LIMIT 50" in result

    def test_caps_excessive_limit(self):
        cypher = "MATCH (n) RETURN n LIMIT 1000"
        result = ensure_limit(cypher, max_limit=50)
        assert "LIMIT 50" in result
        assert "LIMIT 1000" not in result

    def test_keeps_reasonable_limit(self):
        cypher = "MATCH (n) RETURN n LIMIT 20"
        result = ensure_limit(cypher, max_limit=50)
        assert "LIMIT 20" in result


class TestParseCypherResponse:
    def test_parses_json(self):
        raw = json.dumps(
            {
                "cypher": "MATCH (n) RETURN n LIMIT 10",
                "params": {},
                "explanation": "test",
            }
        )
        result = _parse_cypher_response(raw)
        assert "MATCH" in result.cypher

    def test_parses_json_in_text(self):
        raw = 'Here is the query:\n{"cypher": "MATCH (n) RETURN n LIMIT 10", "params": {}, "explanation": "test"}\n'
        result = _parse_cypher_response(raw)
        assert "MATCH" in result.cypher

    def test_raw_fallback(self):
        raw = "MATCH (n) RETURN n LIMIT 10"
        result = _parse_cypher_response(raw)
        assert "MATCH" in result.cypher
