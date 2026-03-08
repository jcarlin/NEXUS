"""Memo drafting domain schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class MemoFormat(StrEnum):
    MARKDOWN = "markdown"
    HTML = "html"


class MemoSection(BaseModel):
    """A single section of a generated memo."""

    heading: str
    content: str
    citations: list[str] = Field(default_factory=list)  # doc IDs referenced


class MemoRequest(BaseModel):
    """Request to generate a memo from a chat thread or ad-hoc query."""

    thread_id: str | None = None  # Generate from existing chat thread
    query: str | None = None  # Or ad-hoc query text
    matter_id: UUID
    title: str | None = None  # Optional custom title
    format: MemoFormat = MemoFormat.MARKDOWN
    include_source_index: bool = True


class MemoResponse(BaseModel):
    """Generated memo."""

    id: UUID
    matter_id: UUID
    thread_id: str | None = None
    title: str
    sections: list[MemoSection]
    format: MemoFormat
    created_by: UUID
    created_at: datetime


class MemoListResponse(BaseModel):
    """List of memos."""

    items: list[MemoResponse]
    total: int
