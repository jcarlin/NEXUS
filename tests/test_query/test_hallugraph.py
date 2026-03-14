"""Tests for T3-9: HalluGraph Entity-Graph Alignment."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.query.nodes import hallugraph_check


@dataclass
class _FakeEntity:
    """Mimics ExtractedEntity from app.entities.extractor."""

    text: str
    type: str
    score: float = 0.9
    start: int = 0
    end: int = 0


class TestHallugraphCheck:
    """Tests for the hallugraph_check node function."""

    @pytest.mark.asyncio
    async def test_skips_when_disabled(self):
        """Returns empty list when feature flag is off."""
        state = {"response": "Jeffrey Epstein flew to the island."}
        with patch("app.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.enable_hallugraph_alignment = False
            result = await hallugraph_check(state)
        assert result == {"entity_grounding": []}

    @pytest.mark.asyncio
    async def test_skips_empty_response(self):
        """Returns empty list when response is empty."""
        state = {"response": ""}
        with patch("app.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.enable_hallugraph_alignment = True
            result = await hallugraph_check(state)
        assert result == {"entity_grounding": []}

    @pytest.mark.asyncio
    async def test_skips_missing_response(self):
        """Returns empty list when response key is absent."""
        state = {}
        with patch("app.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.enable_hallugraph_alignment = True
            result = await hallugraph_check(state)
        assert result == {"entity_grounding": []}

    @pytest.mark.asyncio
    async def test_extracts_entities_from_response(self):
        """Calls GLiNER extractor on the response text."""
        fake_entities = [_FakeEntity(text="Epstein", type="person")]

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = fake_entities

        mock_graph = AsyncMock()
        mock_graph.get_entity_by_name = AsyncMock(return_value={"name": "Epstein"})

        state = {"response": "Epstein flew to the island."}

        with (
            patch("app.dependencies.get_settings") as mock_settings,
            patch("app.dependencies.get_entity_extractor", return_value=mock_extractor),
            patch("app.dependencies.get_graph_service", return_value=mock_graph),
        ):
            mock_settings.return_value.enable_hallugraph_alignment = True
            result = await hallugraph_check(state)

        mock_extractor.extract.assert_called_once()
        assert len(result["entity_grounding"]) == 1

    @pytest.mark.asyncio
    async def test_deduplicates_entities(self):
        """Same entity name (case-insensitive) only checked once."""
        fake_entities = [
            _FakeEntity(text="Epstein", type="person"),
            _FakeEntity(text="epstein", type="person"),
            _FakeEntity(text="EPSTEIN", type="person"),
        ]

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = fake_entities

        mock_graph = AsyncMock()
        mock_graph.get_entity_by_name = AsyncMock(return_value={"name": "Epstein"})

        state = {"response": "Epstein met epstein and EPSTEIN."}

        with (
            patch("app.dependencies.get_settings") as mock_settings,
            patch("app.dependencies.get_entity_extractor", return_value=mock_extractor),
            patch("app.dependencies.get_graph_service", return_value=mock_graph),
        ):
            mock_settings.return_value.enable_hallugraph_alignment = True
            result = await hallugraph_check(state)

        assert len(result["entity_grounding"]) == 1
        assert result["entity_grounding"][0]["name"] == "Epstein"

    @pytest.mark.asyncio
    async def test_all_entities_grounded(self):
        """When all entities exist in KG, all marked grounded=True."""
        fake_entities = [
            _FakeEntity(text="Epstein", type="person"),
            _FakeEntity(text="Maxwell", type="person"),
        ]

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = fake_entities

        mock_graph = AsyncMock()
        mock_graph.get_entity_by_name = AsyncMock(return_value={"name": "found"})

        state = {"response": "Epstein and Maxwell were connected."}

        with (
            patch("app.dependencies.get_settings") as mock_settings,
            patch("app.dependencies.get_entity_extractor", return_value=mock_extractor),
            patch("app.dependencies.get_graph_service", return_value=mock_graph),
        ):
            mock_settings.return_value.enable_hallugraph_alignment = True
            result = await hallugraph_check(state)

        assert len(result["entity_grounding"]) == 2
        assert all(g["grounded"] is True for g in result["entity_grounding"])
        assert all(g["confidence"] == 1.0 for g in result["entity_grounding"])

    @pytest.mark.asyncio
    async def test_no_entities_grounded(self):
        """When no entities exist in KG, all marked grounded=False."""
        fake_entities = [
            _FakeEntity(text="FakeEntity1", type="person"),
            _FakeEntity(text="FakeEntity2", type="organization"),
        ]

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = fake_entities

        mock_graph = AsyncMock()
        mock_graph.get_entity_by_name = AsyncMock(return_value=None)
        mock_graph._run_query = AsyncMock(return_value=[])

        state = {"response": "FakeEntity1 met FakeEntity2."}

        with (
            patch("app.dependencies.get_settings") as mock_settings,
            patch("app.dependencies.get_entity_extractor", return_value=mock_extractor),
            patch("app.dependencies.get_graph_service", return_value=mock_graph),
        ):
            mock_settings.return_value.enable_hallugraph_alignment = True
            result = await hallugraph_check(state)

        assert len(result["entity_grounding"]) == 2
        assert all(g["grounded"] is False for g in result["entity_grounding"])
        assert all(g["confidence"] == 0.0 for g in result["entity_grounding"])
        assert all(g["closest_match"] is None for g in result["entity_grounding"])

    @pytest.mark.asyncio
    async def test_partial_grounding(self):
        """Mix of grounded and ungrounded entities."""
        fake_entities = [
            _FakeEntity(text="Epstein", type="person"),
            _FakeEntity(text="FakeOrg", type="organization"),
        ]

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = fake_entities

        mock_graph = AsyncMock()
        mock_graph.get_entity_by_name = AsyncMock(side_effect=[{"name": "Epstein"}, None])
        mock_graph._run_query = AsyncMock(return_value=[])

        state = {"response": "Epstein worked at FakeOrg."}

        with (
            patch("app.dependencies.get_settings") as mock_settings,
            patch("app.dependencies.get_entity_extractor", return_value=mock_extractor),
            patch("app.dependencies.get_graph_service", return_value=mock_graph),
        ):
            mock_settings.return_value.enable_hallugraph_alignment = True
            result = await hallugraph_check(state)

        assert len(result["entity_grounding"]) == 2
        grounded = [g for g in result["entity_grounding"] if g["grounded"]]
        ungrounded = [g for g in result["entity_grounding"] if not g["grounded"]]
        assert len(grounded) == 1
        assert grounded[0]["name"] == "Epstein"
        assert len(ungrounded) == 1
        assert ungrounded[0]["name"] == "FakeOrg"

    @pytest.mark.asyncio
    async def test_fuzzy_match_provides_closest(self):
        """Ungrounded entities get closest_match from fuzzy Cypher query."""
        fake_entities = [_FakeEntity(text="J. Epstein", type="person")]

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = fake_entities

        mock_graph = AsyncMock()
        mock_graph.get_entity_by_name = AsyncMock(return_value=None)
        mock_graph._run_query = AsyncMock(return_value=[{"name": "Jeffrey Epstein"}])

        state = {"response": "J. Epstein was mentioned."}

        with (
            patch("app.dependencies.get_settings") as mock_settings,
            patch("app.dependencies.get_entity_extractor", return_value=mock_extractor),
            patch("app.dependencies.get_graph_service", return_value=mock_graph),
        ):
            mock_settings.return_value.enable_hallugraph_alignment = True
            result = await hallugraph_check(state)

        assert len(result["entity_grounding"]) == 1
        assert result["entity_grounding"][0]["grounded"] is False
        assert result["entity_grounding"][0]["closest_match"] == "Jeffrey Epstein"

    @pytest.mark.asyncio
    async def test_fuzzy_match_no_results(self):
        """closest_match is None when fuzzy search returns nothing."""
        fake_entities = [_FakeEntity(text="CompletelyUnknown", type="person")]

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = fake_entities

        mock_graph = AsyncMock()
        mock_graph.get_entity_by_name = AsyncMock(return_value=None)
        mock_graph._run_query = AsyncMock(return_value=[])

        state = {"response": "CompletelyUnknown did something."}

        with (
            patch("app.dependencies.get_settings") as mock_settings,
            patch("app.dependencies.get_entity_extractor", return_value=mock_extractor),
            patch("app.dependencies.get_graph_service", return_value=mock_graph),
        ):
            mock_settings.return_value.enable_hallugraph_alignment = True
            result = await hallugraph_check(state)

        assert len(result["entity_grounding"]) == 1
        assert result["entity_grounding"][0]["closest_match"] is None

    @pytest.mark.asyncio
    async def test_graph_service_error_marks_ungrounded(self):
        """If Neo4j query fails, entity marked ungrounded."""
        fake_entities = [_FakeEntity(text="Epstein", type="person")]

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = fake_entities

        mock_graph = AsyncMock()
        mock_graph.get_entity_by_name = AsyncMock(side_effect=Exception("Neo4j down"))
        mock_graph._run_query = AsyncMock(side_effect=Exception("Neo4j down"))

        state = {"response": "Epstein was mentioned."}

        with (
            patch("app.dependencies.get_settings") as mock_settings,
            patch("app.dependencies.get_entity_extractor", return_value=mock_extractor),
            patch("app.dependencies.get_graph_service", return_value=mock_graph),
        ):
            mock_settings.return_value.enable_hallugraph_alignment = True
            result = await hallugraph_check(state)

        assert len(result["entity_grounding"]) == 1
        assert result["entity_grounding"][0]["grounded"] is False

    @pytest.mark.asyncio
    async def test_extractor_error_returns_empty(self):
        """If GLiNER extraction fails, returns empty list."""
        mock_extractor = MagicMock()
        mock_extractor.extract.side_effect = Exception("GLiNER failed")

        state = {"response": "Some text with entities."}

        with (
            patch("app.dependencies.get_settings") as mock_settings,
            patch("app.dependencies.get_entity_extractor", return_value=mock_extractor),
        ):
            mock_settings.return_value.enable_hallugraph_alignment = True
            result = await hallugraph_check(state)

        assert result == {"entity_grounding": []}

    def test_entity_grounding_in_agent_state(self):
        """Verify entity_grounding field exists in AgentState."""
        from app.query.graph import AgentState

        assert "entity_grounding" in AgentState.__annotations__

    @pytest.mark.asyncio
    async def test_matter_id_from_filters(self):
        """Verifies matter_id is extracted from _filters and passed to graph queries."""
        fake_entities = [_FakeEntity(text="Epstein", type="person")]

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = fake_entities

        mock_graph = AsyncMock()
        mock_graph.get_entity_by_name = AsyncMock(return_value={"name": "Epstein"})

        state = {
            "response": "Epstein was mentioned.",
            "_filters": {"matter_id": "test-matter-123"},
        }

        with (
            patch("app.dependencies.get_settings") as mock_settings,
            patch("app.dependencies.get_entity_extractor", return_value=mock_extractor),
            patch("app.dependencies.get_graph_service", return_value=mock_graph),
        ):
            mock_settings.return_value.enable_hallugraph_alignment = True
            result = await hallugraph_check(state)

        # Verify matter_id was passed through
        mock_graph.get_entity_by_name.assert_called_once_with("Epstein", matter_id="test-matter-123")
        assert len(result["entity_grounding"]) == 1
