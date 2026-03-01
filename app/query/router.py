"""Query and chat API endpoints.

POST /query             -- single query (returns full response)
POST /query/stream      -- streaming query (SSE)
GET  /chats             -- list chat threads
GET  /chats/{thread_id} -- get full chat history
DELETE /chats/{thread_id} -- delete chat thread
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.auth.middleware import get_current_user, get_matter_id
from app.common.rate_limit import rate_limit_queries
from app.dependencies import get_db, get_query_graph
from app.query.schemas import (
    ChatHistoryResponse,
    ChatMessage,
    ChatThread,
    CitedClaim,
    EntityMention,
    QueryRequest,
    QueryResponse,
    SourceDocument,
)

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["query"])

# Map LangGraph node names to SSE stage names for the client
_STAGE_MAP = {
    # V1 nodes
    "classify": "classifying",
    "rewrite": "rewriting",
    "retrieve": "retrieving",
    "rerank": "reranking",
    "check_relevance": "checking_relevance",
    "graph_lookup": "graph_lookup",
    "reformulate": "reformulating",
    "synthesize": "analyzing",
    "generate_follow_ups": "generating_follow_ups",
    # Agentic nodes
    "case_context_resolve": "resolving_context",
    "investigation_agent": "investigating",
    "verify_citations": "verifying_citations",
}


# ------------------------------------------------------------------
# State construction helpers
# ------------------------------------------------------------------


def _build_agentic_state(
    *,
    query: str,
    messages: list[dict[str, Any]],
    thread_id: str,
    user_id: str,
    matter_id: str,
    filters: dict | None,
    exclude_privilege: list[str],
) -> dict[str, Any]:
    """Build initial state for the agentic graph (MessagesState format)."""
    from langchain_core.messages import HumanMessage

    # Convert chat history to LangChain message objects + append current query
    lc_messages = []
    for msg in messages:
        if msg["role"] == "user":
            lc_messages.append(HumanMessage(content=msg["content"]))
        else:
            from langchain_core.messages import AIMessage

            lc_messages.append(AIMessage(content=msg["content"]))
    lc_messages.append(HumanMessage(content=query))

    return {
        "messages": lc_messages,
        "original_query": query,
        "thread_id": thread_id,
        "user_id": user_id,
        "_case_context": "",  # populated by case_context_resolve
        "_term_map": {},
        "_filters": {**(filters or {}), "matter_id": matter_id},
        "_exclude_privilege": exclude_privilege,
        "_tier": "standard",
        "_skip_verification": False,
        "response": "",
        "source_documents": [],
        "cited_claims": [],
        "follow_up_questions": [],
        "entities_mentioned": [],
    }


def _build_graph_config(thread_id: str, settings: Any) -> dict[str, Any]:
    """Build the LangGraph config dict with checkpointer thread_id and recursion_limit."""
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    if settings.enable_agentic_pipeline:
        config["recursion_limit"] = settings.agentic_recursion_limit_standard
    return config


def _extract_response(final_state: dict[str, Any], is_agentic: bool) -> str:
    """Extract the response text from the final graph state.

    For the agentic graph, the response is in the last AIMessage's content.
    For v1, it's in the ``response`` field directly.
    """
    if final_state.get("response"):
        return final_state["response"]

    if is_agentic:
        messages = final_state.get("messages", [])
        for msg in reversed(messages):
            content = ""
            if hasattr(msg, "content"):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
            elif isinstance(msg, dict):
                content = msg.get("content", "")
            role = getattr(msg, "type", None) or (msg.get("role") if isinstance(msg, dict) else None)
            if role in ("ai", "assistant") and content:
                return content

    return ""


# ------------------------------------------------------------------
# Chat persistence helpers (raw SQL, same pattern as IngestionService)
# ------------------------------------------------------------------


async def _save_message(
    db: AsyncSession,
    thread_id: str,
    role: str,
    content: str,
    source_documents: list[dict] | None = None,
    entities_mentioned: list[dict] | None = None,
    follow_up_questions: list[str] | None = None,
    matter_id: UUID | None = None,
) -> str:
    """Insert a message into ``chat_messages`` and return its id."""
    message_id = str(uuid.uuid4())
    await db.execute(
        text("""
            INSERT INTO chat_messages
                (id, thread_id, role, content, source_documents, entities_mentioned,
                 follow_up_questions, matter_id, created_at)
            VALUES
                (:id, :thread_id, :role, :content, :source_documents, :entities_mentioned,
                 :follow_up_questions, :matter_id, :created_at)
        """),
        {
            "id": message_id,
            "thread_id": thread_id,
            "role": role,
            "content": content,
            "source_documents": json.dumps(source_documents or []),
            "entities_mentioned": json.dumps(entities_mentioned or []),
            "follow_up_questions": json.dumps(follow_up_questions or []),
            "matter_id": matter_id,
            "created_at": datetime.now(UTC),
        },
    )
    return message_id


async def _load_thread_messages(
    db: AsyncSession,
    thread_id: str,
    matter_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Load all messages for a thread, ordered by creation time."""
    where = "WHERE thread_id = :thread_id"
    params: dict[str, Any] = {"thread_id": thread_id}
    if matter_id is not None:
        where += " AND matter_id = :matter_id"
        params["matter_id"] = matter_id

    result = await db.execute(
        text(f"""
            SELECT id, thread_id, role, content, source_documents,
                   entities_mentioned, follow_up_questions, created_at
            FROM chat_messages
            {where}
            ORDER BY created_at ASC
        """),
        params,
    )
    rows = result.mappings().all()
    return [dict(r) for r in rows]


