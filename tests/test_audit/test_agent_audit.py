"""Tests for agent monitoring: agent_audit_log population, query methods, and API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# 1. AuditService.log_agent_action INSERT verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_agent_action_inserts_correct_params() -> None:
    """log_agent_action should INSERT into agent_audit_log with correct SQL params."""
    from app.audit.service import AuditService

    mock_session = AsyncMock()

    await AuditService.log_agent_action(
        mock_session,
        agent_id="investigation_agent",
        request_id="req-789",
        matter_id=uuid4(),
        action_type="tool_call",
        action_name="vector_search",
        iteration_number=2,
        duration_ms=150.5,
        status="success",
    )

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    sql_text = str(call_args[0][0])
    assert "INSERT INTO agent_audit_log" in sql_text

    params = call_args[0][1]
    assert params["agent_id"] == "investigation_agent"
    assert params["action_type"] == "tool_call"
    assert params["action_name"] == "vector_search"
    assert params["iteration_number"] == 2
    assert params["duration_ms"] == 150.5
    assert params["status"] == "success"

    mock_session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# 2. AuditService.list_agent_audit_logs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_agent_audit_logs_with_filters() -> None:
    """list_agent_audit_logs should filter by agent_id and action_type."""
    from app.audit.service import AuditService

    mock_count_result = MagicMock()
    mock_count_result.scalar_one.return_value = 0

    mock_data_result = MagicMock()
    mock_data_result.mappings.return_value.all.return_value = []

    call_count = 0

    async def mock_execute(query, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_count_result
        return mock_data_result

    mock_session = AsyncMock()
    mock_session.execute = mock_execute

    rows, total = await AuditService.list_agent_audit_logs(
        mock_session,
        agent_id="case_setup",
        action_type="node",
    )

    assert total == 0
    assert rows == []
    assert call_count == 2


@pytest.mark.asyncio
async def test_list_agent_audit_logs_returns_rows() -> None:
    """list_agent_audit_logs should return rows when data exists."""
    from app.audit.service import AuditService

    fake_row = {
        "id": uuid4(),
        "session_id": None,
        "agent_id": "investigation_agent",
        "request_id": "req-1",
        "user_id": None,
        "matter_id": uuid4(),
        "action_type": "tool_call",
        "action_name": "vector_search",
        "input_summary": None,
        "output_summary": None,
        "iteration_number": 1,
        "duration_ms": 42.5,
        "status": "success",
        "created_at": datetime.now(UTC),
    }

    mock_count_result = MagicMock()
    mock_count_result.scalar_one.return_value = 1

    mock_data_result = MagicMock()
    mock_data_result.mappings.return_value.all.return_value = [fake_row]

    call_count = 0

    async def mock_execute(query, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_count_result
        return mock_data_result

    mock_session = AsyncMock()
    mock_session.execute = mock_execute

    rows, total = await AuditService.list_agent_audit_logs(mock_session)

    assert total == 1
    assert len(rows) == 1
    assert rows[0]["agent_id"] == "investigation_agent"
    assert rows[0]["action_name"] == "vector_search"


# ---------------------------------------------------------------------------
# 3. AuditService.get_agent_summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_agent_summary() -> None:
    """get_agent_summary should return aggregate metrics per agent."""
    from app.audit.service import AuditService

    fake_summary = {
        "agent_id": "investigation_agent",
        "total_actions": 50,
        "avg_duration_ms": 120.5,
        "error_count": 2,
        "tool_call_count": 30,
        "node_count": 0,
        "distinct_tools": 8,
        "first_seen": datetime.now(UTC),
        "last_seen": datetime.now(UTC),
    }

    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [fake_summary]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    rows = await AuditService.get_agent_summary(mock_session)

    assert len(rows) == 1
    assert rows[0]["agent_id"] == "investigation_agent"
    assert rows[0]["total_actions"] == 50
    assert rows[0]["error_count"] == 2


# ---------------------------------------------------------------------------
# 4. AuditService.get_tool_distribution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_tool_distribution() -> None:
    """get_tool_distribution should return tool usage counts."""
    from app.audit.service import AuditService

    fake_tools = [
        {"tool_name": "vector_search", "call_count": 25},
        {"tool_name": "graph_query", "call_count": 10},
    ]

    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = fake_tools

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    rows = await AuditService.get_tool_distribution(mock_session)

    assert len(rows) == 2
    assert rows[0]["tool_name"] == "vector_search"
    assert rows[0]["call_count"] == 25


# ---------------------------------------------------------------------------
# 5. Agent audit API endpoint: GET /admin/audit/agents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_audit_endpoint_admin_200(client: AsyncClient) -> None:
    """Admin can access GET /admin/audit/agents."""
    fake_rows = [
        {
            "id": uuid4(),
            "session_id": None,
            "agent_id": "case_setup",
            "request_id": "req-1",
            "user_id": None,
            "matter_id": uuid4(),
            "action_type": "node",
            "action_name": "extract_claims",
            "input_summary": None,
            "output_summary": None,
            "iteration_number": None,
            "duration_ms": 1500.0,
            "status": "success",
            "created_at": datetime.now(UTC),
        }
    ]

    mock_count_result = MagicMock()
    mock_count_result.scalar_one.return_value = 1

    mock_data_result = MagicMock()
    mock_data_result.mappings.return_value.all.return_value = fake_rows

    call_count = 0

    async def mock_execute(query, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_count_result
        return mock_data_result

    from app.dependencies import get_db

    async def mock_get_db():
        mock_session = AsyncMock()
        mock_session.execute = mock_execute
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        yield mock_session

    client._transport.app.dependency_overrides[get_db] = mock_get_db

    try:
        response = await client.get("/api/v1/admin/audit/agents")
    finally:
        del client._transport.app.dependency_overrides[get_db]

    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["agent_id"] == "case_setup"
    assert body["items"][0]["action_name"] == "extract_claims"


# ---------------------------------------------------------------------------
# 6. Agent summary API endpoint: GET /admin/audit/agents/summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_summary_endpoint(client: AsyncClient) -> None:
    """Admin can access GET /admin/audit/agents/summary."""
    fake_summary = [
        {
            "agent_id": "investigation_agent",
            "total_actions": 100,
            "avg_duration_ms": 200.0,
            "error_count": 3,
            "tool_call_count": 60,
            "node_count": 0,
            "distinct_tools": 10,
            "first_seen": datetime.now(UTC),
            "last_seen": datetime.now(UTC),
        }
    ]

    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = fake_summary

    from app.dependencies import get_db

    async def mock_get_db():
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        yield mock_session

    client._transport.app.dependency_overrides[get_db] = mock_get_db

    try:
        response = await client.get("/api/v1/admin/audit/agents/summary")
    finally:
        del client._transport.app.dependency_overrides[get_db]

    assert response.status_code == 200
    body = response.json()
    assert "agents" in body
    assert len(body["agents"]) == 1
    assert body["agents"][0]["agent_id"] == "investigation_agent"
    assert body["agents"][0]["total_actions"] == 100
    assert body["agents"][0]["tool_call_count"] == 60


# ---------------------------------------------------------------------------
# 7. Tool distribution API endpoint: GET /admin/audit/agents/tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_distribution_endpoint(client: AsyncClient) -> None:
    """Admin can access GET /admin/audit/agents/tools."""
    fake_tools = [
        {"tool_name": "vector_search", "call_count": 25},
        {"tool_name": "graph_query", "call_count": 10},
    ]

    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = fake_tools

    from app.dependencies import get_db

    async def mock_get_db():
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        yield mock_session

    client._transport.app.dependency_overrides[get_db] = mock_get_db

    try:
        response = await client.get("/api/v1/admin/audit/agents/tools")
    finally:
        del client._transport.app.dependency_overrides[get_db]

    assert response.status_code == 200
    body = response.json()
    assert "tools" in body
    assert len(body["tools"]) == 2
    assert body["tools"][0]["tool_name"] == "vector_search"


# ---------------------------------------------------------------------------
# 8. Agent audit endpoint — non-admin 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_audit_endpoint_non_admin_403(client: AsyncClient) -> None:
    """Non-admin users get 403 on agent audit endpoints."""
    from app.auth.middleware import get_current_user
    from app.auth.schemas import UserRecord

    reviewer_user = UserRecord(
        id=UUID("00000000-0000-0000-0000-000000000077"),
        email="reviewer@nexus.dev",
        full_name="Doc Reviewer",
        role="reviewer",
        is_active=True,
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
    )

    client._transport.app.dependency_overrides[get_current_user] = lambda: reviewer_user

    try:
        response = await client.get("/api/v1/admin/audit/agents")
    finally:
        from tests.conftest import _TEST_USER

        client._transport.app.dependency_overrides[get_current_user] = lambda: _TEST_USER

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# 9. log_agent_node decorator — sync wrapper
# ---------------------------------------------------------------------------


def test_log_agent_node_sync_wrapper() -> None:
    """log_agent_node should wrap sync functions and track duration."""
    from app.common.agent_logging import log_agent_node

    call_log: list[dict] = []

    # Patch the sync writer to capture calls instead of hitting DB
    with patch("app.common.agent_logging._write_agent_audit_sync") as mock_write:

        @log_agent_node("test_agent", "test_node", postgres_url=None)
        def my_node(state: dict) -> dict:
            return {"result": "ok"}

        result = my_node({"matter_id": "test-matter"})

    assert result == {"result": "ok"}
    mock_write.assert_called_once()
    call_kwargs = mock_write.call_args[1]
    assert call_kwargs["agent_id"] == "test_agent"
    assert call_kwargs["node_name"] == "test_node"
    assert call_kwargs["matter_id"] == "test-matter"
    assert call_kwargs["status"] == "success"
    assert call_kwargs["duration_ms"] >= 0


# ---------------------------------------------------------------------------
# 10. log_agent_node decorator — async wrapper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_agent_node_async_wrapper() -> None:
    """log_agent_node should wrap async functions and track duration."""
    from app.common.agent_logging import log_agent_node

    with patch("app.common.agent_logging._write_agent_audit") as mock_write:
        mock_write.return_value = None  # make it awaitable via AsyncMock behavior

        @log_agent_node("test_agent", "async_node", postgres_url=None)
        async def my_async_node(state: dict) -> dict:
            return {"async_result": "done"}

        # Patch create_task since we're not in a full event loop context with tasks
        with patch("asyncio.create_task"):
            result = await my_async_node({"matter_id": "async-matter"})

    assert result == {"async_result": "done"}


# ---------------------------------------------------------------------------
# 11. log_agent_node decorator — error tracking
# ---------------------------------------------------------------------------


def test_log_agent_node_tracks_errors() -> None:
    """log_agent_node should set status='error' when the node raises."""
    from app.common.agent_logging import log_agent_node

    with patch("app.common.agent_logging._write_agent_audit_sync") as mock_write:

        @log_agent_node("test_agent", "failing_node", postgres_url=None)
        def failing_node(state: dict) -> dict:
            raise ValueError("something broke")

        with pytest.raises(ValueError, match="something broke"):
            failing_node({"matter_id": "test-matter"})

    mock_write.assert_called_once()
    call_kwargs = mock_write.call_args[1]
    assert call_kwargs["status"] == "error"
    assert "something broke" in (call_kwargs["output_summary"] or "")


# ---------------------------------------------------------------------------
# 12. Schemas validation
# ---------------------------------------------------------------------------


def test_agent_audit_log_entry_schema() -> None:
    """AgentAuditLogEntry should accept valid data."""
    from app.audit.schemas import AgentAuditLogEntry

    entry = AgentAuditLogEntry(
        id=uuid4(),
        agent_id="investigation_agent",
        action_type="tool_call",
        action_name="vector_search",
        iteration_number=3,
        duration_ms=150.5,
        status="success",
        created_at=datetime.now(UTC),
    )
    assert entry.agent_id == "investigation_agent"
    assert entry.iteration_number == 3


def test_agent_summary_entry_schema() -> None:
    """AgentSummaryEntry should accept valid data."""
    from app.audit.schemas import AgentSummaryEntry

    entry = AgentSummaryEntry(
        agent_id="case_setup",
        total_actions=50,
        avg_duration_ms=120.5,
        error_count=2,
        tool_call_count=30,
        node_count=20,
        distinct_tools=5,
    )
    assert entry.agent_id == "case_setup"
    assert entry.total_actions == 50


def test_tool_distribution_entry_schema() -> None:
    """ToolDistributionEntry should accept valid data."""
    from app.audit.schemas import ToolDistributionEntry

    entry = ToolDistributionEntry(tool_name="vector_search", call_count=25)
    assert entry.tool_name == "vector_search"
    assert entry.call_count == 25
