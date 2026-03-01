"""Pydantic schemas for communication analytics (M10c)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class CentralityMetric(StrEnum):
    """Supported Neo4j GDS centrality algorithms."""

    DEGREE = "degree"
    PAGERANK = "pagerank"
    BETWEENNESS = "betweenness"


# ---------------------------------------------------------------------------
# Communication matrix
# ---------------------------------------------------------------------------


class CommunicationPair(BaseModel):
    """A sender-recipient pair with message count and date range."""

    sender_name: str
    sender_email: str | None = None
    recipient_name: str
    recipient_email: str | None = None
    relationship_type: str = "to"
    message_count: int = 0
    earliest: datetime | None = None
    latest: datetime | None = None


class CommunicationMatrixResponse(BaseModel):
    """Full communication matrix for a matter."""

    matter_id: UUID
    pairs: list[CommunicationPair] = Field(default_factory=list)
    total_messages: int = 0
    unique_senders: int = 0
    unique_recipients: int = 0


# ---------------------------------------------------------------------------
# Network centrality
# ---------------------------------------------------------------------------


class EntityCentrality(BaseModel):
    """An entity with its centrality score and rank."""

    name: str
    entity_type: str | None = None
    score: float
    rank: int


class NetworkCentralityResponse(BaseModel):
    """Ranked entity centrality for a matter."""

    matter_id: UUID
    metric: CentralityMetric
    entities: list[EntityCentrality] = Field(default_factory=list)
    total_entities: int = 0


# ---------------------------------------------------------------------------
# Org chart
# ---------------------------------------------------------------------------


class OrgChartEntry(BaseModel):
    """A single org chart entry (person + reporting relationship)."""

    person_name: str
    person_email: str | None = None
    reports_to_name: str | None = None
    reports_to_email: str | None = None
    title: str | None = None
    department: str | None = None
    source: str = "manual"
    confidence: float | None = None


class OrgChartImportRequest(BaseModel):
    """Request body for org chart import."""

    entries: list[OrgChartEntry] = Field(..., min_length=1)


class OrgChartImportResponse(BaseModel):
    """Response from org chart import."""

    matter_id: UUID
    imported_count: int
    total_entries: int


# ---------------------------------------------------------------------------
# Topic clustering
# ---------------------------------------------------------------------------


class TopicCluster(BaseModel):
    """A single topic cluster from BERTopic."""

    topic_id: int
    label: str
    representative_terms: list[str] = Field(default_factory=list)
    document_count: int = 0


class TopicClusterResponse(BaseModel):
    """Topic clustering results for a matter."""

    matter_id: UUID
    clusters: list[TopicCluster] = Field(default_factory=list)
    total_documents: int = 0
    total_clusters: int = 0
