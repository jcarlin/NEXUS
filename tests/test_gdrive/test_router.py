"""API endpoint tests for the Google Drive integration."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.schemas import UserRecord
from app.gdrive.crypto import generate_key

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


@pytest.fixture()
async def gdrive_client():
    """Yield an httpx AsyncClient with the gdrive router mounted."""
    from app import main as main_module
    from app.config import Settings

    async def _noop_lifespan(app):
        yield

    # Create real settings with Google Drive enabled
    test_settings = Settings(
        enable_google_drive=True,
        gdrive_client_id="test-client-id",
        gdrive_client_secret="test-secret",
        gdrive_redirect_uri="http://localhost:5173/gdrive/callback",
        gdrive_encryption_key=generate_key(),
        anthropic_api_key="test",
        openai_api_key="test",
    )

    with (
        patch.object(main_module, "lifespan", _noop_lifespan),
        patch("app.main.get_settings", return_value=test_settings),
        patch("app.gdrive.router.get_settings", return_value=test_settings),
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


@pytest.mark.asyncio
class TestGDriveAuthEndpoints:
    async def test_auth_url_returns_google_url(self, gdrive_client):
        """GET /auth/url should return a Google OAuth URL."""
        mock_service = MagicMock()
        mock_service.build_auth_url.return_value = "https://accounts.google.com/o/oauth2/auth?state=xyz"

        with patch("app.gdrive.router._get_gdrive_service", return_value=mock_service):
            resp = await gdrive_client.get("/api/v1/gdrive/auth/url")

        assert resp.status_code == 200
        data = resp.json()
        assert "auth_url" in data
        assert "accounts.google.com" in data["auth_url"]


@pytest.mark.asyncio
class TestGDriveConnectionEndpoints:
    async def test_list_connections_empty(self, gdrive_client):
        """GET /connections should return empty list when no connections exist."""
        mock_service = MagicMock()
        mock_service.get_connections = AsyncMock(return_value=[])

        with patch("app.gdrive.router._get_gdrive_service", return_value=mock_service):
            resp = await gdrive_client.get("/api/v1/gdrive/connections")

        assert resp.status_code == 200
        data = resp.json()
        assert data["connections"] == []

    async def test_delete_connection_not_found(self, gdrive_client):
        """DELETE /connections/{id} should return 404 for missing connection."""
        mock_service = MagicMock()
        mock_service.delete_connection = AsyncMock(return_value=False)

        with patch("app.gdrive.router._get_gdrive_service", return_value=mock_service):
            resp = await gdrive_client.delete(f"/api/v1/gdrive/connections/{uuid4()}")

        assert resp.status_code == 404


@pytest.mark.asyncio
class TestGDriveBrowseEndpoints:
    async def test_browse_returns_files(self, gdrive_client):
        """GET /browse should list files from Drive."""
        conn_id = uuid4()
        mock_service = MagicMock()
        mock_service.get_connection_tokens = AsyncMock(return_value='{"token":"t"}')
        mock_service.list_files.return_value = {
            "files": [
                {
                    "id": "f1",
                    "name": "test.pdf",
                    "mime_type": "application/pdf",
                    "size": 1024,
                    "modified_time": "2026-01-01T00:00:00Z",
                    "is_folder": False,
                },
            ],
            "next_page_token": None,
        }

        with patch("app.gdrive.router._get_gdrive_service", return_value=mock_service):
            resp = await gdrive_client.get(
                "/api/v1/gdrive/browse",
                params={"connection_id": str(conn_id)},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["files"]) == 1
        assert data["files"][0]["name"] == "test.pdf"


@pytest.mark.asyncio
class TestGDriveIngestEndpoints:
    async def test_ingest_no_files_returns_400(self, gdrive_client):
        """POST /ingest with no files should return 400."""
        conn_id = uuid4()
        mock_service = MagicMock()
        mock_service.get_connection_tokens = AsyncMock(return_value='{"token":"t"}')
        mock_service.list_files_recursive.return_value = []

        with patch("app.gdrive.router._get_gdrive_service", return_value=mock_service):
            resp = await gdrive_client.post(
                "/api/v1/gdrive/ingest",
                json={"connection_id": str(conn_id), "file_ids": [], "folder_ids": []},
            )

        assert resp.status_code == 400
