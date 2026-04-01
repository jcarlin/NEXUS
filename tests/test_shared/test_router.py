"""Tests for the shareable chat links router endpoints."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.schemas import UserRecord

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TEST_USER = UserRecord(
    id=UUID("00000000-0000-0000-0000-000000000099"),
    email="test@nexus.dev",
    full_name="Test User",
    role="admin",
    is_active=True,
    password_hash="$2b$12$fake",
    api_key_hash=None,
    created_at=datetime(2025, 1, 1, tzinfo=UTC),
    updated_at=datetime(2025, 1, 1, tzinfo=UTC),
)

_TEST_MATTER_ID = UUID("00000000-0000-0000-0000-000000000001")
_TEST_THREAD_ID = "00000000-0000-0000-0000-000000000abc"


@pytest.fixture()
async def shared_client():
    """Yield an httpx AsyncClient with shareable links enabled."""
    from app import main as main_module
    from app.config import Settings

    async def _noop_lifespan(app):
        yield

    test_settings = Settings(
        enable_shareable_links=True,
        anthropic_api_key="test",
        openai_api_key="test",
    )

    with (
        patch.object(main_module, "lifespan", _noop_lifespan),
        patch("app.main.get_settings", return_value=test_settings),
    ):
        test_app = main_module.create_app()

        from app.auth.middleware import get_current_user, get_matter_id
        from app.common.rate_limit import rate_limit_ingests, rate_limit_queries

        test_app.dependency_overrides[rate_limit_queries] = lambda: None
        test_app.dependency_overrides[rate_limit_ingests] = lambda: None
        test_app.dependency_overrides[get_current_user] = lambda: _TEST_USER
        test_app.dependency_overrides[get_matter_id] = lambda: _TEST_MATTER_ID

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://testserver",
        ) as client:
            yield client


@pytest.fixture()
async def disabled_client():
    """Yield an httpx AsyncClient with shareable links disabled."""
    from app import main as main_module
    from app.config import Settings

    async def _noop_lifespan(app):
        yield

    test_settings = Settings(
        enable_shareable_links=False,
        anthropic_api_key="test",
        openai_api_key="test",
    )

    with (
        patch.object(main_module, "lifespan", _noop_lifespan),
        patch("app.main.get_settings", return_value=test_settings),
    ):
        test_app = main_module.create_app()

        from app.auth.middleware import get_current_user, get_matter_id
        from app.common.rate_limit import rate_limit_ingests, rate_limit_queries

        test_app.dependency_overrides[rate_limit_queries] = lambda: None
        test_app.dependency_overrides[rate_limit_ingests] = lambda: None
        test_app.dependency_overrides[get_current_user] = lambda: _TEST_USER
        test_app.dependency_overrides[get_matter_id] = lambda: _TEST_MATTER_ID

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://testserver",
        ) as client:
            yield client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_db():
    """Create a mock AsyncSession."""
    db = AsyncMock()
    return db


def _fake_share_record(**overrides):
    """Build a fake shared chat DB row."""
    defaults = {
        "id": uuid4(),
        "thread_id": UUID(_TEST_THREAD_ID),
        "matter_id": _TEST_MATTER_ID,
        "share_token": "test-token-abc123",
        "created_by": _TEST_USER.id,
        "created_at": datetime.now(UTC),
        "expires_at": None,
        "is_revoked": False,
        "view_count": 0,
        "allow_follow_ups": True,
    }
    defaults.update(overrides)
    return defaults


def _fake_messages():
    """Build fake chat messages."""
    return [
        {
            "role": "user",
            "content": "Who was on the flight logs?",
            "source_documents": [],
            "entities_mentioned": [],
            "follow_up_questions": [],
            "cited_claims": [],
            "tool_calls": [],
            "timestamp": datetime.now(UTC).isoformat(),
        },
        {
            "role": "assistant",
            "content": "Based on the documents, the flight logs show...",
            "source_documents": [
                {
                    "id": "chunk-1",
                    "doc_id": "doc-1",
                    "filename": "flight_log.pdf",
                    "page": 3,
                    "chunk_text": "Passenger manifest for...",
                    "relevance_score": 0.95,
                }
            ],
            "entities_mentioned": [{"name": "John Doe", "type": "PERSON"}],
            "follow_up_questions": ["What dates were the flights?"],
            "cited_claims": [],
            "tool_calls": [],
            "timestamp": datetime.now(UTC).isoformat(),
        },
    ]


# ---------------------------------------------------------------------------
# Tests: POST /chats/{thread_id}/share — create share link
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_share_link(shared_client: AsyncClient):
    """Creating a share link returns a token and URL."""
    with patch("app.shared.router.SharedChatService.create_share", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = {
            "share_token": "abc123_test_token",
            "expires_at": None,
        }

        resp = await shared_client.post(
            f"/api/v1/chats/{_TEST_THREAD_ID}/share",
            json={"allow_follow_ups": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["share_token"] == "abc123_test_token"
    assert "shared/" in data["share_url"]
    assert data["expires_at"] is None


@pytest.mark.asyncio
async def test_create_share_link_with_expiry(shared_client: AsyncClient):
    """Creating a share link with expiry sets expires_at."""
    future_date = datetime.now(UTC) + timedelta(days=7)
    with patch("app.shared.router.SharedChatService.create_share", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = {
            "share_token": "abc123_test_token",
            "expires_at": future_date,
        }

        resp = await shared_client.post(
            f"/api/v1/chats/{_TEST_THREAD_ID}/share",
            json={"allow_follow_ups": True, "expires_in_days": 7},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["expires_at"] is not None


@pytest.mark.asyncio
async def test_create_share_link_disabled(disabled_client: AsyncClient):
    """Creating a share link when feature is disabled returns 403."""
    resp = await disabled_client.post(
        f"/api/v1/chats/{_TEST_THREAD_ID}/share",
        json={"allow_follow_ups": True},
    )
    # When disabled, the auth router isn't mounted, so 404 or 405
    assert resp.status_code in (404, 405, 403)


@pytest.mark.asyncio
async def test_create_share_link_thread_not_found(shared_client: AsyncClient):
    """Creating a share link for non-existent thread returns 404."""
    with patch("app.shared.router.SharedChatService.create_share", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = ValueError("Thread not found or has no messages")

        resp = await shared_client.post(
            f"/api/v1/chats/{_TEST_THREAD_ID}/share",
            json={"allow_follow_ups": True},
        )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: DELETE /chats/{thread_id}/share — revoke share link
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_share_link(shared_client: AsyncClient):
    """Revoking a share link returns success."""
    with patch("app.shared.router.SharedChatService.revoke_share", new_callable=AsyncMock) as mock_revoke:
        mock_revoke.return_value = True

        resp = await shared_client.delete(f"/api/v1/chats/{_TEST_THREAD_ID}/share")

    assert resp.status_code == 200
    assert "revoked" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_revoke_share_link_not_found(shared_client: AsyncClient):
    """Revoking when no active share exists returns 404."""
    with patch("app.shared.router.SharedChatService.revoke_share", new_callable=AsyncMock) as mock_revoke:
        mock_revoke.return_value = False

        resp = await shared_client.delete(f"/api/v1/chats/{_TEST_THREAD_ID}/share")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: GET /shared/{share_token} — get shared conversation (public)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_shared_chat(shared_client: AsyncClient):
    """Getting a shared chat returns messages without auth."""
    share = _fake_share_record()
    messages = _fake_messages()

    with (
        patch("app.shared.router.SharedChatService.get_share_by_token", new_callable=AsyncMock) as mock_get,
        patch("app.shared.router.SharedChatService.load_shared_messages", new_callable=AsyncMock) as mock_msgs,
    ):
        mock_get.return_value = share
        mock_msgs.return_value = messages

        resp = await shared_client.get("/api/v1/shared/test-token-abc123")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["messages"]) == 2
    assert data["allow_follow_ups"] is True
    assert data["first_query"] == "Who was on the flight logs?"
    assert "flight logs show" in data["first_response_preview"]


@pytest.mark.asyncio
async def test_get_shared_chat_not_found(shared_client: AsyncClient):
    """Getting a non-existent shared chat returns 404."""
    with patch("app.shared.router.SharedChatService.get_share_by_token", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        resp = await shared_client.get("/api/v1/shared/nonexistent-token")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: GET /shared/{share_token}/og — OG meta tags HTML
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shared_chat_og_page(shared_client: AsyncClient):
    """OG page returns HTML with Open Graph meta tags."""
    share = _fake_share_record()
    messages = _fake_messages()

    with (
        patch("app.shared.router.SharedChatService.get_share_by_token", new_callable=AsyncMock) as mock_get,
        patch("app.shared.router.SharedChatService.load_shared_messages", new_callable=AsyncMock) as mock_msgs,
    ):
        mock_get.return_value = share
        mock_msgs.return_value = messages

        resp = await shared_client.get("/api/v1/shared/test-token-abc123/og")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")

    html = resp.text
    assert "og:title" in html
    assert "og:description" in html
    assert "og:site_name" in html
    assert "NEXUS" in html
    assert "twitter:card" in html
    assert "QAPage" in html  # JSON-LD
    assert "robots" in html
    assert "flight logs" in html.lower()


@pytest.mark.asyncio
async def test_shared_chat_og_page_not_found(shared_client: AsyncClient):
    """OG page for non-existent token returns 404 HTML."""
    with patch("app.shared.router.SharedChatService.get_share_by_token", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        resp = await shared_client.get("/api/v1/shared/bad-token/og")

    assert resp.status_code == 404
    assert "not found" in resp.text.lower()


# ---------------------------------------------------------------------------
# Tests: Service unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_create_share_generates_token():
    """SharedChatService.create_share generates a cryptographic token."""
    from app.shared.service import SharedChatService

    mock_db = AsyncMock()

    # Simulate thread has messages
    count_result = MagicMock()
    count_result.scalar.return_value = 5

    # Simulate no existing share
    existing_result = MagicMock()
    existing_result.mappings.return_value.first.return_value = None

    mock_db.execute = AsyncMock(side_effect=[count_result, existing_result, AsyncMock()])

    result = await SharedChatService.create_share(
        db=mock_db,
        thread_id=_TEST_THREAD_ID,
        matter_id=_TEST_MATTER_ID,
        user_id=_TEST_USER.id,
    )

    assert "share_token" in result
    assert len(result["share_token"]) == 22  # base64url of 16 bytes
    assert result["expires_at"] is None


@pytest.mark.asyncio
async def test_service_create_share_returns_existing():
    """SharedChatService.create_share returns existing active share."""
    from app.shared.service import SharedChatService

    mock_db = AsyncMock()

    count_result = MagicMock()
    count_result.scalar.return_value = 5

    existing_result = MagicMock()
    existing_result.mappings.return_value.first.return_value = {
        "share_token": "existing-token",
        "expires_at": None,
    }

    mock_db.execute = AsyncMock(side_effect=[count_result, existing_result])

    result = await SharedChatService.create_share(
        db=mock_db,
        thread_id=_TEST_THREAD_ID,
        matter_id=_TEST_MATTER_ID,
        user_id=_TEST_USER.id,
    )

    assert result["share_token"] == "existing-token"


@pytest.mark.asyncio
async def test_service_create_share_empty_thread_raises():
    """SharedChatService.create_share raises for empty thread."""
    from app.shared.service import SharedChatService

    mock_db = AsyncMock()

    count_result = MagicMock()
    count_result.scalar.return_value = 0

    mock_db.execute = AsyncMock(return_value=count_result)

    with pytest.raises(ValueError, match="Thread not found"):
        await SharedChatService.create_share(
            db=mock_db,
            thread_id=_TEST_THREAD_ID,
            matter_id=_TEST_MATTER_ID,
            user_id=_TEST_USER.id,
        )


@pytest.mark.asyncio
async def test_service_get_share_expired():
    """SharedChatService.get_share_by_token returns None for expired share."""
    from app.shared.service import SharedChatService

    mock_db = AsyncMock()

    result = MagicMock()
    result.mappings.return_value.first.return_value = {
        "id": uuid4(),
        "thread_id": UUID(_TEST_THREAD_ID),
        "matter_id": _TEST_MATTER_ID,
        "share_token": "expired-token",
        "created_by": _TEST_USER.id,
        "created_at": datetime.now(UTC) - timedelta(days=10),
        "expires_at": datetime.now(UTC) - timedelta(days=3),
        "is_revoked": False,
        "view_count": 5,
        "allow_follow_ups": True,
    }

    mock_db.execute = AsyncMock(return_value=result)

    share = await SharedChatService.get_share_by_token(mock_db, "expired-token")
    assert share is None


@pytest.mark.asyncio
async def test_service_get_share_revoked():
    """SharedChatService.get_share_by_token returns None for revoked share."""
    from app.shared.service import SharedChatService

    mock_db = AsyncMock()

    result = MagicMock()
    result.mappings.return_value.first.return_value = {
        "id": uuid4(),
        "thread_id": UUID(_TEST_THREAD_ID),
        "matter_id": _TEST_MATTER_ID,
        "share_token": "revoked-token",
        "created_by": _TEST_USER.id,
        "created_at": datetime.now(UTC),
        "expires_at": None,
        "is_revoked": True,
        "view_count": 5,
        "allow_follow_ups": True,
    }

    mock_db.execute = AsyncMock(return_value=result)

    share = await SharedChatService.get_share_by_token(mock_db, "revoked-token")
    assert share is None


@pytest.mark.asyncio
async def test_service_revoke_share():
    """SharedChatService.revoke_share returns True when shares are revoked."""
    from app.shared.service import SharedChatService

    mock_db = AsyncMock()

    result = MagicMock()
    result.rowcount = 2

    mock_db.execute = AsyncMock(return_value=result)

    revoked = await SharedChatService.revoke_share(mock_db, _TEST_THREAD_ID, _TEST_USER.id)
    assert revoked is True


@pytest.mark.asyncio
async def test_service_revoke_share_none_found():
    """SharedChatService.revoke_share returns False when nothing to revoke."""
    from app.shared.service import SharedChatService

    mock_db = AsyncMock()

    result = MagicMock()
    result.rowcount = 0

    mock_db.execute = AsyncMock(return_value=result)

    revoked = await SharedChatService.revoke_share(mock_db, _TEST_THREAD_ID, _TEST_USER.id)
    assert revoked is False


# ---------------------------------------------------------------------------
# Tests: Schema validation
# ---------------------------------------------------------------------------


def test_create_share_request_defaults():
    """CreateShareRequest has correct defaults."""
    from app.shared.schemas import CreateShareRequest

    req = CreateShareRequest()
    assert req.allow_follow_ups is True
    assert req.expires_in_days is None


def test_create_share_request_expiry_bounds():
    """CreateShareRequest validates expiry bounds."""
    from pydantic import ValidationError

    from app.shared.schemas import CreateShareRequest

    # Valid
    req = CreateShareRequest(expires_in_days=30)
    assert req.expires_in_days == 30

    # Too low
    with pytest.raises(ValidationError):
        CreateShareRequest(expires_in_days=0)

    # Too high
    with pytest.raises(ValidationError):
        CreateShareRequest(expires_in_days=91)


def test_shared_query_request_validation():
    """SharedQueryRequest validates query length."""
    from pydantic import ValidationError

    from app.shared.schemas import SharedQueryRequest

    # Valid
    req = SharedQueryRequest(query="What happened next?")
    assert req.query == "What happened next?"

    # Empty
    with pytest.raises(ValidationError):
        SharedQueryRequest(query="")


def test_shared_query_request_too_long():
    """SharedQueryRequest rejects query longer than 4000 chars."""
    from pydantic import ValidationError

    from app.shared.schemas import SharedQueryRequest

    with pytest.raises(ValidationError):
        SharedQueryRequest(query="x" * 4001)


# ---------------------------------------------------------------------------
# Fixtures: SSE reset (required for sse-starlette across tests)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_sse_status():
    """Reset sse-starlette's AppStatus between tests."""
    try:
        from sse_starlette.sse import AppStatus

        AppStatus.should_exit_event = asyncio.Event()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helpers: SSE parsing
