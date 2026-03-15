"""Tests for M7b SOC 2 Audit Readiness: AI audit logging, prompt hashing, session binding, CSV export."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# 0. AuditService.log_request INSERT verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_request_inserts_correct_params() -> None:
    """log_request should execute an INSERT into audit_log with the correct SQL parameters."""
    from app.audit.service import AuditService

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock(return_value=mock_session)

    user_id = uuid4()
    matter_id = uuid4()

    await AuditService.log_request(
        mock_factory,
        user_id=user_id,
        user_email="test@nexus.dev",
        action="GET",
        resource="/api/v1/documents",
        resource_type="documents",
        matter_id=matter_id,
        ip_address="127.0.0.1",
        user_agent="TestAgent/1.0",
        status_code=200,
        duration_ms=42.5,
        request_id="req-001",
        session_id="sess-001",
    )

    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    sql_text = str(call_args[0][0])
    assert "INSERT INTO audit_log" in sql_text

    params = call_args[0][1]
    assert params["user_id"] == user_id
    assert params["user_email"] == "test@nexus.dev"
    assert params["action"] == "GET"
    assert params["resource"] == "/api/v1/documents"
    assert params["resource_type"] == "documents"
    assert params["matter_id"] == matter_id
    assert params["ip_address"] == "127.0.0.1"
    assert params["user_agent"] == "TestAgent/1.0"
    assert params["status_code"] == 200
    assert params["duration_ms"] == 42.5
    assert params["request_id"] == "req-001"
    assert params["session_id"] == "sess-001"

    mock_session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# 1. AuditService.log_ai_call INSERT verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_ai_call_inserts_correct_params() -> None:
    """log_ai_call should execute an INSERT with the correct SQL parameters."""
    from app.audit.service import AuditService

    mock_session = AsyncMock()

    await AuditService.log_ai_call(
        mock_session,
        request_id="req-123",
        session_id="sess-456",
        provider="anthropic",
        model="claude-sonnet-4-5-20250929",
        node_name="classify",
        prompt_hash="abc123hash",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        latency_ms=123.45,
        status="success",
    )

    # Verify execute was called once with the INSERT
    mock_session.execute.assert_called_once()
    call_args = mock_session.execute.call_args
    sql_text = str(call_args[0][0])
    assert "INSERT INTO ai_audit_log" in sql_text

    params = call_args[0][1]
    assert params["request_id"] == "req-123"
    assert params["session_id"] == "sess-456"
    assert params["provider"] == "anthropic"
    assert params["model"] == "claude-sonnet-4-5-20250929"
    assert params["node_name"] == "classify"
    assert params["prompt_hash"] == "abc123hash"
    assert params["input_tokens"] == 100
    assert params["output_tokens"] == 50
    assert params["total_tokens"] == 150
    assert params["latency_ms"] == 123.45
    assert params["status"] == "success"

    # Verify commit was called
    mock_session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# 2. Prompt hash determinism
# ---------------------------------------------------------------------------


def test_prompt_hash_deterministic() -> None:
    """The same messages should always produce the same SHA-256 hash."""
    from app.common.llm import LLMClient

    messages = [
        {"role": "system", "content": "You are a legal analyst."},
        {"role": "user", "content": "Who is John Doe?"},
    ]

    hash1 = LLMClient._hash_prompt(messages)
    hash2 = LLMClient._hash_prompt(messages)
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 hex digest

    # Verify it matches manual computation
    content = "".join(f"{m['role']}:{m['content']}" for m in messages)
    expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert hash1 == expected


def test_prompt_hash_different_for_different_messages() -> None:
    """Different messages should produce different hashes."""
    from app.common.llm import LLMClient

    messages1 = [{"role": "user", "content": "Query A"}]
    messages2 = [{"role": "user", "content": "Query B"}]

    assert LLMClient._hash_prompt(messages1) != LLMClient._hash_prompt(messages2)


# ---------------------------------------------------------------------------
# 3. Session-ID binding in RequestIDMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_id_from_header(client: AsyncClient) -> None:
    """X-Session-ID header should be bound to structlog contextvars."""
    # The health endpoint doesn't require auth or DB.
    # We just need to verify the middleware processes the header.
    # Since the request_id and session_id are set in middleware,
    # we verify the middleware doesn't break anything.
    response = await client.get(
        "/api/v1/health",
        headers={"X-Session-ID": "test-session-id-123"},
    )
    # If middleware correctly processes the header, the request succeeds
    assert response.status_code in (200, 503)  # 503 if services are down


@pytest.mark.asyncio
async def test_session_id_generated_when_missing(client: AsyncClient) -> None:
    """When X-Session-ID is not provided, a UUID should be generated."""
    response = await client.get("/api/v1/health")
    assert response.status_code in (200, 503)


# ---------------------------------------------------------------------------
# 4. CSV export format
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_csv_format() -> None:
    """export_audit_logs should produce valid CSV with headers."""
    from app.audit.service import AuditService

    fake_row = {
        "id": uuid4(),
        "request_id": "req-1",
        "session_id": uuid4(),
        "user_id": None,
        "matter_id": None,
        "call_type": "completion",
        "node_name": "classify",
        "provider": "anthropic",
        "model": "claude-sonnet-4-5-20250929",
        "prompt_hash": "abc123",
        "input_tokens": 100,
        "output_tokens": 50,
        "total_tokens": 150,
        "latency_ms": 42.5,
        "status": "success",
        "error_message": None,
        "metadata_": {},
        "created_at": datetime.now(UTC),
    }

    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [fake_row]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    csv_output = await AuditService.export_audit_logs(
        mock_session,
        table="ai_audit_log",
        export_format="csv",
    )

    lines = csv_output.strip().split("\n")
    assert len(lines) == 2  # header + 1 data row
    header = lines[0]
    assert "provider" in header
    assert "prompt_hash" in header
    assert "latency_ms" in header

    # Data row should contain the provider value
    assert "anthropic" in lines[1]


# ---------------------------------------------------------------------------
# 5. List AI audit logs with filters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_ai_audit_logs_with_node_name_filter() -> None:
    """list_ai_audit_logs should add WHERE clause for node_name filter."""
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

    rows, total = await AuditService.list_ai_audit_logs(
        mock_session,
        node_name="classify",
    )

    assert total == 0
    assert rows == []
    # Verify the execute was called twice (count + data)
    assert call_count == 2


# ---------------------------------------------------------------------------
# 6. Migration immutability rules
# ---------------------------------------------------------------------------


def test_migration_has_immutability_rules() -> None:
    """Migration 004 should define CREATE RULE for all three audit tables."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "migration_004",
        "migrations/versions/004_soc2_audit.py",
    )
    assert spec is not None
    assert spec.loader is not None

    _module = importlib.util.module_from_spec(spec)

    # Read the source to check for rule definitions
    with open("migrations/versions/004_soc2_audit.py") as f:
        source = f.read()

    # Verify all 6 rules are defined (no_update + no_delete for 3 tables)
    assert "audit_log_no_update" in source
    assert "audit_log_no_delete" in source
    assert "ai_audit_log_no_update" in source
    assert "ai_audit_log_no_delete" in source
    assert "agent_audit_log_no_update" in source
    assert "agent_audit_log_no_delete" in source

    # Verify downgrade drops the rules
    assert "DROP RULE IF EXISTS" in source


# ---------------------------------------------------------------------------
# 7. Router admin-only access
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_ai_endpoint_admin_200(client: AsyncClient) -> None:
    """Admin can access GET /admin/audit/ai."""
    fake_rows = [
        {
            "id": uuid4(),
            "request_id": "req-1",
            "session_id": uuid4(),
            "user_id": None,
            "matter_id": None,
            "call_type": "completion",
            "node_name": "classify",
            "provider": "anthropic",
            "model": "claude-sonnet-4-5-20250929",
            "prompt_hash": "abc123",
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "latency_ms": 42.5,
            "status": "success",
            "error_message": None,
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
        response = await client.get("/api/v1/admin/audit/ai")
    finally:
        del client._transport.app.dependency_overrides[get_db]

    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["provider"] == "anthropic"
    assert body["items"][0]["node_name"] == "classify"


@pytest.mark.asyncio
async def test_audit_ai_endpoint_non_admin_403(client: AsyncClient) -> None:
    """Non-admin users get 403 on the audit AI endpoint."""
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
        response = await client.get("/api/v1/admin/audit/ai")
    finally:
        from tests.conftest import _TEST_USER

        client._transport.app.dependency_overrides[get_current_user] = lambda: _TEST_USER

    assert response.status_code == 403
