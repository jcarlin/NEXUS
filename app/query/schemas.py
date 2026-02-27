"""Pydantic schemas for the query / chat domain."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Payload for POST /query and POST /query/stream."""

    query: str = Field(..., min_length=1, max_length=4000, description="The user's natural-language question.")
    thread_id: UUID | None = Field(default=None, description="Existing conversation thread to continue.")
    filters: dict | None = Field(default=None, description="Optional metadata filters (document_type, date_range, etc.).")


class SourceDocument(BaseModel):
    """A single source passage retrieved as evidence for the answer."""

    id: str
    filename: str
    page: int | None = None
    chunk_text: str
    relevance_score: float
    preview_url: str | None = None
    download_url: str | None = None


class EntityMention(BaseModel):
    """An entity detected in the query response, linked to the knowledge graph."""

    name: str
    type: str
    kg_id: str | None = None
    connections: int = 0


class QueryResponse(BaseModel):
    """Full (non-streaming) response to a user query."""

    response: str
    source_documents: list[SourceDocument] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    entities_mentioned: list[EntityMention] = Field(default_factory=list)
    thread_id: UUID
    message_id: UUID


class ChatMessage(BaseModel):
    """A single message in a conversation thread."""

    role: str = Field(..., description="'user' or 'assistant'")
    content: str
    source_documents: list[SourceDocument] = Field(default_factory=list)
    entities_mentioned: list[EntityMention] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatThread(BaseModel):
    """Summary of a conversation thread for listing."""

    thread_id: UUID
    message_count: int
    last_message_at: datetime
    first_query: str


class ChatHistoryResponse(BaseModel):
    """Full message history for a conversation thread."""

    thread_id: UUID
    messages: list[ChatMessage]
