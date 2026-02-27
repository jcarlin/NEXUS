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
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.common.rate_limit import rate_limit_queries
from app.dependencies import get_db, get_query_graph
from app.query.schemas import (
    ChatHistoryResponse,
    ChatMessage,
    ChatThread,
    EntityMention,
    QueryRequest,
    QueryResponse,
    SourceDocument,
)

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["query"])

# Map LangGraph node names to SSE stage names for the client
_STAGE_MAP = {
    "classify": "classifying",
    "rewrite": "rewriting",
    "retrieve": "retrieving",
    "rerank": "reranking",
    "check_relevance": "checking_relevance",
    "graph_lookup": "graph_lookup",
    "reformulate": "reformulating",
    "synthesize": "analyzing",
    "generate_follow_ups": "generating_follow_ups",
}


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
) -> str:
    """Insert a message into ``chat_messages`` and return its id."""
    message_id = str(uuid.uuid4())
    await db.execute(
        text("""
            INSERT INTO chat_messages
                (id, thread_id, role, content, source_documents, entities_mentioned, follow_up_questions, created_at)
            VALUES
                (:id, :thread_id, :role, :content, :source_documents, :entities_mentioned, :follow_up_questions, :created_at)
        """),
        {
            "id": message_id,
            "thread_id": thread_id,
            "role": role,
            "content": content,
            "source_documents": json.dumps(source_documents or []),
            "entities_mentioned": json.dumps(entities_mentioned or []),
            "follow_up_questions": json.dumps(follow_up_questions or []),
            "created_at": datetime.now(timezone.utc),
        },
    )
    return message_id


async def _load_thread_messages(
    db: AsyncSession,
    thread_id: str,
) -> list[dict[str, Any]]:
    """Load all messages for a thread, ordered by creation time."""
    result = await db.execute(
        text("""
            SELECT id, thread_id, role, content, source_documents,
                   entities_mentioned, follow_up_questions, created_at
            FROM chat_messages
            WHERE thread_id = :thread_id
            ORDER BY created_at ASC
        """),
        {"thread_id": thread_id},
    )
    rows = result.mappings().all()
    return [dict(r) for r in rows]