def _parse_jsonb(val: Any) -> list[Any]:
    """Safely parse a JSONB column that may be a string, list, or None."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return list(parsed) if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


# ------------------------------------------------------------------
# POST /query — full (non-streaming) endpoint
# ------------------------------------------------------------------


@router.post("/query", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
    graph=Depends(get_query_graph),
    _rate_limit=Depends(rate_limit_queries),
):
    """Execute a single investigation query and return the full response."""
    from app.dependencies import get_settings

    settings = get_settings()
    thread_id = str(request.thread_id) if request.thread_id else str(uuid.uuid4())

    # Load chat history if continuing a thread
    messages: list[dict[str, Any]] = []
    if request.thread_id:
        rows = await _load_thread_messages(db, thread_id, matter_id=matter_id)
        messages = [{"role": r["role"], "content": r["content"]} for r in rows]

    exclude_privilege = ["privileged", "work_product"] if current_user["role"] not in ("admin", "attorney") else []

    if settings.enable_agentic_pipeline:
        initial_state = _build_agentic_state(
            query=request.query,
            messages=messages,
            thread_id=thread_id,
            user_id=str(current_user["id"]),
            matter_id=str(matter_id),
            filters=request.filters,
            exclude_privilege=exclude_privilege,
        )
    else:
        # V1 state
        case_context_text = ""
        try:
            from app.cases.context_resolver import CaseContextResolver

            ctx = await CaseContextResolver.get_context_for_matter(db, str(matter_id))
            if ctx:
                case_context_text = CaseContextResolver.format_context_for_prompt(ctx)
        except Exception:
            logger.debug("query.case_context_load_skipped")

        initial_state = {
            "messages": messages,
            "thread_id": thread_id,
            "user_id": str(current_user["id"]),
            "original_query": request.query,
            "rewritten_query": "",
            "query_type": "",
            "text_results": [],
            "visual_results": [],
            "graph_results": [],
            "fused_context": [],
            "response": "",
            "source_documents": [],
            "follow_up_questions": [],
            "entities_mentioned": [],
            "_case_context": case_context_text,
            "_relevance": "",
            "_reformulated": False,
            "_filters": {**(request.filters or {}), "matter_id": str(matter_id)},
            "_exclude_privilege": exclude_privilege,
        }

    config = _build_graph_config(thread_id, settings)
    final_state = await graph.ainvoke(initial_state, config)

    # Extract response (agentic: from last AI message; v1: from response field)
    response_text = _extract_response(final_state, settings.enable_agentic_pipeline)

    # Save user message
    await _save_message(db, thread_id, "user", request.query, matter_id=matter_id)

    # Save assistant response
    message_id = await _save_message(
        db,
        thread_id,
        "assistant",
        response_text,
        source_documents=final_state.get("source_documents", []),
        entities_mentioned=final_state.get("entities_mentioned", []),
        follow_up_questions=final_state.get("follow_up_questions", []),
        matter_id=matter_id,
    )

    await db.commit()

    return QueryResponse(
        response=response_text,
        source_documents=[SourceDocument(**doc) for doc in final_state.get("source_documents", [])],
        follow_up_questions=final_state.get("follow_up_questions", []),
        entities_mentioned=[EntityMention(**ent) for ent in final_state.get("entities_mentioned", [])],
        thread_id=uuid.UUID(thread_id),
        message_id=uuid.UUID(message_id),
        cited_claims=[CitedClaim(**c) for c in final_state.get("cited_claims", []) if "claim_text" in c],
        tier=final_state.get("_tier"),
    )


# ------------------------------------------------------------------
# POST /query/stream — SSE streaming endpoint
# ------------------------------------------------------------------


@router.post("/query/stream")
async def query_stream(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
    graph=Depends(get_query_graph),
    _rate_limit=Depends(rate_limit_queries),
):
    """Execute a query with Server-Sent Events streaming.

    Supports both v1 and agentic graph variants:
    - v1: ``stream_mode=["updates", "custom"]``
    - agentic: ``stream_mode=["messages", "updates", "custom"]``
    """
    from app.dependencies import get_settings

    settings = get_settings()
    thread_id = str(request.thread_id) if request.thread_id else str(uuid.uuid4())

    # Load chat history
    messages: list[dict[str, Any]] = []
    if request.thread_id:
        rows = await _load_thread_messages(db, thread_id, matter_id=matter_id)
        messages = [{"role": r["role"], "content": r["content"]} for r in rows]

    exclude_privilege = ["privileged", "work_product"] if current_user["role"] not in ("admin", "attorney") else []

    if settings.enable_agentic_pipeline:
        initial_state = _build_agentic_state(
            query=request.query,
            messages=messages,
            thread_id=thread_id,
            user_id=str(current_user["id"]),
            matter_id=str(matter_id),
            filters=request.filters,
            exclude_privilege=exclude_privilege,
        )
    else:
        stream_case_context = ""
        try:
            from app.cases.context_resolver import CaseContextResolver

            ctx = await CaseContextResolver.get_context_for_matter(db, str(matter_id))
            if ctx:
                stream_case_context = CaseContextResolver.format_context_for_prompt(ctx)
        except Exception:
            logger.debug("query_stream.case_context_load_skipped")

        initial_state = {
            "messages": messages,
            "thread_id": thread_id,
            "user_id": str(current_user["id"]),
            "original_query": request.query,
            "rewritten_query": "",
            "query_type": "",
            "text_results": [],
            "visual_results": [],
            "graph_results": [],
            "fused_context": [],
            "response": "",
            "source_documents": [],
            "follow_up_questions": [],
            "entities_mentioned": [],
            "_case_context": stream_case_context,
            "_relevance": "",
            "_reformulated": False,
            "_filters": {**(request.filters or {}), "matter_id": str(matter_id)},
            "_exclude_privilege": exclude_privilege,
        }

    config = _build_graph_config(thread_id, settings)

    if settings.enable_agentic_pipeline:
        return EventSourceResponse(
            _agentic_event_generator(graph, initial_state, config, db, thread_id, request.query, matter_id)
        )
    else:
        return EventSourceResponse(
            _v1_event_generator(graph, initial_state, config, db, thread_id, request.query, matter_id)
        )


async def _v1_event_generator(graph, initial_state, config, db, thread_id, query_text, matter_id):
    """SSE event generator for the v1 graph."""
    final_state: dict[str, Any] = {}

    async for stream_mode, chunk in graph.astream(initial_state, config, stream_mode=["updates", "custom"]):
        if stream_mode == "updates":
            for node_name, update in chunk.items():
                stage = _STAGE_MAP.get(node_name, node_name)
                yield {"event": "status", "data": json.dumps({"stage": stage})}
                if node_name == "rerank" and "source_documents" in update:
                    yield {"event": "sources", "data": json.dumps({"documents": update["source_documents"]})}
                final_state.update(update)
        elif stream_mode == "custom":
            if isinstance(chunk, dict) and chunk.get("type") == "token":
                yield {"event": "token", "data": json.dumps({"text": chunk["text"]})}

    try:
        await _save_message(db, thread_id, "user", query_text, matter_id=matter_id)
        await _save_message(
            db,
            thread_id,
            "assistant",
            final_state.get("response", ""),
            source_documents=final_state.get("source_documents", []),
            entities_mentioned=final_state.get("entities_mentioned", []),
            follow_up_questions=final_state.get("follow_up_questions", []),
            matter_id=matter_id,
        )
        await db.commit()
    except Exception:
        logger.error("query_stream.save_failed")

    yield {
        "event": "done",
        "data": json.dumps(
            {
                "thread_id": thread_id,
                "follow_ups": final_state.get("follow_up_questions", []),
                "entities": final_state.get("entities_mentioned", []),
            }
        ),
    }


async def _agentic_event_generator(graph, initial_state, config, db, thread_id, query_text, matter_id):
    """SSE event generator for the agentic graph.

    Uses ``stream_mode=["messages", "updates", "custom"]``:
    - "messages": yields AI message chunks (filter for content, not tool calls)
    - "updates": yields node completion events → SSE status events
    - "custom": yields progress events from verify_citations / case_context_resolve
    """
    final_state: dict[str, Any] = {}
    sources_emitted = False

    async for stream_mode, chunk in graph.astream(initial_state, config, stream_mode=["messages", "updates", "custom"]):
        if stream_mode == "updates":
            for node_name, update in chunk.items():
                stage = _STAGE_MAP.get(node_name, node_name)
                yield {"event": "status", "data": json.dumps({"stage": stage})}

                # Emit sources when the agent finishes (source_documents populated)
                if not sources_emitted and update.get("source_documents"):
                    yield {
                        "event": "sources",
                        "data": json.dumps({"documents": update["source_documents"]}),
                    }
                    sources_emitted = True

                final_state.update(update)

        elif stream_mode == "messages":
            # Messages channel: (message_chunk, metadata) tuples
            msg_chunk, metadata = chunk
            # Only emit content tokens from the agent's final response
            # (not tool call chunks)
            if hasattr(msg_chunk, "content") and msg_chunk.content:
                # Skip tool call messages
                tool_calls = getattr(msg_chunk, "tool_call_chunks", None)
                if not tool_calls:
                    content = msg_chunk.content
                    if isinstance(content, str) and content:
                        yield {"event": "token", "data": json.dumps({"text": content})}

        elif stream_mode == "custom":
            if isinstance(chunk, dict) and chunk.get("type") == "token":
                yield {"event": "token", "data": json.dumps({"text": chunk["text"]})}

    # Extract response
    from app.dependencies import get_settings

    settings = get_settings()
    response_text = _extract_response(final_state, settings.enable_agentic_pipeline)

    try:
        await _save_message(db, thread_id, "user", query_text, matter_id=matter_id)
        await _save_message(
            db,
            thread_id,
            "assistant",
            response_text,
            source_documents=final_state.get("source_documents", []),
            entities_mentioned=final_state.get("entities_mentioned", []),
            follow_up_questions=final_state.get("follow_up_questions", []),
            matter_id=matter_id,
        )
        await db.commit()
    except Exception:
        logger.error("query_stream.save_failed")

    yield {
        "event": "done",
        "data": json.dumps(
            {
                "thread_id": thread_id,
                "follow_ups": final_state.get("follow_up_questions", []),
                "entities": final_state.get("entities_mentioned", []),
                "cited_claims": final_state.get("cited_claims", []),
                "tier": final_state.get("_tier"),
            }
        ),
    }


# ------------------------------------------------------------------
# GET /chats — list all chat threads
# ------------------------------------------------------------------


@router.get("/chats")
async def list_chats(
    offset: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """List all chat threads with summary info."""
    result = await db.execute(
        text("""
            SELECT
                thread_id,
                COUNT(*) as message_count,
                MAX(created_at) as last_message_at,
                MIN(CASE WHEN role = 'user' THEN content END) as first_query
            FROM chat_messages
            WHERE matter_id = :matter_id
            GROUP BY thread_id
            ORDER BY MAX(created_at) DESC
            LIMIT :limit OFFSET :offset
        """),
        {"limit": limit, "offset": offset, "matter_id": matter_id},
    )
    rows = result.mappings().all()

    threads = [
        ChatThread(
            thread_id=uuid.UUID(str(r["thread_id"])),
            message_count=r["message_count"],
            last_message_at=r["last_message_at"],
            first_query=r["first_query"] or "",
        )
        for r in rows
    ]

    return {"threads": [t.model_dump() for t in threads]}


# ------------------------------------------------------------------
# GET /chats/{thread_id} — get full chat history
# ------------------------------------------------------------------


@router.get("/chats/{thread_id}")
async def get_chat(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Return the full message history for a chat thread."""
    rows = await _load_thread_messages(db, thread_id, matter_id=matter_id)

    if not rows:
        return JSONResponse(status_code=404, content={"detail": "Thread not found"})

    messages = [
        ChatMessage(
            role=r["role"],
            content=r["content"],
            source_documents=[SourceDocument(**doc) for doc in _parse_jsonb(r.get("source_documents"))],
            entities_mentioned=[EntityMention(**ent) for ent in _parse_jsonb(r.get("entities_mentioned"))],
            follow_up_questions=_parse_jsonb(r.get("follow_up_questions")),
            timestamp=r["created_at"],
        )
        for r in rows
    ]

    return ChatHistoryResponse(
        thread_id=uuid.UUID(thread_id),
        messages=messages,
    )


# ------------------------------------------------------------------
# DELETE /chats/{thread_id} — delete chat thread
# ------------------------------------------------------------------


@router.delete("/chats/{thread_id}")
async def delete_chat(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Delete a chat thread and all its messages."""
    result = await db.execute(
        text("DELETE FROM chat_messages WHERE thread_id = :thread_id AND matter_id = :matter_id"),
        {"thread_id": thread_id, "matter_id": matter_id},
    )
    await db.commit()

    deleted: int = result.rowcount or 0  # type: ignore[attr-defined]
    if deleted == 0:
        return JSONResponse(status_code=404, content={"detail": "Thread not found"})

    return {"detail": "deleted", "thread_id": thread_id, "messages_deleted": deleted}