# ---------------------------------------------------------------------------


def _parse_sse_events(text: str) -> list[dict]:
    """Parse SSE text into a list of {event, data} dicts."""
    events = []
    current_event = None
    for line in text.split("\n"):
        if line.startswith("event: "):
            current_event = line[7:].strip()
        elif line.startswith("data: ") and current_event:
            try:
                data = json.loads(line[6:])
            except json.JSONDecodeError:
                data = line[6:]
            events.append({"event": current_event, "data": data})
            current_event = None
    return events


# ---------------------------------------------------------------------------
# Helpers: shared streaming fixtures
# ---------------------------------------------------------------------------


def _stream_share_record(**overrides):
    """Build a valid share record for streaming tests."""
    defaults = _fake_share_record()
    defaults["allow_follow_ups"] = True
    defaults.update(overrides)
    return defaults


def _mock_settings(agentic: bool = False):
    """Create a mock settings object for streaming tests."""
    s = MagicMock()
    s.enable_shareable_links = True
    s.enable_agentic_pipeline = agentic
    s.cors_allowed_origins = ""
    return s


# ---------------------------------------------------------------------------
# Tests: POST /shared/{share_token}/query/stream — V1 pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shared_stream_v1_happy_path(shared_client: AsyncClient):
    """V1 streaming returns status, token, sources, and done SSE events."""
    share = _stream_share_record()

    async def fake_astream(state, config, stream_mode=None):
        yield ("updates", {"classify": {"query_type": "factual"}})
        yield ("updates", {"rewrite": {"rewritten_query": "test"}})
        yield ("updates", {"rerank": {"source_documents": [{"id": "doc-1", "filename": "test.pdf"}]}})
        yield ("custom", {"type": "token", "text": "Hello "})
        yield ("custom", {"type": "token", "text": "world"})

    mock_graph = MagicMock()
    mock_graph.astream = fake_astream

    with (
        patch("app.shared.router.SharedChatService.get_share_by_token", new_callable=AsyncMock, return_value=share),
        patch("app.common.rate_limit.rate_limit_shared_queries", new_callable=AsyncMock),
        patch("app.shared.router.ChatService.load_thread_messages", new_callable=AsyncMock, return_value=[]),
        patch("app.shared.router.ChatService.save_message", new_callable=AsyncMock) as mock_save,
        patch("app.shared.router.QueryService.build_v1_state", new_callable=AsyncMock, return_value={}),
        patch("app.shared.router.QueryService.build_graph_config", return_value={}),
        patch("app.shared.router.QueryService.extract_response", return_value="Hello world"),
        patch("app.dependencies.get_query_graph", return_value=mock_graph),
        patch("app.shared.router.get_settings", return_value=_mock_settings(agentic=False)),
    ):
        resp = await shared_client.post(
            "/api/v1/shared/test-token-abc123/query/stream",
            json={"query": "What happened?"},
        )

    assert resp.status_code == 200
    events = _parse_sse_events(resp.text)

    event_types = [e["event"] for e in events]
    assert "status" in event_types
    assert "token" in event_types
    assert "sources" in event_types
    assert "done" in event_types

    # Check sources content
    sources_evt = next(e for e in events if e["event"] == "sources")
    assert sources_evt["data"]["documents"][0]["id"] == "doc-1"

    # Check token content
    token_texts = [e["data"]["text"] for e in events if e["event"] == "token"]
    assert "Hello " in token_texts
    assert "world" in token_texts

    # Check done event
    done_evt = next(e for e in events if e["event"] == "done")
    assert "thread_id" in done_evt["data"]

    # Verify messages saved (user + assistant)
    assert mock_save.call_count == 2
    user_call = mock_save.call_args_list[0]
    assert user_call.args[2] == "user"
    assistant_call = mock_save.call_args_list[1]
    assert assistant_call.args[2] == "assistant"


