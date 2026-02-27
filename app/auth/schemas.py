"""Auth domain Pydantic schemas: roles, tokens, users, matters, audit."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.common.models import PaginatedResponse


class Role(StrEnum):
    ADMIN = "admin"
    ATTORNEY = "attorney"
    PARALEGAL = "paralegal"
    REVIEWER = "reviewer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    role: Role = Role.REVIEWER


class MatterResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    is_active: bool
    created_at: datetime


class AuditLogEntry(BaseModel):
    """Single row from the audit_log table."""

    id: UUID
    user_id: UUID | None = None
    user_email: str | None = None
    action: str
    resource: str
    resource_type: str | None = None
    matter_id: UUID | None = None
    ip_address: str
    user_agent: str | None = None
    status_code: int
    duration_ms: float | None = None
    request_id: str | None = None
    created_at: datetime


class AuditLogListResponse(PaginatedResponse[AuditLogEntry]):
    """Paginated list of audit log entries."""
