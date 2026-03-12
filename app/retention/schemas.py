"""Retention policy Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class PurgeStatus(StrEnum):
    ACTIVE = "active"
    PENDING_PURGE = "pending_purge"
    ARCHIVING = "archiving"
    PURGING = "purging"
    COMPLETED = "completed"
    FAILED = "failed"


class RetentionPolicyRequest(BaseModel):
    retention_days: int = Field(gt=0)
    matter_id: UUID


class RetentionPolicyResponse(BaseModel):
    id: UUID
    matter_id: UUID
    retention_days: int
    policy_set_by: UUID
    policy_set_at: datetime
    purge_scheduled_at: datetime | None = None
    purge_completed_at: datetime | None = None
    purge_error: str | None = None
    archive_path: str | None = None
    status: str


class RetentionPolicyListResponse(BaseModel):
    policies: list[RetentionPolicyResponse]
    total: int
