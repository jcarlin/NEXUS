"""Pydantic schemas for shareable chat links."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.query.schemas import ChatMessage


class CreateShareRequest(BaseModel):
    """Request to create a shareable link for a chat thread."""

    allow_follow_ups: bool = Field(default=True, description="Allow viewers to ask follow-up questions.")
    expires_in_days: int | None = Field(default=None, ge=1, le=90, description="Days until link expires (null = never).")


class CreateShareResponse(BaseModel):
    """Response after creating a shareable link."""

    share_token: str
    share_url: str
    expires_at: datetime | None = None


class RevokeShareResponse(BaseModel):
    """Response after revoking a shareable link."""

    detail: str


class SharedChatResponse(BaseModel):
    """Public-facing shared chat conversation."""

    thread_id: UUID
    messages: list[ChatMessage]
    allow_follow_ups: bool
    created_at: datetime
    expires_at: datetime | None = None
    first_query: str = ""
    first_response_preview: str = ""


class SharedQueryRequest(BaseModel):
    """Simplified query request for shared chat follow-ups (no auth, no filters)."""

    query: str = Field(..., min_length=1, max_length=4000, description="Follow-up question.")
