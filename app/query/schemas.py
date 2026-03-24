"""Pydantic schemas for the query / chat domain."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class RetrievalOverrides(BaseModel):
    """Per-request overrides for retrieval strategy flags.

    Each field corresponds to one ``ENABLE_*`` flag on Settings.
    ``None`` means "use the global default".  ``True``/``False`` overrides
    the global setting for this request only.
    """

    enable_hyde: bool | None = None
    enable_multi_query_expansion: bool | None = None
    enable_retrieval_grading: bool | None = None
    enable_citation_verification: bool | None = None
    enable_self_reflection: bool | None = None
    enable_text_to_cypher: bool | None = None
    enable_text_to_sql: bool | None = None
    enable_question_decomposition: bool | None = None
    enable_prompt_routing: bool | None = None
    enable_adaptive_retrieval_depth: bool | None = None
    enable_reranker: bool | None = None
    enable_sparse_embeddings: bool | None = None
    enable_visual_embeddings: bool | None = None


class OverrideFlagCategory(StrEnum):
    """Override flag categories."""

    LOGIC = "logic"
    DI_GATED = "di_gated"


class OverrideFlagDetail(BaseModel):
    """Metadata for a single overridable flag (returned by retrieval-options endpoint)."""

    flag_name: str
    display_name: str
    description: str
    category: OverrideFlagCategory
    global_enabled: bool
    can_enable: bool
    can_disable: bool


class AvailableOverridesResponse(BaseModel):
    """Response for GET /query/retrieval-options."""

    flags: list[OverrideFlagDetail]


class QueryRequest(BaseModel):
    """Payload for POST /query and POST /query/stream."""

    query: str = Field(..., min_length=1, max_length=4000, description="The user's natural-language question.")
    thread_id: UUID | None = Field(default=None, description="Existing conversation thread to continue.")
    filters: dict | None = Field(
        default=None, description="Optional metadata filters (document_type, date_range, etc.)."
    )
    dataset_id: UUID | None = Field(default=None, description="Scope query to documents in this dataset.")
    retrieval_overrides: RetrievalOverrides | None = Field(
        default=None,
        description="Per-chat overrides for retrieval strategy flags. Omit or set fields to null for global defaults.",
    )


class SourceDocument(BaseModel):
    """A single source passage retrieved as evidence for the answer."""

    id: str
    doc_id: str | None = None
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


class EntityGrounding(BaseModel):
    """Result of HalluGraph entity-graph alignment check (T3-9)."""

    name: str
    type: str
    grounded: bool
    confidence: float = Field(ge=0.0, le=1.0)
    closest_match: str | None = None


class QueryResponse(BaseModel):
    """Full (non-streaming) response to a user query."""

    response: str
    source_documents: list[SourceDocument] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    entities_mentioned: list[EntityMention] = Field(default_factory=list)
    thread_id: UUID
    message_id: UUID
    cited_claims: list["CitedClaim"] = Field(default_factory=list)
    tier: str | None = None
    entity_grounding: list[EntityGrounding] = Field(default_factory=list)


class ToolCallEntry(BaseModel):
    """A single tool invocation or pipeline step logged during agent investigation."""

    tool: str
    label: str
    kind: str = "tool"  # "tool" for agent tool calls, "step" for pipeline nodes


class ChatMessage(BaseModel):
    """A single message in a conversation thread."""

    role: str = Field(..., description="'user' or 'assistant'")
    content: str
    source_documents: list[SourceDocument] = Field(default_factory=list)
    entities_mentioned: list[EntityMention] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    cited_claims: list["CitedClaim"] = Field(default_factory=list)
    tool_calls: list[ToolCallEntry] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatThread(BaseModel):
    """Summary of a conversation thread for listing."""

    thread_id: UUID
    message_count: int
    last_message_at: datetime
    first_query: str


class CitedClaim(BaseModel):
    """A factual assertion with source provenance."""

    claim_text: str
    document_id: str
    filename: str | None = None
    page_number: int | None = None
    bates_range: str | None = None
    excerpt: str = Field(max_length=500)
    grounding_score: float = Field(ge=0.0, le=1.0)
    verification_status: str = "unverified"  # unverified | verified | flagged


class VerificationJudgment(BaseModel):
    """Instructor extraction model for CoVe claim verification."""

    claim_index: int
    supported: bool
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class ChatHistoryResponse(BaseModel):
    """Full message history for a conversation thread."""

    thread_id: UUID
    messages: list[ChatMessage]


class ClarificationResponse(BaseModel):
    """User's answer to an agent clarification question."""

    thread_id: UUID
    answer: str = Field(..., min_length=1, max_length=4000)