@pytest.mark.asyncio
async def test_shared_stream_v1_privilege_filtering(shared_client: AsyncClient):
    """V1 streaming passes exclude_privilege for shared users."""
    share = _stream_share_record()

    async def fake_astream(state, config, stream_mode=None):
        yield ("custom", {"type": "token", "text": "ok"})

    mock_graph = MagicMock()
    mock_graph.astream = fake_astream

    with (
        patch("app.shared.router.SharedChatService.get_share_by_token", new_callable=AsyncMock, return_value=share),
        patch("app.common.rate_limit.rate_limit_shared_queries", new_callable=AsyncMock),
        patch("app.shared.router.ChatService.load_thread_messages", new_callable=AsyncMock, return_value=[]),
        patch("app.shared.router.ChatService.save_message", new_callable=AsyncMock),
        patch("app.shared.router.QueryService.build_v1_state", new_callable=AsyncMock, return_value={}) as mock_build,
        patch("app.shared.router.QueryService.build_graph_config", return_value={}),
        patch("app.shared.router.QueryService.extract_response", return_value="ok"),
        patch("app.dependencies.get_query_graph", return_value=mock_graph),
        patch("app.shared.router.get_settings", return_value=_mock_settings(agentic=False)),
    ):
        await shared_client.post(
            "/api/v1/shared/test-token-abc123/query/stream",
            json={"query": "test"},
        )

    # Verify exclude_privilege was passed
    call_kwargs = mock_build.call_args
    assert call_kwargs.kwargs.get("exclude_privilege") == ["privileged", "work_product"]


