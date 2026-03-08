"""Unit tests for the Google Drive service layer."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.gdrive.crypto import decrypt_tokens, encrypt_tokens, generate_key

# ---------------------------------------------------------------------------
# Crypto tests
# ---------------------------------------------------------------------------


class TestCrypto:
    def test_generate_key_is_valid_fernet_key(self):
        key = generate_key()
        assert isinstance(key, str)
        assert len(key) == 44  # Fernet keys are 44 chars base64

    def test_encrypt_decrypt_roundtrip(self):
        key = generate_key()
        plaintext = json.dumps({"token": "abc123", "refresh_token": "xyz"})
        encrypted = encrypt_tokens(plaintext, key)
        assert encrypted != plaintext
        decrypted = decrypt_tokens(encrypted, key)
        assert decrypted == plaintext

    def test_decrypt_with_wrong_key_fails(self):
        key1 = generate_key()
        key2 = generate_key()
        encrypted = encrypt_tokens("secret", key1)
        from cryptography.fernet import InvalidToken

        with pytest.raises(InvalidToken):
            decrypt_tokens(encrypted, key2)


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def gdrive_settings():
    """Minimal settings for GDriveService."""
    from app.config import Settings

    key = generate_key()
    return Settings(
        enable_google_drive=True,
        gdrive_client_id="test-client-id",
        gdrive_client_secret="test-client-secret",
        gdrive_redirect_uri="http://localhost:5173/gdrive/callback",
        gdrive_encryption_key=key,
        anthropic_api_key="test",
        openai_api_key="test",
    )


@pytest.fixture()
def gdrive_service(gdrive_settings):
    from app.gdrive.service import GDriveService

    return GDriveService(gdrive_settings)


class TestGDriveService:
    def test_build_auth_url(self, gdrive_service):
        """Auth URL should contain the Google accounts endpoint."""
        url = gdrive_service.build_auth_url(state="test-state")
        assert "accounts.google.com" in url
        assert "test-state" in url
        assert "drive.readonly" in url

    @patch("app.gdrive.service.build")
    def test_list_files(self, mock_build, gdrive_service):
        """list_files should call the Drive API and return structured results."""
        mock_drive = MagicMock()
        mock_build.return_value = mock_drive

        mock_drive.files().list().execute.return_value = {
            "files": [
                {"id": "f1", "name": "doc.pdf", "mimeType": "application/pdf", "size": "1024"},
                {"id": "f2", "name": "Folder", "mimeType": "application/vnd.google-apps.folder"},
            ],
            "nextPageToken": "token123",
        }

        tokens = json.dumps({"token": "access", "refresh_token": "refresh"})
        result = gdrive_service.list_files(tokens, "root", page_size=50)

        assert len(result["files"]) == 2
        assert result["files"][0]["id"] == "f1"
        assert result["files"][0]["is_folder"] is False
        assert result["files"][1]["is_folder"] is True
        assert result["next_page_token"] == "token123"

    @patch("app.gdrive.service.build")
    @patch("app.gdrive.service.MediaIoBaseDownload")
    def test_download_regular_file(self, mock_download_cls, mock_build, gdrive_service):
        """Regular files should be downloaded with get_media."""
        mock_drive = MagicMock()
        mock_build.return_value = mock_drive

        # Mock the downloader
        mock_downloader = MagicMock()
        mock_downloader.next_chunk.return_value = (None, True)
        mock_download_cls.return_value = mock_downloader

        tokens = json.dumps({"token": "access", "refresh_token": "refresh"})
        data, suffix = gdrive_service.download_file(tokens, "file123", "application/pdf")

        assert suffix == ""  # Not a Google-native format
        mock_drive.files().get_media.assert_called_once_with(fileId="file123")

    @patch("app.gdrive.service.build")
    @patch("app.gdrive.service.MediaIoBaseDownload")
    def test_download_google_doc_exports_as_pdf(self, mock_download_cls, mock_build, gdrive_service):
        """Google Docs should be exported as PDF."""
        mock_drive = MagicMock()
        mock_build.return_value = mock_drive

        mock_downloader = MagicMock()
        mock_downloader.next_chunk.return_value = (None, True)
        mock_download_cls.return_value = mock_downloader

        tokens = json.dumps({"token": "access", "refresh_token": "refresh"})
        data, suffix = gdrive_service.download_file(
            tokens,
            "doc123",
            "application/vnd.google-apps.document",
        )

        assert suffix == ".pdf"
        mock_drive.files().export_media.assert_called_once_with(
            fileId="doc123",
            mimeType="application/pdf",
        )

    @patch("app.gdrive.service.build")
    def test_get_user_email(self, mock_build, gdrive_service):
        mock_drive = MagicMock()
        mock_build.return_value = mock_drive
        mock_drive.about().get().execute.return_value = {
            "user": {"emailAddress": "user@example.com"},
        }

        tokens = json.dumps({"token": "access", "refresh_token": "refresh"})
        email = gdrive_service.get_user_email(tokens)
        assert email == "user@example.com"


# ---------------------------------------------------------------------------
# DB operations (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGDriveServiceDB:
    async def test_store_connection(self, gdrive_service, gdrive_settings):
        """store_connection should encrypt tokens and insert a row."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.first.return_value = MagicMock(id=uuid4())
        db.execute.return_value = mock_result

        connection_id = await gdrive_service.store_connection(
            db,
            user_id=uuid4(),
            matter_id=uuid4(),
            tokens={"token": "abc", "refresh_token": "xyz"},
            email="user@example.com",
        )
        assert connection_id is not None
        db.execute.assert_called_once()

        # Verify the encrypted_tokens param is not plaintext
        call_args = db.execute.call_args
        params = call_args[1] if call_args[1] else call_args[0][1]
        encrypted = params["encrypted_tokens"]
        assert "abc" not in encrypted  # Token should be encrypted

    async def test_get_connections(self, gdrive_service):
        db = AsyncMock()
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": uuid4(),
            "connection_type": "oauth",
            "email": "user@example.com",
            "is_active": True,
            "scopes": "drive.readonly",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        db.execute.return_value = mock_result

        connections = await gdrive_service.get_connections(db, uuid4(), uuid4())
        assert len(connections) == 1
        assert connections[0]["email"] == "user@example.com"

    async def test_delete_connection(self, gdrive_service):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        db.execute.return_value = mock_result

        deleted = await gdrive_service.delete_connection(db, uuid4(), uuid4())
        assert deleted is True

    async def test_delete_connection_not_found(self, gdrive_service):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        db.execute.return_value = mock_result

        deleted = await gdrive_service.delete_connection(db, uuid4(), uuid4())
        assert deleted is False
