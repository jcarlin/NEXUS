"""Business logic for shareable chat links."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db_utils import parse_jsonb

logger = structlog.get_logger(__name__)


class SharedChatService:
    """Static methods for shared chat link CRUD."""

    @staticmethod
    async def create_share(
        db: AsyncSession,
        thread_id: str,
        matter_id: UUID,
        user_id: UUID,
        allow_follow_ups: bool = True,
        expires_in_days: int | None = None,
    ) -> dict:
        """Create a shareable link for a chat thread.

        Returns dict with share_token, expires_at.
        """
        # Check thread has messages
        result = await db.execute(
            text("SELECT COUNT(*) FROM chat_messages WHERE thread_id = :tid AND matter_id = :mid"),
            {"tid": thread_id, "mid": str(matter_id)},
        )
        count = result.scalar()
        if not count:
            raise ValueError("Thread not found or has no messages")

        # Check if an active share already exists for this thread
        result = await db.execute(
            text("""
                SELECT share_token, expires_at FROM shared_chats
                WHERE thread_id = :tid AND NOT is_revoked
                AND (expires_at IS NULL OR expires_at > now())
                LIMIT 1
            """),
            {"tid": thread_id},
        )
        existing = result.mappings().first()
        if existing:
            return {
                "share_token": existing["share_token"],
                "expires_at": existing["expires_at"],
            }

        share_token = secrets.token_urlsafe(16)
        expires_at = None
        if expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        await db.execute(
            text("""
                INSERT INTO shared_chats (thread_id, matter_id, share_token, created_by, expires_at, allow_follow_ups)
                VALUES (:thread_id, :matter_id, :share_token, :created_by, :expires_at, :allow_follow_ups)
            """),
            {
                "thread_id": thread_id,
                "matter_id": str(matter_id),
                "share_token": share_token,
                "created_by": str(user_id),
                "expires_at": expires_at,
                "allow_follow_ups": allow_follow_ups,
            },
        )
        await db.commit()

        logger.info(
            "shared_chat.created",
            thread_id=thread_id,
            share_token=share_token[:8] + "...",
            user_id=str(user_id),
        )

        return {"share_token": share_token, "expires_at": expires_at}

    @staticmethod
    async def get_share_by_token(db: AsyncSession, share_token: str) -> dict | None:
        """Look up a shared chat by token. Returns None if not found/expired/revoked."""
        result = await db.execute(
            text("""
                SELECT id, thread_id, matter_id, share_token, created_by,
                       created_at, expires_at, is_revoked, view_count, allow_follow_ups
                FROM shared_chats
                WHERE share_token = :token
            """),
            {"token": share_token},
        )
        row = result.mappings().first()
        if not row:
            return None

        if row["is_revoked"]:
            return None

        if row["expires_at"] and row["expires_at"] < datetime.now(timezone.utc):
            return None

        # Increment view count
        await db.execute(
            text("UPDATE shared_chats SET view_count = view_count + 1 WHERE id = :id"),
            {"id": str(row["id"])},
        )
        await db.commit()

        return dict(row)

    @staticmethod
    async def load_shared_messages(db: AsyncSession, thread_id: str) -> list[dict]:
        """Load all messages for a shared thread."""
        result = await db.execute(
            text("""
                SELECT role, content, source_documents, entities_mentioned,
                       follow_up_questions, cited_claims, tool_calls, created_at
                FROM chat_messages
                WHERE thread_id = :tid
                ORDER BY created_at ASC
            """),
            {"tid": thread_id},
        )
        rows = result.mappings().all()

        messages = []
        for r in rows:
            messages.append({
                "role": r["role"],
                "content": r["content"] or "",
                "source_documents": parse_jsonb(r.get("source_documents")),
                "entities_mentioned": parse_jsonb(r.get("entities_mentioned")),
                "follow_up_questions": parse_jsonb(r.get("follow_up_questions")),
                "cited_claims": parse_jsonb(r.get("cited_claims")),
                "tool_calls": parse_jsonb(r.get("tool_calls")),
                "timestamp": r["created_at"].isoformat() if r["created_at"] else None,
            })
        return messages

    @staticmethod
    async def revoke_share(db: AsyncSession, thread_id: str, user_id: UUID) -> bool:
        """Revoke all active shares for a thread. Returns True if any were revoked."""
        result = await db.execute(
            text("""
                UPDATE shared_chats SET is_revoked = true
                WHERE thread_id = :tid AND created_by = :uid AND NOT is_revoked
            """),
            {"tid": thread_id, "uid": str(user_id)},
        )
        await db.commit()
        revoked = result.rowcount > 0

        if revoked:
            logger.info("shared_chat.revoked", thread_id=thread_id, user_id=str(user_id))

        return revoked
