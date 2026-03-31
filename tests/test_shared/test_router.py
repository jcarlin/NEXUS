"""Tests for the shareable chat links router endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
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
        "created_at": datetime.now(timezone.utc),
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
    future_date = datetime.now(timezone.utc) + timedelta(days=7)
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
    assert 'og:title' in html
    assert 'og:description' in html
    assert 'og:site_name' in html
    assert 'NEXUS' in html
    assert 'twitter:card' in html
    assert 'QAPage' in html  # JSON-LD
    assert 'robots' in html
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
        "created_at": datetime.now(timezone.utc) - timedelta(days=10),
        "expires_at": datetime.now(timezone.utc) - timedelta(days=3),
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
        "created_at": datetime.now(timezone.utc),
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
    from app.shared.schemas import CreateShareRequest
    from pydantic import ValidationError

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
    from app.shared.schemas import SharedQueryRequest
    from pydantic import ValidationError

    # Valid
    req = SharedQueryRequest(query="What happened next?")
    assert req.query == "What happened next?"

    # Empty
    with pytest.raises(ValidationError):
        SharedQueryRequest(query="")
