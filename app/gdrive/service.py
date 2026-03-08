"""Google Drive service — token management, file listing, and download.

All Google API calls go through this service.  Tokens are decrypted on
demand, and refreshed tokens are re-encrypted and persisted.
"""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any
from uuid import UUID

import structlog
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.gdrive.crypto import decrypt_tokens, encrypt_tokens

logger = structlog.get_logger(__name__)

# Google-native MIME types that need export (→ PDF)
_EXPORT_MIME_MAP: dict[str, str] = {
    "application/vnd.google-apps.document": "application/pdf",
    "application/vnd.google-apps.spreadsheet": "application/pdf",
    "application/vnd.google-apps.presentation": "application/pdf",
    "application/vnd.google-apps.drawing": "application/pdf",
}

_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


class GDriveService:
    """Stateless service for Google Drive operations."""

    def __init__(self, settings: Settings) -> None:
        self._client_id = settings.gdrive_client_id
        self._client_secret = settings.gdrive_client_secret
        self._redirect_uri = settings.gdrive_redirect_uri
        self._encryption_key = settings.gdrive_encryption_key

    # ------------------------------------------------------------------
    # OAuth helpers
    # ------------------------------------------------------------------

    def build_auth_url(self, state: str) -> str:
        """Return the Google OAuth2 authorization URL."""
        flow = self._make_flow()
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )
        return auth_url

    def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange an authorization code for OAuth tokens.

        Returns the raw credentials dict (access_token, refresh_token, etc.).
        """
        flow = self._make_flow()
        flow.fetch_token(code=code)
        creds = flow.credentials
        return {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes or []),
        }

    # ------------------------------------------------------------------
    # Credential management
    # ------------------------------------------------------------------

    def _make_flow(self) -> Flow:
        client_config = {
            "web": {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [self._redirect_uri],
            }
        }
        return Flow.from_client_config(client_config, scopes=_SCOPES, redirect_uri=self._redirect_uri)

    def _creds_from_tokens(self, tokens_json: str) -> Credentials:
        """Build ``Credentials`` from a decrypted tokens JSON string."""
        data = json.loads(tokens_json)
        return Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=data.get("client_id", self._client_id),
            client_secret=data.get("client_secret", self._client_secret),
            scopes=data.get("scopes", _SCOPES),
        )

    def _build_drive(self, creds: Credentials):
        """Build a Google Drive API v3 service object."""
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    # ------------------------------------------------------------------
    # Token persistence
    # ------------------------------------------------------------------

    async def store_connection(
        self,
        db: AsyncSession,
        user_id: UUID,
        matter_id: UUID,
        tokens: dict[str, Any],
        email: str,
        connection_type: str = "oauth",
    ) -> UUID:
        """Encrypt and store OAuth tokens as a new connection row."""
        encrypted = encrypt_tokens(json.dumps(tokens), self._encryption_key)
        scopes = ",".join(tokens.get("scopes", _SCOPES))
        result = await db.execute(
            text(
                """
                INSERT INTO google_drive_connections
                    (user_id, matter_id, connection_type, encrypted_tokens, email, scopes)
                VALUES
                    (:user_id, :matter_id, :connection_type, :encrypted_tokens, :email, :scopes)
                ON CONFLICT (user_id, matter_id, email) DO UPDATE SET
                    encrypted_tokens = EXCLUDED.encrypted_tokens,
                    is_active = true,
                    updated_at = now()
                RETURNING id
                """
            ),
            {
                "user_id": str(user_id),
                "matter_id": str(matter_id),
                "connection_type": connection_type,
                "encrypted_tokens": encrypted,
                "email": email,
                "scopes": scopes,
            },
        )
        row = result.first()
        assert row is not None
        connection_id = row.id
        logger.info("gdrive.connection_stored", connection_id=str(connection_id), email=email)
        return connection_id

    async def get_connections(
        self,
        db: AsyncSession,
        matter_id: UUID,
        user_id: UUID,
    ) -> list[dict[str, Any]]:
        """List active Drive connections for a matter/user."""
        result = await db.execute(
            text(
                """
                SELECT id, connection_type, email, is_active, scopes, created_at, updated_at
                FROM google_drive_connections
                WHERE matter_id = :matter_id AND user_id = :user_id AND is_active = true
                ORDER BY created_at DESC
                """
            ),
            {"matter_id": str(matter_id), "user_id": str(user_id)},
        )
        return [dict(row._mapping) for row in result.fetchall()]

    async def get_connection_tokens(
        self,
        db: AsyncSession,
        connection_id: UUID,
        matter_id: UUID,
    ) -> str:
        """Decrypt and return tokens JSON for a connection.

        Raises ``ValueError`` if the connection is not found or not active.
        """
        result = await db.execute(
            text(
                """
                SELECT encrypted_tokens
                FROM google_drive_connections
                WHERE id = :id AND matter_id = :matter_id AND is_active = true
                """
            ),
            {"id": str(connection_id), "matter_id": str(matter_id)},
        )
        row = result.first()
        if row is None:
            raise ValueError(f"Connection {connection_id} not found or inactive")
        return decrypt_tokens(row.encrypted_tokens, self._encryption_key)

    async def delete_connection(
        self,
        db: AsyncSession,
        connection_id: UUID,
        matter_id: UUID,
    ) -> bool:
        """Soft-delete a connection (set is_active = false)."""
        result = await db.execute(
            text(
                """
                UPDATE google_drive_connections
                SET is_active = false, updated_at = now()
                WHERE id = :id AND matter_id = :matter_id
                """
            ),
            {"id": str(connection_id), "matter_id": str(matter_id)},
        )
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # File listing (Drive API)
    # ------------------------------------------------------------------

    def list_files(
        self,
        tokens_json: str,
        folder_id: str = "root",
        page_token: str | None = None,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """List files in a Drive folder.

        Returns ``{"files": [...], "next_page_token": ... | None}``.
        """
        creds = self._creds_from_tokens(tokens_json)
        drive = self._build_drive(creds)

        query = f"'{folder_id}' in parents and trashed = false"
        fields = "nextPageToken, files(id, name, mimeType, size, modifiedTime)"

        kwargs: dict[str, Any] = {
            "q": query,
            "fields": fields,
            "pageSize": page_size,
            "orderBy": "name",
        }
        if page_token:
            kwargs["pageToken"] = page_token

        resp = drive.files().list(**kwargs).execute()
        files = []
        for f in resp.get("files", []):
            files.append(
                {
                    "id": f["id"],
                    "name": f["name"],
                    "mime_type": f["mimeType"],
                    "size": int(f["size"]) if "size" in f else None,
                    "modified_time": f.get("modifiedTime"),
                    "is_folder": f["mimeType"] == "application/vnd.google-apps.folder",
                }
            )
        return {
            "files": files,
            "next_page_token": resp.get("nextPageToken"),
        }

    def list_files_recursive(
        self,
        tokens_json: str,
        folder_id: str,
    ) -> list[dict[str, Any]]:
        """Recursively list all non-folder files under a Drive folder."""
        all_files: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            result = self.list_files(tokens_json, folder_id, page_token, page_size=1000)
            for f in result["files"]:
                if f["is_folder"]:
                    all_files.extend(self.list_files_recursive(tokens_json, f["id"]))
                else:
                    all_files.append(f)
            page_token = result["next_page_token"]
            if not page_token:
                break

        return all_files

    # ------------------------------------------------------------------
    # File download / export
    # ------------------------------------------------------------------

    def download_file(self, tokens_json: str, file_id: str, mime_type: str) -> tuple[bytes, str]:
        """Download a file from Drive.

        For Google-native formats (Docs/Sheets/Slides), exports as PDF.
        Returns ``(file_bytes, effective_filename_suffix)``.
        """
        creds = self._creds_from_tokens(tokens_json)
        drive = self._build_drive(creds)

        export_mime = _EXPORT_MIME_MAP.get(mime_type)
        if export_mime:
            # Google Docs/Sheets/Slides → export as PDF
            request = drive.files().export_media(fileId=file_id, mimeType=export_mime)
            suffix = ".pdf"
        else:
            request = drive.files().get_media(fileId=file_id)
            suffix = ""

        buf = BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        return buf.getvalue(), suffix

    def get_user_email(self, tokens_json: str) -> str:
        """Get the email address of the authenticated Drive user."""
        creds = self._creds_from_tokens(tokens_json)
        drive = self._build_drive(creds)
        about = drive.about().get(fields="user(emailAddress)").execute()
        return about["user"]["emailAddress"]

    # ------------------------------------------------------------------
    # Sync state management
    # ------------------------------------------------------------------

    async def upsert_sync_state(
        self,
        db: AsyncSession,
        connection_id: UUID,
        matter_id: UUID,
        drive_file_id: str,
        drive_file_name: str,
        drive_modified_time: str | None,
        content_hash: str | None,
        document_id: UUID | None = None,
        sync_status: str = "synced",
    ) -> None:
        """Insert or update a sync state record for a Drive file."""
        await db.execute(
            text(
                """
                INSERT INTO google_drive_sync_state
                    (connection_id, matter_id, drive_file_id, drive_file_name,
                     drive_modified_time, content_hash, document_id, sync_status, last_synced_at)
                VALUES
                    (:connection_id, :matter_id, :drive_file_id, :drive_file_name,
                     :drive_modified_time, :content_hash, :document_id, :sync_status, now())
                ON CONFLICT (connection_id, drive_file_id) DO UPDATE SET
                    drive_file_name = EXCLUDED.drive_file_name,
                    drive_modified_time = EXCLUDED.drive_modified_time,
                    content_hash = EXCLUDED.content_hash,
                    document_id = COALESCE(EXCLUDED.document_id, google_drive_sync_state.document_id),
                    sync_status = EXCLUDED.sync_status,
                    last_synced_at = now()
                """
            ),
            {
                "connection_id": str(connection_id),
                "matter_id": str(matter_id),
                "drive_file_id": drive_file_id,
                "drive_file_name": drive_file_name,
                "drive_modified_time": drive_modified_time,
                "content_hash": content_hash,
                "document_id": str(document_id) if document_id else None,
                "sync_status": sync_status,
            },
        )

    async def get_sync_state(
        self,
        db: AsyncSession,
        connection_id: UUID,
        matter_id: UUID,
    ) -> list[dict[str, Any]]:
        """Get sync state records for a connection."""
        result = await db.execute(
            text(
                """
                SELECT id, drive_file_id, drive_file_name, sync_status,
                       last_synced_at, document_id
                FROM google_drive_sync_state
                WHERE connection_id = :connection_id AND matter_id = :matter_id
                ORDER BY drive_file_name
                """
            ),
            {"connection_id": str(connection_id), "matter_id": str(matter_id)},
        )
        return [dict(row._mapping) for row in result.fetchall()]

    async def get_existing_sync_map(
        self,
        db: AsyncSession,
        connection_id: UUID,
    ) -> dict[str, dict[str, Any]]:
        """Return a map of drive_file_id → sync record for change detection."""
        result = await db.execute(
            text(
                """
                SELECT drive_file_id, drive_modified_time, content_hash, sync_status
                FROM google_drive_sync_state
                WHERE connection_id = :connection_id
                """
            ),
            {"connection_id": str(connection_id)},
        )
        return {row.drive_file_id: dict(row._mapping) for row in result.fetchall()}
