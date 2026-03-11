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
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import AIMessageChunk
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.auth.middleware import get_current_user, get_matter_id
from app.auth.schemas import UserRecord
from app.common.db_utils import parse_jsonb
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
from app.query.service import ChatService, QueryService

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
    "post_agent_extract": "extracting_results",
    "verify_citations": "verifying_citations",
}


# ------------------------------------------------------------------
# POST /query — full (non-streaming) endpoint
# ------------------------------------------------------------------


@router.post("/query", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
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
        rows = await ChatService.load_thread_messages(db, thread_id, matter_id=matter_id)
        messages = [{"role": r["role"], "content": r["content"]} for r in rows]

    exclude_privilege = ["privileged", "work_product"] if current_user.role not in ("admin", "attorney") else []

    # Resolve dataset_id to document IDs for Qdrant filtering
    dataset_doc_ids: list[str] | None = None
    if request.dataset_id:
        from app.datasets.service import DatasetService

        dataset_doc_ids = await DatasetService.get_document_ids_for_dataset(db, request.dataset_id, matter_id)

    if settings.enable_agentic_pipeline:
        initial_state = QueryService.build_agentic_state(
            query=request.query,
            messages=messages,
            thread_id=thread_id,
            user_id=str(current_user.id),
            matter_id=str(matter_id),
            filters=request.filters,
            exclude_privilege=exclude_privilege,
            dataset_doc_ids=dataset_doc_ids,
        )
    else:
        initial_state = await QueryService.build_v1_state(
            query=request.query,
            messages=messages,
            thread_id=thread_id,
            user_id=str(current_user.id),
            matter_id=str(matter_id),
            filters=request.filters,
            exclude_privilege=exclude_privilege,
            db=db,
            settings=settings,
            dataset_doc_ids=dataset_doc_ids,
        )

    config = QueryService.build_graph_config(thread_id, settings, request.query)
    final_state = await graph.ainvoke(initial_state, config)

    # Extract response (agentic: from last AI message; v1: from response field)
    response_text = QueryService.extract_response(final_state, settings.enable_agentic_pipeline)

    # Save user message
    await ChatService.save_message(db, thread_id, "user", request.query, matter_id=matter_id)

    # Save assistant response
    message_id = await ChatService.save_message(
        db,
        thread_id,
        "assistant",
        response_text,
        source_documents=final_state.get("source_documents", []),
        entities_mentioned=final_state.get("entities_mentioned", []),
        follow_up_questions=final_state.get("follow_up_questions", []),
        matter_id=matter_id,
        cited_claims=final_state.get("cited_claims", []),
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
    current_user: UserRecord = Depends(get_current_user),
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
        rows = await ChatService.load_thread_messages(db, thread_id, matter_id=matter_id)
        messages = [{"role": r["role"], "content": r["content"]} for r in rows]

    exclude_privilege = ["privileged", "work_product"] if current_user.role not in ("admin", "attorney") else []

    # Resolve dataset_id to document IDs for Qdrant filtering
    dataset_doc_ids: list[str] | None = None
    if request.dataset_id:
        from app.datasets.service import DatasetService

        dataset_doc_ids = await DatasetService.get_document_ids_for_dataset(db, request.dataset_id, matter_id)

    if settings.enable_agentic_pipeline:
        initial_state = QueryService.build_agentic_state(
            query=request.query,
            messages=messages,
            thread_id=thread_id,
            user_id=str(current_user.id),
            matter_id=str(matter_id),
            filters=request.filters,
            exclude_privilege=exclude_privilege,
            dataset_doc_ids=dataset_doc_ids,
        )
    else:
        initial_state = await QueryService.build_v1_state(
            query=request.query,
            messages=messages,
            thread_id=thread_id,
            user_id=str(current_user.id),
            matter_id=str(matter_id),
            filters=request.filters,
            exclude_privilege=exclude_privilege,
            db=db,
            settings=settings,
            dataset_doc_ids=dataset_doc_ids,
        )

    config = QueryService.build_graph_config(thread_id, settings, request.query)

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
    client_disconnected = False
    graph_error = False
    stream_completed = False

    try:
        async for stream_mode, chunk in graph.astream(initial_state, config, stream_mode=["updates", "custom"]):
            if stream_mode == "updates":
                for node_name, update in chunk.items():
                    if update is None:
                        continue
                    stage = _STAGE_MAP.get(node_name, node_name)
                    yield {"event": "status", "data": json.dumps({"stage": stage})}
                    if node_name == "rerank" and "source_documents" in update:
                        yield {"event": "sources", "data": json.dumps({"documents": update["source_documents"]})}
                    final_state.update(update)
            elif stream_mode == "custom":
                if isinstance(chunk, dict) and chunk.get("type") == "token":
                    yield {"event": "token", "data": json.dumps({"text": chunk["text"]})}
        stream_completed = True
    except GeneratorExit:
        logger.info("query_stream.client_disconnected", thread_id=thread_id)
        client_disconnected = True
    except Exception:
        logger.error("query_stream.graph_error", thread_id=thread_id, exc_info=True)
        graph_error = True

    # Persist user message (always) and assistant message (only if stream completed fully).
    try:
        await ChatService.save_message(db, thread_id, "user", query_text, matter_id=matter_id)
        response_text = final_state.get("response", "")
        if response_text and stream_completed:
            await ChatService.save_message(
                db,
                thread_id,
                "assistant",
                response_text,
                source_documents=final_state.get("source_documents", []),
                entities_mentioned=final_state.get("entities_mentioned", []),
                follow_up_questions=final_state.get("follow_up_questions", []),
                matter_id=matter_id,
                cited_claims=final_state.get("cited_claims", []),
            )
        await db.commit()
    except Exception:
        logger.error("query_stream.save_failed", thread_id=thread_id, exc_info=True)

    if client_disconnected:
        return

    if graph_error:
        yield {
            "event": "error",
            "data": json.dumps({"message": "An error occurred while processing your query. Please try again."}),
        }
        return

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
    client_disconnected = False
    graph_error = False
    stream_completed = False
    # Track current message ID to detect when a "thinking" message turns into
    # a tool call.  When that happens we emit a ``clear`` SSE event so the
    # frontend discards the tokens that were prematurely streamed.
    _cur_msg_id: str | None = None
    _cur_msg_had_tool_calls = False
    _emitted_tokens_for_cur_msg = False

    try:
        async for ns, stream_mode, chunk in graph.astream(
            initial_state, config, stream_mode=["messages", "updates", "custom"], subgraphs=True
        ):
            if stream_mode == "updates":
                for node_name, update in chunk.items():
                    if update is None:
                        continue
                    stage = _STAGE_MAP.get(node_name, node_name)
                    yield {"event": "status", "data": json.dumps({"stage": stage})}

                    # Emit sources when post_agent_extract populates source_documents
                    if not sources_emitted and update.get("source_documents"):
                        yield {
                            "event": "sources",
                            "data": json.dumps({"documents": update["source_documents"]}),
                        }
                        sources_emitted = True

                    # Only update final_state from root-level nodes (not subgraph internals)
                    if not ns:
                        final_state.update(update)

            elif stream_mode == "messages":
                # Messages channel: (message_chunk, metadata) tuples
                msg_chunk, metadata = chunk
                if not isinstance(msg_chunk, AIMessageChunk):
                    continue

                # Detect message boundary — reset tracking when a new message starts.
                # Real LLM streams always set chunk ids; None ids (e.g. in tests)
                # are treated as distinct messages each time.
                chunk_id = msg_chunk.id
                if chunk_id != _cur_msg_id or chunk_id is None:
                    _cur_msg_id = chunk_id
                    _cur_msg_had_tool_calls = False
                    _emitted_tokens_for_cur_msg = False

                # If this chunk carries tool call data, mark the message and
                # tell the frontend to discard any tokens we already sent for it.
                if msg_chunk.tool_call_chunks:
                    if not _cur_msg_had_tool_calls and _emitted_tokens_for_cur_msg:
                        yield {"event": "clear", "data": "{}"}
                    _cur_msg_had_tool_calls = True

                # Only emit content tokens from messages that haven't produced
                # tool calls (i.e. the final answer, not intermediate "thinking").
                if msg_chunk.content and not _cur_msg_had_tool_calls:
                    content = msg_chunk.content
                    if isinstance(content, list):
                        for block in content:
                            text_val = ""
                            if isinstance(block, dict) and block.get("type") == "text":
                                text_val = block.get("text", "")
                            elif isinstance(block, str):
                                text_val = block
                            if text_val:
                                yield {"event": "token", "data": json.dumps({"text": text_val})}
                                _emitted_tokens_for_cur_msg = True
                    elif isinstance(content, str) and content:
                        yield {"event": "token", "data": json.dumps({"text": content})}
                        _emitted_tokens_for_cur_msg = True

            elif stream_mode == "custom":
                if isinstance(chunk, dict) and chunk.get("type") == "token":
                    yield {"event": "token", "data": json.dumps({"text": chunk["text"]})}
        stream_completed = True
    except GeneratorExit:
        logger.info("query_stream.client_disconnected", thread_id=thread_id)
        client_disconnected = True
    except Exception:
        logger.error("query_stream.graph_error", thread_id=thread_id, exc_info=True)
        graph_error = True

    # Extract response
    try:
        from app.dependencies import get_settings

        settings = get_settings()
        response_text = QueryService.extract_response(final_state, settings.enable_agentic_pipeline)
    except Exception:
        logger.error("query_stream.extract_failed", thread_id=thread_id, exc_info=True)
        response_text = ""

    # Persist user message (always) and assistant message (only if stream completed fully).
    try:
        await ChatService.save_message(db, thread_id, "user", query_text, matter_id=matter_id)
        if response_text and stream_completed:
            await ChatService.save_message(
                db,
                thread_id,
                "assistant",
                response_text,
                source_documents=final_state.get("source_documents", []),
                entities_mentioned=final_state.get("entities_mentioned", []),
                follow_up_questions=final_state.get("follow_up_questions", []),
                matter_id=matter_id,
                cited_claims=final_state.get("cited_claims", []),
            )
        await db.commit()
    except Exception:
        logger.error("query_stream.save_failed", thread_id=thread_id, exc_info=True)

    if client_disconnected:
        return

    if graph_error:
        yield {
            "event": "error",
            "data": json.dumps({"message": "An error occurred while processing your query. Please try again."}),
        }
        return

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
    current_user: UserRecord = Depends(get_current_user),
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
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Return the message history for a chat thread with pagination."""
    rows = await ChatService.load_thread_messages(db, thread_id, matter_id=matter_id, limit=limit, offset=offset)

    if not rows:
        raise HTTPException(status_code=404, detail="Thread not found")

    messages = [
        ChatMessage(
            role=r["role"],
            content=r["content"],
            source_documents=[SourceDocument(**doc) for doc in parse_jsonb(r.get("source_documents"))],
            entities_mentioned=[EntityMention(**ent) for ent in parse_jsonb(r.get("entities_mentioned"))],
            follow_up_questions=parse_jsonb(r.get("follow_up_questions")),
            cited_claims=[CitedClaim(**c) for c in parse_jsonb(r.get("cited_claims")) if "claim_text" in c],
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
    current_user: UserRecord = Depends(get_current_user),
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
        raise HTTPException(status_code=404, detail="Thread not found")

    return {"detail": "deleted", "thread_id": thread_id, "messages_deleted": deleted}