@pytest.mark.asyncio
async def test_shared_stream_v1_graph_error(shared_client: AsyncClient):
    """V1 streaming yields error event on graph exception."""
    share = _stream_share_record()

    async def failing_astream(state, config, stream_mode=None):
        yield ("updates", {"classify": {"query_type": "factual"}})
        raise RuntimeError("Graph exploded")

    mock_graph = MagicMock()
    mock_graph.astream = failing_astream

    with (
        patch("app.shared.router.SharedChatService.get_share_by_token", new_callable=AsyncMock, return_value=share),
        patch("app.common.rate_limit.rate_limit_shared_queries", new_callable=AsyncMock),
        patch("app.shared.router.ChatService.load_thread_messages", new_callable=AsyncMock, return_value=[]),
        patch("app.shared.router.ChatService.save_message", new_callable=AsyncMock),
        patch("app.shared.router.QueryService.build_v1_state", new_callable=AsyncMock, return_value={}),
        patch("app.shared.router.QueryService.build_graph_config", return_value={}),
        patch("app.dependencies.get_query_graph", return_value=mock_graph),
        patch("app.shared.router.get_settings", return_value=_mock_settings(agentic=False)),
    ):
        resp = await shared_client.post(
            "/api/v1/shared/test-token-abc123/query/stream",
            json={"query": "test"},
        )

    assert resp.status_code == 200  # SSE always 200, errors are events
    events = _parse_sse_events(resp.text)
    error_events = [e for e in events if e["event"] == "error"]
    assert len(error_events) == 1
    assert "failed" in error_events[0]["data"]["message"].lower()


