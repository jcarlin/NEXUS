"""LangGraph tool wrappers for the agentic investigation pipeline.

Each tool is a thin ``@tool``-decorated async function that wraps an existing
service.  Security-scoped fields (``matter_id``, privilege filters) are
injected from graph state via ``InjectedState`` so the LLM never sees them.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

import structlog
from langchain_core.tools import tool
from langgraph.prebuilt.tool_node import InjectedState

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Real tools (wrapping existing services)
# ---------------------------------------------------------------------------


@tool
async def vector_search(
    query: str,
    limit: int = 20,
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Search legal documents by semantic similarity.

    Use for content questions, finding mentions of specific topics, locating
    evidence about events, agreements, or communications.
    """
    from app.dependencies import get_retriever

    retriever = get_retriever()
    results = await retriever.retrieve_text(
        query,
        limit=limit,
        filters=state.get("_filters"),
        exclude_privilege_statuses=state.get("_exclude_privilege") or None,
    )
    # Return structured results for the agent to reason over
    formatted = [
        {
            "id": r.get("id", ""),
            "filename": r.get("source_file", "unknown"),
            "page": r.get("page_number"),
            "text": r.get("chunk_text", "")[:500],
            "score": round(r.get("score", 0), 4),
        }
        for r in results[:limit]
    ]
    return json.dumps(formatted, default=str)


@tool
async def graph_query(
    entity_name: str,
    limit: int = 20,
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Query the knowledge graph for entity relationships and connections.

    Use for questions like "Who communicated with X?", "What entities are
    connected to Y?", or "Show relationships for Z".
    """
    from app.dependencies import get_graph_service

    gs = get_graph_service()
    connections = await gs.get_entity_connections(
        entity_name,
        limit=limit,
        exclude_privilege_statuses=state.get("_exclude_privilege") or None,
    )
    return json.dumps(connections, default=str)


@tool
async def temporal_search(
    query: str,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Search documents within a specific date range.

    Use for queries like "Between January and March 2020..." or
    "What happened before the agreement was signed?".
    Provide date_from and/or date_to in YYYY-MM-DD format.
    """
    from app.dependencies import get_retriever

    retriever = get_retriever()
    filters: dict[str, Any] = dict(state.get("_filters") or {})
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to

    results = await retriever.retrieve_text(
        query,
        limit=limit,
        filters=filters,
        exclude_privilege_statuses=state.get("_exclude_privilege") or None,
    )
    formatted = [
        {
            "id": r.get("id", ""),
            "filename": r.get("source_file", "unknown"),
            "page": r.get("page_number"),
            "text": r.get("chunk_text", "")[:500],
            "score": round(r.get("score", 0), 4),
        }
        for r in results[:limit]
    ]
    return json.dumps(formatted, default=str)


@tool
async def entity_lookup(
    name: str,
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Look up a specific entity by name, with alias resolution.

    Use for "Who is Defendant A?", "What is the Agreement?", or
    any question about a specific person, organization, or defined term.
    Resolves aliases from the case context term map.
    """
    from app.dependencies import get_graph_service

    gs = get_graph_service()

    # Try alias resolution from case context term map
    term_map: dict[str, str] = state.get("_term_map", {})
    resolved_name = term_map.get(name.lower(), name)

    entity = await gs.get_entity_by_name(resolved_name)
    if entity is None and resolved_name != name:
        # Fallback to original name
        entity = await gs.get_entity_by_name(name)

    if entity is None:
        return json.dumps({"error": f"Entity '{name}' not found in knowledge graph."})

    # Also fetch connections
    connections = await gs.get_entity_connections(
        entity["name"],
        limit=10,
        exclude_privilege_statuses=state.get("_exclude_privilege") or None,
    )
    entity["connections"] = connections
    return json.dumps(entity, default=str)


@tool
async def document_retrieval(
    document_id: str,
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Retrieve full metadata and content chunks for a specific document.

    Use for "Summarize document X", "What does Exhibit A say?", or when
    you need the full content of a known document.
    """
    from app.dependencies import get_retriever

    retriever = get_retriever()
    # Search with document_id filter to get all chunks for this doc
    filters: dict[str, Any] = dict(state.get("_filters") or {})
    filters["document_id"] = document_id

    results = await retriever.retrieve_text(
        "",  # Empty query to get all chunks by filter
        limit=50,
        filters=filters,
        exclude_privilege_statuses=state.get("_exclude_privilege") or None,
    )
    formatted = [
        {
            "id": r.get("id", ""),
            "filename": r.get("source_file", "unknown"),
            "page": r.get("page_number"),
            "text": r.get("chunk_text", "")[:500],
        }
        for r in results
    ]
    return json.dumps(formatted, default=str)


@tool
async def case_context(
    aspect: str = "all",
    state: Annotated[dict, InjectedState] = {},  # noqa: B006
) -> str:
    """Retrieve case-level context: claims, parties, defined terms, timeline.

    Use for "What are the claims?", "Who are the parties?", "What are the
    key dates?". Set aspect to 'claims', 'parties', 'terms', 'timeline',
    or 'all' for everything.
    """
    from app.cases.service import CaseService
    from app.dependencies import get_db

    filters = state.get("_filters", {})
    matter_id = filters.get("matter_id", "")

    # Get a fresh DB session for the lookup
    db_gen = get_db()
    db = await db_gen.__anext__()
    try:
        ctx = await CaseService.get_full_context(db, matter_id)
        if ctx is None:
            return json.dumps({"info": "No case context configured for this matter."})

        if aspect == "claims":
            return json.dumps(ctx.get("claims", []), default=str)
        elif aspect == "parties":
            return json.dumps(ctx.get("parties", []), default=str)
        elif aspect == "terms":
            return json.dumps(ctx.get("defined_terms", []), default=str)
        elif aspect == "timeline":
            return json.dumps(ctx.get("timeline", []), default=str)
        else:
            return json.dumps(
                {
                    "claims": ctx.get("claims", []),
                    "parties": ctx.get("parties", []),
                    "defined_terms": ctx.get("defined_terms", []),
                    "timeline": ctx.get("timeline", []),
                },
                default=str,
            )
    finally:
        try:
            await db_gen.aclose()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Stub tools (feature-flagged for M10b/M10c)
# ---------------------------------------------------------------------------


@tool
async def sentiment_search(query: str) -> str:
    """Search for documents by sentiment or emotional tone. (Coming soon)"""
    return "This capability is not yet available. Use vector_search or graph_query instead."


@tool
async def communication_matrix(entity_name: str) -> str:
    """Analyze communication patterns between entities. (Coming soon)"""
    return "This capability is not yet available. Use graph_query instead."


@tool
async def topic_cluster(query: str) -> str:
    """Find topic clusters across the document corpus. (Coming soon)"""
    return "This capability is not yet available. Use vector_search instead."


@tool
async def sql_aggregation(query: str) -> str:
    """Run aggregate queries over document metadata. (Coming soon)"""
    return "This capability is not yet available. Use vector_search or case_context instead."


# ---------------------------------------------------------------------------
# Tool lists
# ---------------------------------------------------------------------------

INVESTIGATION_TOOLS = [
    vector_search,
    graph_query,
    temporal_search,
    entity_lookup,
    document_retrieval,
    case_context,
    # Stubs
    sentiment_search,
    communication_matrix,
    topic_cluster,
    sql_aggregation,
]
