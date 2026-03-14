"""Tests for the get_community_context LangGraph tool (T3-10).

Covers:
- Tool invocation with InjectedState for matter_id extraction
- Entity found / not found scenarios
- Feature flag disabled
- Missing matter context
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_get_community_context_found():
    """Tool returns community info when entity is found."""
    from app.query.tools import get_community_context

    mock_row = {
        "id": "c1",
        "entity_names": ["Alice Smith", "Bob Jones"],
        "relationship_types": ["SENT_TO"],
        "summary": "Alice and Bob communicated frequently.",
        "entity_count": 2,
        "level": 0,
    }

    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = mock_row

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    async def _mock_get_db():
        yield mock_db

    mock_settings = MagicMock()
    mock_settings.enable_graphrag_communities = True

    state = {"_filters": {"matter_id": "test-matter-001"}}

    with (
        patch("app.dependencies.get_settings", return_value=mock_settings),
        patch("app.dependencies.get_db", _mock_get_db),
    ):
        result = await get_community_context.ainvoke({"entity_name": "Alice Smith", "state": state})

    parsed = json.loads(result)
    assert parsed["community_id"] == "c1"
    assert parsed["entity_count"] == 2
    assert "Alice Smith" in parsed["members"]
    assert parsed["summary"] == "Alice and Bob communicated frequently."


@pytest.mark.asyncio
async def test_get_community_context_not_found():
    """Tool returns error when entity is not in any community."""
    from app.query.tools import get_community_context

    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = None

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    async def _mock_get_db():
        yield mock_db

    mock_settings = MagicMock()
    mock_settings.enable_graphrag_communities = True

    state = {"_filters": {"matter_id": "test-matter-001"}}

    with (
        patch("app.dependencies.get_settings", return_value=mock_settings),
        patch("app.dependencies.get_db", _mock_get_db),
    ):
        result = await get_community_context.ainvoke({"entity_name": "Unknown Person", "state": state})

    parsed = json.loads(result)
    assert "error" in parsed
    assert "No community found" in parsed["error"]


@pytest.mark.asyncio
async def test_get_community_context_flag_disabled():
    """Tool returns info message when feature flag is disabled."""
    from app.query.tools import get_community_context

    mock_settings = MagicMock()
    mock_settings.enable_graphrag_communities = False

    state = {"_filters": {"matter_id": "test-matter-001"}}

    with patch("app.dependencies.get_settings", return_value=mock_settings):
        result = await get_community_context.ainvoke({"entity_name": "Alice", "state": state})

    parsed = json.loads(result)
    assert "info" in parsed
    assert "not enabled" in parsed["info"]


@pytest.mark.asyncio
async def test_get_community_context_no_matter():
    """Tool returns error when no matter_id in state."""
    from app.query.tools import get_community_context

    mock_settings = MagicMock()
    mock_settings.enable_graphrag_communities = True

    state = {"_filters": {}}

    with patch("app.dependencies.get_settings", return_value=mock_settings):
        result = await get_community_context.ainvoke({"entity_name": "Alice", "state": state})

    parsed = json.loads(result)
    assert "error" in parsed
    assert "No matter context" in parsed["error"]