# ---------------------------------------------------------------------------
# Tests: POST /shared/{share_token}/query/stream — agentic pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shared_stream_agentic_happy_path(shared_client: AsyncClient):
    """Agentic streaming returns status, token, and done events."""
    from langchain_core.messages import AIMessageChunk

    share = _stream_share_record()

    async def fake_astream(state, config, stream_mode=None):
        yield ("updates", {"case_context_resolve": {"context": "resolved"}})
        yield ("messages", (AIMessageChunk(content="Hello "), {"langgraph_node": "investigation_agent"}))
        yield ("messages", (AIMessageChunk(content="world"), {"langgraph_node": "investigation_agent"}))
        yield ("updates", {"verify_citations": {"citations_verified": True}})
        yield ("custom", {"type": "sources", "documents": [{"id": "d1"}]})

    mock_graph = MagicMock()
    mock_graph.astream = fake_astream

    with (
        patch("app.shared.router.SharedChatService.get_share_by_token", new_callable=AsyncMock, return_value=share),
        patch("app.common.rate_limit.rate_limit_shared_queries", new_callable=AsyncMock),
        patch("app.shared.router.ChatService.load_thread_messages", new_callable=AsyncMock, return_value=[]),
        patch("app.shared.router.ChatService.save_message", new_callable=AsyncMock),
        patch("app.shared.router.QueryService.build_agentic_state", return_value={}),
        patch("app.shared.router.QueryService.build_graph_config", return_value={}),
        patch("app.shared.router.QueryService.extract_response", return_value="Hello world"),
        patch("app.dependencies.get_query_graph", return_value=mock_graph),
        patch("app.shared.router.get_settings", return_value=_mock_settings(agentic=True)),
    ):
        resp = await shared_client.post(
            "/api/v1/shared/test-token-abc123/query/stream",
            json={"query": "Who is connected?"},
        )

    assert resp.status_code == 200
    events = _parse_sse_events(resp.text)

    event_types = [e["event"] for e in events]
    assert "status" in event_types
    assert "token" in event_types
    assert "sources" in event_types
    assert "done" in event_types

    # Token events from investigation_agent messages
    token_texts = [e["data"]["text"] for e in events if e["event"] == "token"]
    assert "Hello " in token_texts
    assert "world" in token_texts


