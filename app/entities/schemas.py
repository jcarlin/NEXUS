"""Pydantic schemas for the entities / knowledge-graph domain."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.common.models import PaginatedResponse


class EntityResponse(BaseModel):
    """Full view of a knowledge-graph entity."""

    id: str
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


class DocumentEntityStatus(BaseModel):
    """Per-document entity/graph status for the KG admin view."""

    doc_id: UUID
    filename: str
    entity_count: int
    neo4j_indexed: bool
    created_at: datetime


class KGStatusResponse(BaseModel):
    """Full knowledge-graph health snapshot."""

    total_nodes: int
    total_edges: int
    node_counts: dict[str, int]
    edge_counts: dict[str, int]
    documents: list[DocumentEntityStatus]
    total_documents: int
    indexed_documents: int


class KGReprocessRequest(BaseModel):
    """Request to reprocess documents into Neo4j."""

    document_ids: list[UUID] | None = None
    all_unprocessed: bool = False


class KGReprocessResponse(BaseModel):
    """Confirmation of reprocess task dispatch."""

    task_id: str
    document_count: int


class KGResolveRequest(BaseModel):
    """Request to run entity resolution."""

    mode: str = "simple"


class KGResolveResponse(BaseModel):
    """Confirmation of resolution task dispatch."""

    task_id: str
    mode: str


# ---------------------------------------------------------------------------
# Interactive graph editing (T3-5)
# ---------------------------------------------------------------------------


class EntityRenameRequest(BaseModel):
    """Rename an entity node in the knowledge graph."""

    new_name: str = Field(..., min_length=1, max_length=500)


class EntityTypeUpdateRequest(BaseModel):
    """Change the type of an entity node."""

    new_type: str = Field(..., min_length=1, max_length=100)


class EntityMergeRequest(BaseModel):
    """Merge two entity nodes (source is absorbed into target)."""

    source_name: str = Field(..., min_length=1)
    target_name: str = Field(..., min_length=1)


class RelationshipCreateRequest(BaseModel):
    """Create a new relationship between two entities."""

    source_name: str = Field(..., min_length=1)
    target_name: str = Field(..., min_length=1)
    relationship_type: str = Field(..., min_length=1)
    properties: dict | None = None


class RelationshipDeleteRequest(BaseModel):
    """Delete a specific relationship between two entities."""

    source_name: str = Field(..., min_length=1)
    target_name: str = Field(..., min_length=1)
    relationship_type: str = Field(..., min_length=1)
