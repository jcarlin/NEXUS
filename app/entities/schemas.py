"""Pydantic schemas for the entities / knowledge-graph domain."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.common.models import PaginatedResponse


class EntityResponse(BaseModel):
    """Full view of a knowledge-graph entity."""

    id: UUID
    name: str
    type: str
    aliases: list[str] = Field(default_factory=list)
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    description: str | None = None
    mention_count: int = 0


class EntityConnection(BaseModel):
    """A single edge between two entities in the graph."""

    source: str
    target: str
    relationship_type: str
    context: str | None = None
    weight: float = 1.0


class GraphStatsResponse(BaseModel):
    """Aggregate statistics for the knowledge graph."""

    node_count: int = 0
    edge_count: int = 0
    entity_types: dict[str, int] = Field(default_factory=dict)


class TimelineEvent(BaseModel):
    """A chronologically-ordered event associated with an entity."""

    date: datetime | None = None
    description: str
    entities: list[str] = Field(default_factory=list)
    document_source: str | None = None


class EntityListResponse(PaginatedResponse[EntityResponse]):
    """Paginated list of entities."""


class CommunicationPairRecord(BaseModel):
    email_id: str
    subject: str | None = None
    date: str | None = None
    message_id: str | None = None


class CommunicationPairsResponse(BaseModel):
    person_a: str
    person_b: str
    emails: list[CommunicationPairRecord] = Field(default_factory=list)
    total: int = 0


class ReportingChainResponse(BaseModel):
    person: str
    chains: list[dict] = Field(default_factory=list)


class PathResponse(BaseModel):
    entity_a: str
    entity_b: str
    paths: list[dict] = Field(default_factory=list)
