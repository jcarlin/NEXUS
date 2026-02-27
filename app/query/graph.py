"""LangGraph state graph for the investigation query pipeline.

Defines ``InvestigationState`` (the conversation state schema) and
``build_graph()`` which wires up 8 nodes into a compiled ``StateGraph``.

Edge structure::

    START → classify → rewrite → retrieve → rerank → check_relevance
      check_relevance ──(relevant)──→ graph_lookup
      check_relevance ──(not_relevant, first time)──→ reformulate → retrieve
      check_relevance ──(not_relevant, already reformulated)──→ graph_lookup
    graph_lookup → synthesize → generate_follow_ups → END
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:
    from app.common.llm import LLMClient
    from app.entities.extractor import EntityExtractor
    from app.entities.graph_service import GraphService
    from app.query.retriever import HybridRetriever


def _replace(existing: list, new: list) -> list:
    """Reducer that replaces a list field wholesale (no append semantics)."""
    return new


class InvestigationState(TypedDict, total=False):
    """State schema for the investigation query pipeline.

    Fields marked with ``Annotated[..., _replace]`` use a custom reducer
    so that node outputs *replace* rather than append to the list.
    """

    # Conversation
    messages: list[dict[str, Any]]
    thread_id: str
    user_id: str

    # Current query processing
    original_query: str
    rewritten_query: str
    query_type: str

    # Retrieved context
    text_results: Annotated[list[dict[str, Any]], _replace]
    visual_results: Annotated[list[dict[str, Any]], _replace]
    graph_results: Annotated[list[dict[str, Any]], _replace]
    fused_context: Annotated[list[dict[str, Any]], _replace]

    # Response
    response: str
    source_documents: Annotated[list[dict[str, Any]], _replace]
    follow_up_questions: Annotated[list[str], _replace]
    entities_mentioned: Annotated[list[dict[str, Any]], _replace]

    # Internal routing
    _relevance: str
    _reformulated: bool
    _filters: dict[str, Any] | None


def _route_relevance(state: dict) -> str:
    """Conditional edge after ``check_relevance``.

    - If relevant → proceed to ``graph_lookup``
    - If not relevant AND not yet reformulated → ``reformulate``
    - If not relevant but already reformulated → ``graph_lookup`` (proceed anyway)
    """
    relevance = state.get("_relevance", "relevant")
    reformulated = state.get("_reformulated", False)

    if relevance == "relevant":
        return "graph_lookup"
    if not reformulated:
        return "reformulate"
    # Already tried reformulation — proceed with what we have
    return "graph_lookup"


def build_graph(
    llm: LLMClient,
    retriever: HybridRetriever,
    graph_service: GraphService,
    entity_extractor: EntityExtractor,
) -> StateGraph:
    """Construct and return the (uncompiled) investigation ``StateGraph``.

    The caller should ``.compile()`` before invoking.
    """
    from app.query.nodes import create_nodes

    nodes = create_nodes(llm, retriever, graph_service, entity_extractor)

    graph = StateGraph(InvestigationState)

    # Register nodes
    graph.add_node("classify", nodes["classify"])
    graph.add_node("rewrite", nodes["rewrite"])
    graph.add_node("retrieve", nodes["retrieve"])
    graph.add_node("rerank", nodes["rerank"])
    graph.add_node("check_relevance", nodes["check_relevance"])
    graph.add_node("graph_lookup", nodes["graph_lookup"])
    graph.add_node("reformulate", nodes["reformulate"])
    graph.add_node("synthesize", nodes["synthesize"])
    graph.add_node("generate_follow_ups", nodes["generate_follow_ups"])

    # Linear edges
    graph.add_edge(START, "classify")
    graph.add_edge("classify", "rewrite")
    graph.add_edge("rewrite", "retrieve")
    graph.add_edge("retrieve", "rerank")
    graph.add_edge("rerank", "check_relevance")

    # Conditional edge: relevance routing
    graph.add_conditional_edges(
        "check_relevance",
        _route_relevance,
        {
            "graph_lookup": "graph_lookup",
            "reformulate": "reformulate",
        },
    )

    # Reformulate loops back to retrieve
    graph.add_edge("reformulate", "retrieve")

    # Final linear path
    graph.add_edge("graph_lookup", "synthesize")
    graph.add_edge("synthesize", "generate_follow_ups")
    graph.add_edge("generate_follow_ups", END)

    return graph
