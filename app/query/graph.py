"""LangGraph state graphs for the investigation query pipeline.

Two graph variants:
  * **v1** (``build_graph_v1``): Fixed 9-node chain (classify → ... → follow_ups).
  * **agentic** (``build_agentic_graph``): 4-node parent graph with a
    ``create_react_agent`` subgraph that handles tool selection and iteration.

``build_graph()`` is the public factory — it reads ``enable_agentic_pipeline``
from settings to decide which variant to compile.

Agentic edge structure::

    START → case_context_resolve → investigation_agent → verify_citations
          → generate_follow_ups → END

The ``investigation_agent`` node is a compiled ``create_react_agent`` subgraph
that handles the entire agentic loop (tool binding, execution, routing,
iteration caps) via LangGraph's built-in ``ToolNode`` + ``tools_condition``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.managed.is_last_step import RemainingStepsManager

if TYPE_CHECKING:
    from app.common.llm import LLMClient
    from app.config import Settings
    from app.entities.extractor import EntityExtractor
    from app.entities.graph_service import GraphService
    from app.query.retriever import HybridRetriever


# ---------------------------------------------------------------------------
# Shared reducer
# ---------------------------------------------------------------------------


def _replace(existing: list, new: list) -> list:
    """Reducer that replaces a list field wholesale (no append semantics)."""
    return new


# ---------------------------------------------------------------------------
# V1 state schema (unchanged)
# ---------------------------------------------------------------------------


class InvestigationState(TypedDict, total=False):
    """State schema for the v1 investigation query pipeline."""

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

    # Case context (injected by router when available)
    _case_context: str

    # Internal routing
    _relevance: str
    _reformulated: bool
    _filters: dict[str, Any] | None
    _exclude_privilege: list[str]


# ---------------------------------------------------------------------------
# Agentic state schema (M10)
# ---------------------------------------------------------------------------


class AgentState(TypedDict, total=False):
    """State schema for the agentic investigation pipeline.

    Uses LangGraph's ``add_messages`` reducer for the ``messages`` field so
    that the ``create_react_agent`` subgraph can append tool calls/results.
    ``remaining_steps`` is required by ``create_react_agent`` v2.
    """

    # Conversation (add_messages reducer for agent compatibility)
    messages: Annotated[list[BaseMessage], add_messages]
    thread_id: str
    user_id: str

    # Required by create_react_agent v2
    remaining_steps: Annotated[int, RemainingStepsManager]

    # Query
    original_query: str

    # Case context (injected by case_context_resolve)
    _case_context: str
    _term_map: dict[str, str]

    # Security scoping (injected by router, hidden from LLM)
    _filters: dict[str, Any] | None
    _exclude_privilege: list[str]

    # Tier classification
    _tier: str
    _skip_verification: bool

    # Response fields (populated after agent runs)
    response: str
    source_documents: Annotated[list[dict[str, Any]], _replace]
    cited_claims: Annotated[list[dict[str, Any]], _replace]
    follow_up_questions: Annotated[list[str], _replace]
    entities_mentioned: Annotated[list[dict[str, Any]], _replace]


# ---------------------------------------------------------------------------
# V1 graph
# ---------------------------------------------------------------------------


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
    return "graph_lookup"


def build_graph_v1(
    llm: LLMClient,
    retriever: HybridRetriever,
    graph_service: GraphService,
    entity_extractor: EntityExtractor,
) -> StateGraph:
    """Construct and return the v1 (uncompiled) investigation ``StateGraph``."""
    from app.query.nodes import create_nodes_v1

    nodes = create_nodes_v1(llm, retriever, graph_service, entity_extractor)

    graph = StateGraph(InvestigationState)

    graph.add_node("classify", nodes["classify"])
    graph.add_node("rewrite", nodes["rewrite"])
    graph.add_node("retrieve", nodes["retrieve"])
    graph.add_node("rerank", nodes["rerank"])
    graph.add_node("check_relevance", nodes["check_relevance"])
    graph.add_node("graph_lookup", nodes["graph_lookup"])
    graph.add_node("reformulate", nodes["reformulate"])
    graph.add_node("synthesize", nodes["synthesize"])
    graph.add_node("generate_follow_ups", nodes["generate_follow_ups"])

    graph.add_edge(START, "classify")
    graph.add_edge("classify", "rewrite")
    graph.add_edge("rewrite", "retrieve")
    graph.add_edge("retrieve", "rerank")
    graph.add_edge("rerank", "check_relevance")

    graph.add_conditional_edges(
        "check_relevance",
        _route_relevance,
        {"graph_lookup": "graph_lookup", "reformulate": "reformulate"},
    )
    graph.add_edge("reformulate", "retrieve")
    graph.add_edge("graph_lookup", "synthesize")
    graph.add_edge("synthesize", "generate_follow_ups")
    graph.add_edge("generate_follow_ups", END)

    return graph


# Backward-compatible alias
build_graph = build_graph_v1


# ---------------------------------------------------------------------------
# Agentic graph (M10)
# ---------------------------------------------------------------------------


def build_agentic_graph(settings: Settings, checkpointer: Any) -> Any:
    """Build and compile the agentic investigation graph.

    Architecture::

        START → case_context_resolve → investigation_agent
              → verify_citations → generate_follow_ups → END

    The ``investigation_agent`` node is a ``create_react_agent`` subgraph
    that handles the entire tool-calling loop.
    """
    from langchain_anthropic import ChatAnthropic
    from langgraph.prebuilt import create_react_agent

    from app.query.nodes import (
        audit_log_hook,
        build_system_prompt,
        case_context_resolve,
        generate_follow_ups_agentic,
        verify_citations,
    )
    from app.query.tools import INVESTIGATION_TOOLS

    # 1. Create ChatAnthropic model (library handles tool binding)
    model = ChatAnthropic(
        model=settings.llm_model,
        api_key=settings.anthropic_api_key,
        max_tokens=4096,
        temperature=0.1,
    )

    # 2. Create the agent subgraph
    agent = create_react_agent(
        model=model,
        tools=INVESTIGATION_TOOLS,
        prompt=build_system_prompt,
        state_schema=AgentState,
        post_model_hook=audit_log_hook,
        name="investigation_agent",
    )

    # 3. Build parent graph (pre/post processing around agent)
    parent = StateGraph(AgentState)
    parent.add_node("case_context_resolve", case_context_resolve)
    parent.add_node("investigation_agent", agent)
    parent.add_node("verify_citations", verify_citations)
    parent.add_node("generate_follow_ups", generate_follow_ups_agentic)

    parent.add_edge(START, "case_context_resolve")
    parent.add_edge("case_context_resolve", "investigation_agent")
    parent.add_edge("investigation_agent", "verify_citations")
    parent.add_edge("verify_citations", "generate_follow_ups")
    parent.add_edge("generate_follow_ups", END)

    return parent.compile(checkpointer=checkpointer)
