"""Tests for the audit logging middleware."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.common.middleware import AuditLoggingMiddleware, _derive_resource_type, _get_client_ip


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


def test_derive_resource_type_documents():
    """Extracts 'documents' from /api/v1/documents/xxx."""
    assert _derive_resource_type("/api/v1/documents/abc-123") == "documents"


def test_derive_resource_type_query():
    """Extracts 'query' from /api/v1/query."""
    assert _derive_resource_type("/api/v1/query") == "query"


def test_derive_resource_type_no_match():
    """Returns None for non-API paths."""
    assert _derive_resource_type("/docs") is None


def test_get_client_ip_forwarded():
    """Prefers X-Forwarded-For when present."""
    request = MagicMock()
    request.headers = {"X-Forwarded-For": "10.0.0.1, 192.168.1.1"}
    assert _get_client_ip(request) == "10.0.0.1"


def test_get_client_ip_direct():
    """Falls back to request.client.host."""
    request = MagicMock()
    request.headers = {}
    request.client.host = "127.0.0.1"
    assert _get_client_ip(request) == "127.0.0.1"


# ---------------------------------------------------------------------------
# Middleware integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_middleware_writes_log() -> None:
    """Audit middleware calls _write_audit_log with correct params."""
    mock_request = MagicMock()
    mock_request.url.path = "/api/v1/documents"
    mock_request.method = "GET"
    mock_request.state.request_id = "test-req-id"
    mock_request.state.user = {
        "id": "00000000-0000-0000-0000-000000000099",
        "email": "test@nexus.dev",
    }
    mock_request.headers = {"X-Matter-ID": "00000000-0000-0000-0000-000000000001"}
    mock_request.client.host = "127.0.0.1"

    mock_response = MagicMock()
    mock_response.status_code = 200

    async def mock_call_next(request):
        return mock_response

    with patch.object(
        AuditLoggingMiddleware, "_write_audit_log", new_callable=AsyncMock
    ) as mock_write:
        middleware = AuditLoggingMiddleware(app=MagicMock())
        await middleware.dispatch(mock_request, mock_call_next)

        mock_write.assert_called_once()
        args = mock_write.call_args[0]
        assert args[0] is mock_request  # request
        assert args[1] == 200  # status_code


@pytest.mark.asyncio
async def test_audit_middleware_handles_unauthenticated() -> None:
    """Audit middleware handles routes without user (user_id=None)."""
    mock_request = MagicMock()
    mock_request.url.path = "/api/v1/auth/login"
    mock_request.method = "POST"
    mock_request.headers = {}
    mock_request.client.host = "127.0.0.1"

    # Simulate no user on request.state
    del mock_request.state.user

    mock_response = MagicMock()
    mock_response.status_code = 200

    async def mock_call_next(request):
        return mock_response

    with patch.object(
        AuditLoggingMiddleware, "_write_audit_log", new_callable=AsyncMock
    ) as mock_write:
        middleware = AuditLoggingMiddleware(app=MagicMock())
        await middleware.dispatch(mock_request, mock_call_next)

        mock_write.assert_called_once()


@pytest.mark.asyncio
async def test_audit_middleware_skips_health() -> None:
    """Audit middleware does NOT log /api/v1/health requests."""
    mock_request = MagicMock()
    mock_request.url.path = "/api/v1/health"

    mock_response = MagicMock()
    mock_response.status_code = 200

    async def mock_call_next(request):
        return mock_response

    with patch.object(
        AuditLoggingMiddleware, "_write_audit_log", new_callable=AsyncMock
    ) as mock_write:
        middleware = AuditLoggingMiddleware(app=MagicMock())
        await middleware.dispatch(mock_request, mock_call_next)

        mock_write.assert_not_called()