@pytest.mark.asyncio
async def test_shared_stream_agentic_ignores_non_agent_messages(shared_client: AsyncClient):
    """Agentic streaming ignores messages from nodes other than investigation/post_agent_extract."""
    from langchain_core.messages import AIMessageChunk

    share = _stream_share_record()

    async def fake_astream(state, config, stream_mode=None):
        # This message is from a different node — should be ignored
        yield ("messages", (AIMessageChunk(content="ignored"), {"langgraph_node": "classify"}))
        yield ("messages", (AIMessageChunk(content="visible"), {"langgraph_node": "post_agent_extract"}))

    mock_graph = MagicMock()
    mock_graph.astream = fake_astream

    with (
        patch("app.shared.router.SharedChatService.get_share_by_token", new_callable=AsyncMock, return_value=share),
        patch("app.common.rate_limit.rate_limit_shared_queries", new_callable=AsyncMock),
        patch("app.shared.router.ChatService.load_thread_messages", new_callable=AsyncMock, return_value=[]),
        patch("app.shared.router.ChatService.save_message", new_callable=AsyncMock),
        patch("app.shared.router.QueryService.build_agentic_state", return_value={}),
        patch("app.shared.router.QueryService.build_graph_config", return_value={}),
        patch("app.shared.router.QueryService.extract_response", return_value="visible"),
        patch("app.dependencies.get_query_graph", return_value=mock_graph),
        patch("app.shared.router.get_settings", return_value=_mock_settings(agentic=True)),
    ):
        resp = await shared_client.post(
            "/api/v1/shared/test-token-abc123/query/stream",
            json={"query": "test"},
        )

    events = _parse_sse_events(resp.text)
    token_texts = [e["data"]["text"] for e in events if e["event"] == "token"]
    assert "ignored" not in token_texts
    assert "visible" in token_texts