def _parse_jsonb(val: Any) -> list:
    """Safely parse a JSONB column that may be a string, list, or None."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
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
    graph=Depends(get_query_graph),
    _rate_limit=Depends(rate_limit_queries),
):
    """Execute a single investigation query and return the full response."""
    thread_id = str(request.thread_id) if request.thread_id else str(uuid.uuid4())

    # Load chat history if continuing a thread
    messages: list[dict[str, Any]] = []
    if request.thread_id:
        rows = await _load_thread_messages(db, thread_id)
        messages = [
            {"role": r["role"], "content": r["content"]}
            for r in rows
        ]

    # Build initial state
    initial_state = {
        "messages": messages,
        "thread_id": thread_id,
        "user_id": "default",
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
        "_relevance": "",
        "_reformulated": False,
        "_filters": request.filters,
    }

    # Run the graph with checkpointer config
    config = {"configurable": {"thread_id": thread_id}}
    final_state = await graph.ainvoke(initial_state, config)

    # Save user message
    await _save_message(db, thread_id, "user", request.query)

    # Save assistant response
    message_id = await _save_message(
        db,
        thread_id,
        "assistant",
        final_state.get("response", ""),
        source_documents=final_state.get("source_documents", []),
        entities_mentioned=final_state.get("entities_mentioned", []),
        follow_up_questions=final_state.get("follow_up_questions", []),
    )

    # Flush to DB
    await db.commit()

    return QueryResponse(
        response=final_state.get("response", ""),
        source_documents=[
            SourceDocument(**doc)
            for doc in final_state.get("source_documents", [])
        ],
        follow_up_questions=final_state.get("follow_up_questions", []),
        entities_mentioned=[
            EntityMention(**ent)
            for ent in final_state.get("entities_mentioned", [])
        ],
        thread_id=uuid.UUID(thread_id),
        message_id=uuid.UUID(message_id),
    )


# ------------------------------------------------------------------
# POST /query/stream — SSE streaming endpoint
# ------------------------------------------------------------------


@router.post("/query/stream")
async def query_stream(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
    graph=Depends(get_query_graph),
    _rate_limit=Depends(rate_limit_queries),
):
    """Execute a query with Server-Sent Events streaming.

    Uses ``graph.astream()`` with ``stream_mode=["updates", "custom"]``:
    - "updates" channel emits node outputs (used for status + sources events)
    - "custom" channel emits token-level data from ``get_stream_writer()``
      inside the synthesize node
    """
    thread_id = str(request.thread_id) if request.thread_id else str(uuid.uuid4())

    # Load chat history
    messages: list[dict[str, Any]] = []
    if request.thread_id:
        rows = await _load_thread_messages(db, thread_id)
        messages = [{"role": r["role"], "content": r["content"]} for r in rows]

    initial_state = {
        "messages": messages,
        "thread_id": thread_id,
        "user_id": "default",
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
        "_relevance": "",
        "_reformulated": False,
        "_filters": request.filters,
    }

    config = {"configurable": {"thread_id": thread_id}}

    async def event_generator():
        final_state: dict[str, Any] = {}

        async for stream_mode, chunk in graph.astream(
            initial_state, config, stream_mode=["updates", "custom"]
        ):
            if stream_mode == "updates":
                for node_name, update in chunk.items():
                    # Emit status event for each node
                    stage = _STAGE_MAP.get(node_name, node_name)
                    yield {
                        "event": "status",
                        "data": json.dumps({"stage": stage}),
                    }
                    # Emit sources after rerank node
                    if node_name == "rerank" and "source_documents" in update:
                        yield {
                            "event": "sources",
                            "data": json.dumps({"documents": update["source_documents"]}),
                        }
                    # Accumulate state from all nodes
                    final_state.update(update)

            elif stream_mode == "custom":
                # Custom channel: token events from synthesize node
                if isinstance(chunk, dict) and chunk.get("type") == "token":
                    yield {
                        "event": "token",
                        "data": json.dumps({"text": chunk["text"]}),
                    }

        # Save messages to DB
        try:
            await _save_message(db, thread_id, "user", request.query)
            await _save_message(
                db,
                thread_id,
                "assistant",
                final_state.get("response", ""),
                source_documents=final_state.get("source_documents", []),
                entities_mentioned=final_state.get("entities_mentioned", []),
                follow_up_questions=final_state.get("follow_up_questions", []),
            )
            await db.commit()
        except Exception:
            logger.error("query_stream.save_failed")

        # Done event
        yield {
            "event": "done",
            "data": json.dumps({
                "thread_id": thread_id,
                "follow_ups": final_state.get("follow_up_questions", []),
                "entities": final_state.get("entities_mentioned", []),
            }),
        }

    return EventSourceResponse(event_generator())


# ------------------------------------------------------------------
# GET /chats — list all chat threads
# ------------------------------------------------------------------


@router.get("/chats")
async def list_chats(
    offset: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
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
            GROUP BY thread_id
            ORDER BY MAX(created_at) DESC
            LIMIT :limit OFFSET :offset
        """),
        {"limit": limit, "offset": offset},
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
):
    """Return the full message history for a chat thread."""
    rows = await _load_thread_messages(db, thread_id)

    if not rows:
        return JSONResponse(status_code=404, content={"detail": "Thread not found"})

    messages = [
        ChatMessage(
            role=r["role"],
            content=r["content"],
            source_documents=[
                SourceDocument(**doc)
                for doc in _parse_jsonb(r.get("source_documents"))
            ],
            entities_mentioned=[
                EntityMention(**ent)
                for ent in _parse_jsonb(r.get("entities_mentioned"))
            ],
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
):
    """Delete a chat thread and all its messages."""
    result = await db.execute(
        text("DELETE FROM chat_messages WHERE thread_id = :thread_id"),
        {"thread_id": thread_id},
    )
    await db.commit()

    deleted = result.rowcount
    if deleted == 0:
        return JSONResponse(status_code=404, content={"detail": "Thread not found"})

    return {"detail": "deleted", "thread_id": thread_id, "messages_deleted": deleted}
