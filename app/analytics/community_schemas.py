"""Pydantic schemas for GraphRAG community detection (T3-10)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class Community(BaseModel):
    """A detected entity community from Louvain clustering."""

    id: str
    matter_id: UUID
    level: int = 0  # 0 = leaf, 1 = parent
    parent_id: str | None = None
    entity_names: list[str] = Field(default_factory=list)
    relationship_types: list[str] = Field(default_factory=list)
    summary: str | None = None
    entity_count: int = 0


class HierarchicalCommunity(Community):
    """A community with its child communities."""

    children: list[Community] = Field(default_factory=list)


class CommunityListResponse(BaseModel):
    """Paginated list of communities for a matter."""

    communities: list[Community]
    total: int
    matter_id: UUID


class CommunitySummaryResponse(BaseModel):
    """A single community with related communities."""

    community: Community
    related_communities: list[Community] = Field(default_factory=list)
