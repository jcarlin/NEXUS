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

from app.dependencies import (
    get_db,
    get_embedder,
    get_entity_extractor,
    get_graph_service,
    get_llm,
    get_query_graph,
    get_retriever,
)
from app.query.nodes import (
    _format_chat_history,
    _format_context,
    _format_graph_context,
    create_nodes,
)
from app.query.prompts import SYNTHESIS_PROMPT
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

    # Run the graph
    final_state = await graph.ainvoke(initial_state)

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
    llm=Depends(get_llm),
    retriever=Depends(get_retriever),
    graph_service=Depends(get_graph_service),
    entity_extractor=Depends(get_entity_extractor),
):
    """Execute a query with Server-Sent Events streaming.

    Calls node functions directly (not ``graph.ainvoke``) so that the
    synthesis step can stream tokens incrementally.
    """
    thread_id = str(request.thread_id) if request.thread_id else str(uuid.uuid4())

    # Load chat history
    messages: list[dict[str, Any]] = []
    if request.thread_id:
        rows = await _load_thread_messages(db, thread_id)
        messages = [{"role": r["role"], "content": r["content"]} for r in rows]

    nodes = create_nodes(llm, retriever, graph_service, entity_extractor)

    async def event_generator():
        state: dict[str, Any] = {
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

        # Phase 1: Classify
        yield {"event": "status", "data": json.dumps({"stage": "classifying"})}
        update = await nodes["classify"](state)
        state.update(update)

        # Phase 2: Rewrite
        yield {"event": "status", "data": json.dumps({"stage": "rewriting"})}
        update = await nodes["rewrite"](state)
        state.update(update)

        # Phase 3: Retrieve
        yield {"event": "status", "data": json.dumps({"stage": "retrieving"})}
        update = await nodes["retrieve"](state)
        state.update(update)

        # Phase 4: Rerank
        update = await nodes["rerank"](state)
        state.update(update)

        # Phase 5: Check relevance + possible reformulation loop
        update = await nodes["check_relevance"](state)
        state.update(update)

        if state.get("_relevance") == "not_relevant" and not state.get("_reformulated"):
            yield {"event": "status", "data": json.dumps({"stage": "reformulating"})}
            update = await nodes["reformulate"](state)
            state.update(update)

            yield {"event": "status", "data": json.dumps({"stage": "retrieving"})}
            update = await nodes["retrieve"](state)
            state.update(update)
            update = await nodes["rerank"](state)
            state.update(update)

        # Phase 6: Graph lookup
        yield {"event": "status", "data": json.dumps({"stage": "graph_lookup"})}
        update = await nodes["graph_lookup"](state)
        state.update(update)

        # Emit sources BEFORE generation starts
        yield {
            "event": "sources",
            "data": json.dumps({"documents": state.get("source_documents", [])}),
        }

        # Phase 7: Stream synthesis tokens
        yield {"event": "status", "data": json.dumps({"stage": "analyzing"})}

        query = state.get("rewritten_query") or state["original_query"]
        context = _format_context(state.get("fused_context", []))
        graph_context = _format_graph_context(state.get("graph_results", []))

        synthesis_prompt = SYNTHESIS_PROMPT.format(
            context=context,
            graph_context=graph_context,
            query=query,
        )

        full_response = ""
        async for token in llm.stream(
            [
                {"role": "system", "content": "You are a legal investigation analyst."},
                {"role": "user", "content": synthesis_prompt},
            ],
            max_tokens=2048,
            temperature=0.1,
        ):
            full_response += token
            yield {"event": "token", "data": json.dumps({"text": token})}

        state["response"] = full_response

        # Extract entities from response
        entities_mentioned: list[dict[str, Any]] = []
        try:
            raw_entities = entity_extractor.extract(
                full_response,
                entity_types=["person", "organization", "location", "vehicle"],
                threshold=0.4,
            )
            seen_names: set[str] = set()
            for ent in raw_entities:
                name_lower = ent.text.lower()
                if name_lower not in seen_names:
                    seen_names.add(name_lower)
                    entities_mentioned.append({
                        "name": ent.text,
                        "type": ent.type,
                        "kg_id": None,
                        "connections": 0,
                    })
        except Exception:
            logger.warning("query_stream.entity_extraction_failed")

        state["entities_mentioned"] = entities_mentioned

        # Phase 8: Follow-ups
        update = await nodes["generate_follow_ups"](state)
        state.update(update)

        # Save messages to DB
        try:
            await _save_message(db, thread_id, "user", request.query)
            await _save_message(
                db,
                thread_id,
                "assistant",
                full_response,
                source_documents=state.get("source_documents", []),
                entities_mentioned=entities_mentioned,
                follow_up_questions=state.get("follow_up_questions", []),
            )
            await db.commit()
        except Exception:
            logger.error("query_stream.save_failed")

        # Done event
        yield {
            "event": "done",
            "data": json.dumps({
                "thread_id": thread_id,
                "follow_ups": state.get("follow_up_questions", []),
                "entities": entities_mentioned,
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
