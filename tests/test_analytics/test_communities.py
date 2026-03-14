"""Tests for GraphRAG community detection and summarization (T3-10).

Covers:
- CommunityDetector.detect_communities (Neo4j GDS mocked)
- CommunityDetector.build_hierarchy
- CommunityDetector.summarize_community (LLM mocked)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_community(
    entity_names: list[str],
    matter_id: str = "test-matter",
    level: int = 0,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "matter_id": matter_id,
        "level": level,
        "parent_id": None,
        "entity_names": entity_names,
        "relationship_types": [],
        "summary": None,
        "entity_count": len(entity_names),
    }


# ---------------------------------------------------------------------------
# TestCommunityDetection
# ---------------------------------------------------------------------------


class TestCommunityDetection:
    @pytest.mark.asyncio
    async def test_detect_communities_returns_groups(self):
        """Communities are grouped by communityId from Louvain results."""
        from app.analytics.communities import CommunityDetector

        mock_result = AsyncMock()
        mock_result.data.return_value = [
            {"name": "Alice", "type": "person", "communityId": 0},
            {"name": "Bob", "type": "person", "communityId": 0},
            {"name": "Corp X", "type": "organization", "communityId": 1},
        ]

        mock_session = AsyncMock()
        mock_session.run.return_value = mock_result

        mock_driver = MagicMock()
        mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_gs = MagicMock()
        mock_gs._driver = mock_driver

        communities = await CommunityDetector.detect_communities("test-matter", mock_gs)

        assert len(communities) == 2
        counts = sorted([c["entity_count"] for c in communities])
        assert counts == [1, 2]

    @pytest.mark.asyncio
    async def test_detect_communities_empty_graph(self):
        """Empty graph returns no communities."""
        from app.analytics.communities import CommunityDetector

        mock_result = AsyncMock()
        mock_result.data.return_value = []

        mock_session = AsyncMock()
        mock_session.run.return_value = mock_result

        mock_driver = MagicMock()
        mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_gs = MagicMock()
        mock_gs._driver = mock_driver

        communities = await CommunityDetector.detect_communities("test-matter", mock_gs)
        assert communities == []

    @pytest.mark.asyncio
    async def test_detect_communities_single_community(self):
        """All entities in one community."""
        from app.analytics.communities import CommunityDetector

        mock_result = AsyncMock()
        mock_result.data.return_value = [
            {"name": "Alice", "type": "person", "communityId": 0},
            {"name": "Bob", "type": "person", "communityId": 0},
            {"name": "Carol", "type": "person", "communityId": 0},
        ]

        mock_session = AsyncMock()
        mock_session.run.return_value = mock_result

        mock_driver = MagicMock()
        mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_gs = MagicMock()
        mock_gs._driver = mock_driver

        communities = await CommunityDetector.detect_communities("test-matter", mock_gs)
        assert len(communities) == 1
        assert communities[0]["entity_count"] == 3
        assert set(communities[0]["entity_names"]) == {"Alice", "Bob", "Carol"}

    @pytest.mark.asyncio
    async def test_detect_communities_multiple_communities(self):
        """Multiple distinct communities."""
        from app.analytics.communities import CommunityDetector

        mock_result = AsyncMock()
        mock_result.data.return_value = [
            {"name": "A", "type": "person", "communityId": 0},
            {"name": "B", "type": "person", "communityId": 1},
            {"name": "C", "type": "person", "communityId": 2},
            {"name": "D", "type": "person", "communityId": 0},
        ]

        mock_session = AsyncMock()
        mock_session.run.return_value = mock_result

        mock_driver = MagicMock()
        mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_gs = MagicMock()
        mock_gs._driver = mock_driver

        communities = await CommunityDetector.detect_communities("test-matter", mock_gs)
        assert len(communities) == 3

    @pytest.mark.asyncio
    async def test_detect_communities_drops_graph_projection(self):
        """Graph projection is dropped after detection (cleanup)."""
        from app.analytics.communities import CommunityDetector

        mock_result = AsyncMock()
        mock_result.data.return_value = []

        mock_session = AsyncMock()
        mock_session.run.return_value = mock_result

        mock_driver = MagicMock()
        mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_gs = MagicMock()
        mock_gs._driver = mock_driver

        await CommunityDetector.detect_communities("test-matter", mock_gs)

        # session.run is called: drop (initial), project, louvain, drop (cleanup)
        assert mock_session.run.call_count == 4


# ---------------------------------------------------------------------------
# TestBuildHierarchy
# ---------------------------------------------------------------------------


class TestBuildHierarchy:
    def test_hierarchy_merges_small_communities(self):
        from app.analytics.communities import CommunityDetector

        communities = [
            _make_community(["A", "B", "C", "D"]),  # large (4 >= 3)
            _make_community(["E"]),  # small
            _make_community(["F", "G"]),  # small
        ]

        result = CommunityDetector.build_hierarchy(communities, min_size=3)

        # Should have: original large + parent + 2 small
        parents = [c for c in result if c["level"] == 1]
        assert len(parents) == 1
        assert parents[0]["entity_count"] == 3  # E + F + G

    def test_hierarchy_preserves_large_communities(self):
        from app.analytics.communities import CommunityDetector

        communities = [
            _make_community(["A", "B", "C"]),
            _make_community(["D", "E", "F", "G"]),
        ]

        result = CommunityDetector.build_hierarchy(communities, min_size=3)

        # All large, no parent created (no small communities)
        parents = [c for c in result if c["level"] == 1]
        assert len(parents) == 0

    def test_hierarchy_all_large(self):
        from app.analytics.communities import CommunityDetector

        communities = [
            _make_community(["A", "B", "C"]),
            _make_community(["D", "E", "F"]),
        ]

        result = CommunityDetector.build_hierarchy(communities, min_size=3)
        assert len(result) == 2
        assert all(c["parent_id"] is None for c in result)

    def test_hierarchy_all_small(self):
        from app.analytics.communities import CommunityDetector

        communities = [
            _make_community(["A"]),
            _make_community(["B"]),
        ]

        result = CommunityDetector.build_hierarchy(communities, min_size=3)

        # 1 parent + 2 small
        assert len(result) == 3
        parents = [c for c in result if c["level"] == 1]
        assert len(parents) == 1
        assert parents[0]["entity_count"] == 2

    def test_hierarchy_assigns_parent_ids(self):
        from app.analytics.communities import CommunityDetector

        communities = [
            _make_community(["A"]),
            _make_community(["B"]),
        ]

        result = CommunityDetector.build_hierarchy(communities, min_size=3)

        parents = [c for c in result if c["level"] == 1]
        children = [c for c in result if c["level"] == 0]

        assert len(parents) == 1
        parent_id = parents[0]["id"]
        for child in children:
            assert child["parent_id"] == parent_id


# ---------------------------------------------------------------------------
# TestSummarizeCommunity
# ---------------------------------------------------------------------------


class TestSummarizeCommunity:
    @pytest.mark.asyncio
    async def test_summarize_calls_llm(self):
        from app.analytics.communities import CommunityDetector

        community = _make_community(["Alice Smith", "Bob Jones", "Corp X"])
        community["relationship_types"] = ["SENT_TO", "WORKS_FOR"]

        mock_llm = AsyncMock()
        mock_llm.complete.return_value = "Alice and Bob are connected via Corp X."

        summary = await CommunityDetector.summarize_community(community, mock_llm)

        assert summary == "Alice and Bob are connected via Corp X."
        mock_llm.complete.assert_called_once()
        call_args = mock_llm.complete.call_args
        assert call_args.kwargs["max_tokens"] == 200
        assert call_args.kwargs["temperature"] == 0.3

    @pytest.mark.asyncio
    async def test_summarize_truncates_large_communities(self):
        from app.analytics.communities import CommunityDetector

        # Community with 30 entities — should truncate to 20 in prompt
        names = [f"Entity_{i}" for i in range(30)]
        community = _make_community(names)

        mock_llm = AsyncMock()
        mock_llm.complete.return_value = "Large community summary."

        await CommunityDetector.summarize_community(community, mock_llm)

        call_args = mock_llm.complete.call_args
        prompt_content = call_args.args[0][0]["content"]
        # Only first 20 should appear in entity details
        assert "Entity_19" in prompt_content
        assert "Entity_20" not in prompt_content

    @pytest.mark.asyncio
    async def test_summarize_handles_empty_rels(self):
        from app.analytics.communities import CommunityDetector

        community = _make_community(["Alice"])
        # No relationship_types set (empty list)

        mock_llm = AsyncMock()
        mock_llm.complete.return_value = "Single entity community."

        await CommunityDetector.summarize_community(community, mock_llm)

        call_args = mock_llm.complete.call_args
        prompt_content = call_args.args[0][0]["content"]
        assert "unknown" in prompt_content