# ---------------------------------------------------------------------------
# Tests: POST /shared/{share_token}/query/stream — access control
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shared_stream_follow_ups_disabled(shared_client: AsyncClient):
    """Streaming returns 403 when follow-ups are disabled."""
    share = _stream_share_record(allow_follow_ups=False)

    with (
        patch("app.shared.router.SharedChatService.get_share_by_token", new_callable=AsyncMock, return_value=share),
        patch("app.common.rate_limit.rate_limit_shared_queries", new_callable=AsyncMock),
    ):
        resp = await shared_client.post(
            "/api/v1/shared/test-token-abc123/query/stream",
            json={"query": "test"},
        )

    assert resp.status_code == 403
    assert "disabled" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_shared_stream_expired_share(shared_client: AsyncClient):
    """Streaming returns 404 for expired share."""
    with (
        patch("app.shared.router.SharedChatService.get_share_by_token", new_callable=AsyncMock, return_value=None),
        patch("app.common.rate_limit.rate_limit_shared_queries", new_callable=AsyncMock),
    ):
        resp = await shared_client.post(
            "/api/v1/shared/expired-token/query/stream",
            json={"query": "test"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_shared_stream_revoked_share(shared_client: AsyncClient):
    """Streaming returns 404 for revoked share."""
    with (
        patch("app.shared.router.SharedChatService.get_share_by_token", new_callable=AsyncMock, return_value=None),
        patch("app.common.rate_limit.rate_limit_shared_queries", new_callable=AsyncMock),
    ):
        resp = await shared_client.post(
            "/api/v1/shared/revoked-token/query/stream",
            json={"query": "test"},
        )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: Rate limiting for shared queries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_shared_queries_enforced():
    """rate_limit_shared_queries raises 429 when limit exceeded."""
    from app.common.rate_limit import rate_limit_shared_queries

    mock_request = MagicMock()
    mock_request.client.host = "192.168.1.1"

    # Mock Redis returning count >= 5 (at limit)
    mock_pipe = MagicMock()
    mock_pipe.zremrangebyscore.return_value = mock_pipe
    mock_pipe.zcard.return_value = mock_pipe
    mock_pipe.zadd.return_value = mock_pipe
    mock_pipe.expire.return_value = mock_pipe
    mock_pipe.execute = AsyncMock(return_value=[None, 5, None, None])

    mock_redis = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe

    with patch("app.common.rate_limit.get_redis", return_value=mock_redis):
        with pytest.raises(Exception) as exc_info:
            await rate_limit_shared_queries(mock_request)

    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers


@pytest.mark.asyncio
async def test_rate_limit_shared_queries_allows_under_limit():
    """rate_limit_shared_queries allows requests under the limit."""
    from app.common.rate_limit import rate_limit_shared_queries

    mock_request = MagicMock()
    mock_request.client.host = "192.168.1.1"

    mock_pipe = MagicMock()
    mock_pipe.zremrangebyscore.return_value = mock_pipe
    mock_pipe.zcard.return_value = mock_pipe
    mock_pipe.zadd.return_value = mock_pipe
    mock_pipe.expire.return_value = mock_pipe
    mock_pipe.execute = AsyncMock(return_value=[None, 2, None, None])

    mock_redis = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe

    with patch("app.common.rate_limit.get_redis", return_value=mock_redis):
        # Should not raise
        await rate_limit_shared_queries(mock_request)


@pytest.mark.asyncio
async def test_rate_limit_shared_queries_fails_open():
    """rate_limit_shared_queries allows request when Redis is down."""
    from app.common.rate_limit import rate_limit_shared_queries

    mock_request = MagicMock()
    mock_request.client.host = "192.168.1.1"

    with patch("app.common.rate_limit.get_redis", side_effect=ConnectionError("Redis down")):
        # Should not raise — fails open
        await rate_limit_shared_queries(mock_request)


# ---------------------------------------------------------------------------
# Tests: Service — load_shared_messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_load_messages_with_rich_jsonb():
    """load_shared_messages parses all JSONB fields correctly."""
    from app.shared.service import SharedChatService

    mock_db = AsyncMock()
    result = MagicMock()
    now = datetime.now(UTC)
    result.mappings.return_value.all.return_value = [
        {
            "role": "user",
            "content": "Who was involved?",
            "source_documents": None,
            "entities_mentioned": None,
            "follow_up_questions": None,
            "cited_claims": None,
            "tool_calls": None,
            "created_at": now,
        },
        {
            "role": "assistant",
            "content": "Several people were mentioned.",
            "source_documents": json.dumps(
                [
                    {
                        "id": "c1",
                        "doc_id": "d1",
                        "filename": "test.pdf",
                        "page": 1,
                        "chunk_text": "excerpt",
                        "relevance_score": 0.9,
                    }
                ]
            ),
            "entities_mentioned": json.dumps([{"name": "Jane", "type": "person"}]),
            "follow_up_questions": json.dumps(["What dates?", "Where?"]),
            "cited_claims": json.dumps([{"claim_text": "Jane was present", "source_id": "c1"}]),
            "tool_calls": json.dumps([{"tool": "vector_search", "input": {"q": "test"}}]),
            "created_at": now,
        },
    ]
    mock_db.execute = AsyncMock(return_value=result)

    messages = await SharedChatService.load_shared_messages(mock_db, "thread-1")

    assert len(messages) == 2

    # User message — null JSONB fields become empty lists
    assert messages[0]["source_documents"] == []
    assert messages[0]["entities_mentioned"] == []
    assert messages[0]["timestamp"] == now.isoformat()

    # Assistant message — JSONB parsed
    assert len(messages[1]["source_documents"]) == 1
    assert messages[1]["source_documents"][0]["filename"] == "test.pdf"
    assert len(messages[1]["entities_mentioned"]) == 1
    assert messages[1]["entities_mentioned"][0]["name"] == "Jane"
    assert len(messages[1]["follow_up_questions"]) == 2
    assert len(messages[1]["cited_claims"]) == 1
    assert len(messages[1]["tool_calls"]) == 1


@pytest.mark.asyncio
async def test_service_load_messages_empty_thread():
    """load_shared_messages returns empty list for thread with no messages."""
    from app.shared.service import SharedChatService

    mock_db = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=result)

    messages = await SharedChatService.load_shared_messages(mock_db, "empty-thread")
    assert messages == []


# ---------------------------------------------------------------------------
# Tests: Service — create_share with expiry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_create_share_with_expiry():
    """create_share sets expires_at when expires_in_days is provided."""
    from app.shared.service import SharedChatService

    mock_db = AsyncMock()

    count_result = MagicMock()
    count_result.scalar.return_value = 3

    existing_result = MagicMock()
    existing_result.mappings.return_value.first.return_value = None

    mock_db.execute = AsyncMock(side_effect=[count_result, existing_result, AsyncMock()])

    result = await SharedChatService.create_share(
        db=mock_db,
        thread_id=_TEST_THREAD_ID,
        matter_id=_TEST_MATTER_ID,
        user_id=_TEST_USER.id,
        expires_in_days=7,
    )

    assert result["expires_at"] is not None
    # Should be approximately 7 days from now (within a few seconds of 7*86400)
    delta = result["expires_at"] - datetime.now(UTC)
    assert delta.total_seconds() > 6.99 * 86400


# ---------------------------------------------------------------------------
# Tests: Service — get_share_by_token valid share
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_get_share_valid():
    """get_share_by_token returns share dict and increments view_count."""
    from app.shared.service import SharedChatService

    mock_db = AsyncMock()
    share_id = uuid4()

    result = MagicMock()
    result.mappings.return_value.first.return_value = {
        "id": share_id,
        "thread_id": UUID(_TEST_THREAD_ID),
        "matter_id": _TEST_MATTER_ID,
        "share_token": "valid-token",
        "created_by": _TEST_USER.id,
        "created_at": datetime.now(UTC),
        "expires_at": None,
        "is_revoked": False,
        "view_count": 3,
        "allow_follow_ups": True,
    }

    # First call returns the row, second call is the view_count update
    mock_db.execute = AsyncMock(side_effect=[result, MagicMock()])

    share = await SharedChatService.get_share_by_token(mock_db, "valid-token")

    assert share is not None
    assert share["share_token"] == "valid-token"
    assert share["view_count"] == 3

    # Verify view_count UPDATE was executed
    assert mock_db.execute.call_count == 2
    assert mock_db.commit.call_count == 1


# ---------------------------------------------------------------------------
# Tests: OG page edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_og_page_html_escapes_special_chars(shared_client: AsyncClient):
    """OG page HTML-escapes special characters in messages."""
    share = _fake_share_record()
    messages = [
        {
            "role": "user",
            "content": 'What about <script>alert("xss")</script>?',
            "source_documents": [],
            "entities_mentioned": [],
            "follow_up_questions": [],
            "cited_claims": [],
            "tool_calls": [],
            "timestamp": datetime.now(UTC).isoformat(),
        },
        {
            "role": "assistant",
            "content": 'The documents show O\'Brien & Associates "quoted" content.',
            "source_documents": [],
            "entities_mentioned": [],
            "follow_up_questions": [],
            "cited_claims": [],
            "tool_calls": [],
            "timestamp": datetime.now(UTC).isoformat(),
        },
    ]

    with (
        patch("app.shared.router.SharedChatService.get_share_by_token", new_callable=AsyncMock, return_value=share),
        patch(
            "app.shared.router.SharedChatService.load_shared_messages", new_callable=AsyncMock, return_value=messages
        ),
    ):
        resp = await shared_client.get("/api/v1/shared/test-token-abc123/og")

    assert resp.status_code == 200
    html = resp.text
    # Script tags should be escaped
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    # Quotes/ampersands escaped
    assert "&amp;" in html
