"""Shareable chat link endpoints.

Authenticated:
    POST /chats/{thread_id}/share   -- create share link
    DELETE /chats/{thread_id}/share  -- revoke share link

Public (no auth):
    GET  /shared/{share_token}              -- get shared conversation
    GET  /shared/{share_token}/og           -- OG meta tag HTML for link previews
    POST /shared/{share_token}/query/stream -- follow-up question (SSE)
"""

from __future__ import annotations

import json
import uuid
from html import escape as html_escape
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.auth.middleware import get_current_user, get_matter_id
from app.auth.schemas import UserRecord
from app.common.db_utils import parse_jsonb
from app.dependencies import get_db, get_settings
from app.query.schemas import ChatMessage, CitedClaim, EntityMention, SourceDocument, ToolCallEntry
from app.query.service import ChatService, QueryService
from app.shared.schemas import (
    CreateShareRequest,
    CreateShareResponse,
    RevokeShareResponse,
    SharedChatResponse,
    SharedQueryRequest,
)
from app.shared.service import SharedChatService

logger = structlog.get_logger(__name__)

# --- Authenticated router (requires auth + matter-id) ---
auth_router = APIRouter(tags=["shared"])

# --- Public router (no auth) ---
public_router = APIRouter(tags=["shared"])


# ------------------------------------------------------------------
# POST /chats/{thread_id}/share — create share link (authenticated)
# ------------------------------------------------------------------


@auth_router.post("/chats/{thread_id}/share", response_model=CreateShareResponse)
async def create_share_link(
    thread_id: str,
    body: CreateShareRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: uuid.UUID = Depends(get_matter_id),
):
    """Create a shareable link for a chat conversation."""
    settings = get_settings()
    if not settings.enable_shareable_links:
        raise HTTPException(status_code=403, detail="Shareable links are not enabled.")

    try:
        result = await SharedChatService.create_share(
            db=db,
            thread_id=thread_id,
            matter_id=matter_id,
            user_id=current_user.id,
            allow_follow_ups=body.allow_follow_ups,
            expires_in_days=body.expires_in_days,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    # Build the share URL from the request's base URL
    base_url = str(request.base_url).rstrip("/")
    # Frontend route: /shared/{token}
    share_url = f"{base_url}/shared/{result['share_token']}"

    # If CORS origins are configured, use the first one as the frontend URL
    if settings.cors_allowed_origins:
        frontend_origin = settings.cors_allowed_origins.split(",")[0].strip()
        if frontend_origin:
            share_url = f"{frontend_origin}/shared/{result['share_token']}"

    return CreateShareResponse(
        share_token=result["share_token"],
        share_url=share_url,
        expires_at=result["expires_at"],
    )


# ------------------------------------------------------------------
# DELETE /chats/{thread_id}/share — revoke share link (authenticated)
# ------------------------------------------------------------------


@auth_router.delete("/chats/{thread_id}/share", response_model=RevokeShareResponse)
async def revoke_share_link(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
):
    """Revoke all active share links for a chat thread."""
    revoked = await SharedChatService.revoke_share(db, thread_id, current_user.id)
    if not revoked:
        raise HTTPException(status_code=404, detail="No active share link found for this thread.")
    return RevokeShareResponse(detail="Share link revoked successfully.")


# ------------------------------------------------------------------
# GET /shared/{share_token} — get shared conversation (public)
# ------------------------------------------------------------------


@public_router.get("/shared/{share_token}", response_model=SharedChatResponse)
async def get_shared_chat(
    share_token: str,
    db: AsyncSession = Depends(get_db),
):
    """View a shared conversation. No authentication required."""
    share = await SharedChatService.get_share_by_token(db, share_token)
    if not share:
        raise HTTPException(status_code=404, detail="Shared conversation not found or has expired.")

    raw_messages = await SharedChatService.load_shared_messages(db, str(share["thread_id"]))

    messages = []
    first_query = ""
    first_response_preview = ""

    for msg in raw_messages:
        messages.append(
            ChatMessage(
                role=msg["role"],
                content=msg["content"],
                source_documents=[SourceDocument(**d) for d in msg.get("source_documents", []) if isinstance(d, dict)],
                entities_mentioned=[EntityMention(**e) for e in msg.get("entities_mentioned", []) if isinstance(e, dict)],
                follow_up_questions=msg.get("follow_up_questions", []),
                cited_claims=[CitedClaim(**c) for c in msg.get("cited_claims", []) if isinstance(c, dict) and "claim_text" in c],
                tool_calls=[ToolCallEntry(**t) for t in msg.get("tool_calls", []) if isinstance(t, dict)],
                timestamp=msg.get("timestamp"),
            )
        )

        if not first_query and msg["role"] == "user":
            first_query = msg["content"][:200]
        if not first_response_preview and msg["role"] == "assistant":
            first_response_preview = msg["content"][:300]

    return SharedChatResponse(
        thread_id=share["thread_id"],
        messages=messages,
        allow_follow_ups=share["allow_follow_ups"],
        created_at=share["created_at"],
        expires_at=share.get("expires_at"),
        first_query=first_query,
        first_response_preview=first_response_preview,
    )


# ------------------------------------------------------------------
# GET /shared/{share_token}/og — OG meta tags HTML for link previews
# ------------------------------------------------------------------


@public_router.get("/shared/{share_token}/og", response_class=HTMLResponse)
async def shared_chat_og_page(
    share_token: str,
    db: AsyncSession = Depends(get_db),
):
    """Serve HTML with Open Graph meta tags for rich link previews.

    When shared via iMessage, WhatsApp, Slack, or Twitter, their crawlers
    fetch this URL and extract OG tags for the preview card.
    """
    share = await SharedChatService.get_share_by_token(db, share_token)
    if not share:
        return HTMLResponse("<html><body>Conversation not found.</body></html>", status_code=404)

    raw_messages = await SharedChatService.load_shared_messages(db, str(share["thread_id"]))

    first_query = "Shared Conversation"
    first_response = "View this NEXUS investigation conversation."

    for msg in raw_messages:
        if msg["role"] == "user" and first_query == "Shared Conversation":
            first_query = msg["content"][:150]
        if msg["role"] == "assistant" and first_response == "View this NEXUS investigation conversation.":
            first_response = msg["content"][:250]

    title = html_escape(first_query)
    description = html_escape(first_response)

    settings = get_settings()
    frontend_origin = "http://localhost:5173"
    if settings.cors_allowed_origins:
        frontend_origin = settings.cors_allowed_origins.split(",")[0].strip()

    canonical_url = f"{frontend_origin}/shared/{share_token}"
    message_count = len(raw_messages)

    html = f"""<!DOCTYPE html>
<html lang="en" prefix="og: https://ogp.me/ns#">
<head>
    <meta charset="utf-8" />
    <title>{title} - NEXUS</title>
    <meta name="description" content="{description}" />
    <meta name="robots" content="index, follow" />

    <!-- Open Graph -->
    <meta property="og:type" content="article" />
    <meta property="og:title" content="{title}" />
    <meta property="og:description" content="{description}" />
    <meta property="og:site_name" content="NEXUS" />
    <meta property="og:url" content="{html_escape(canonical_url)}" />

    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary" />
    <meta name="twitter:title" content="{title}" />
    <meta name="twitter:description" content="{description}" />

    <!-- JSON-LD Structured Data for SEO -->
    <script type="application/ld+json">
    {{
        "@context": "https://schema.org",
        "@type": "QAPage",
        "mainEntity": {{
            "@type": "Question",
            "name": "{title}",
            "text": "{title}",
            "answerCount": 1,
            "acceptedAnswer": {{
                "@type": "Answer",
                "text": "{description}"
            }}
        }}
    }}
    </script>

    <meta http-equiv="refresh" content="0;url={html_escape(canonical_url)}" />
</head>
<body>
    <h1>{title}</h1>
    <p>{description}</p>
    <p>{message_count} messages in this conversation.</p>
    <p><a href="{html_escape(canonical_url)}">View full conversation on NEXUS</a></p>
</body>
</html>"""

    return HTMLResponse(html)


# ------------------------------------------------------------------
# POST /shared/{share_token}/query/stream — follow-up (public, SSE)
# ------------------------------------------------------------------


@public_router.post("/shared/{share_token}/query/stream")
async def shared_query_stream(
    share_token: str,
    body: SharedQueryRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Ask a follow-up question on a shared conversation. No auth required.

    Rate-limited to 5 requests/minute per IP.
    """
    from app.common.rate_limit import rate_limit_shared_queries

    await rate_limit_shared_queries(request)

    share = await SharedChatService.get_share_by_token(db, share_token)
    if not share:
        raise HTTPException(status_code=404, detail="Shared conversation not found or has expired.")

    if not share["allow_follow_ups"]:
        raise HTTPException(status_code=403, detail="Follow-up questions are disabled for this shared conversation.")

    settings = get_settings()
    thread_id = str(share["thread_id"])
    matter_id = str(share["matter_id"])

    # Load chat history
    rows = await ChatService.load_thread_messages(db, thread_id)
    messages = [{"role": r["role"], "content": r["content"]} for r in rows]

    # Shared users get no privilege access
    exclude_privilege = ["privileged", "work_product"]

    # Build state and run the query graph
    from app.dependencies import get_query_graph

    graph = get_query_graph()
    use_agentic = settings.enable_agentic_pipeline

    if use_agentic:
        initial_state = QueryService.build_agentic_state(
            query=body.query,
            messages=messages,
            thread_id=thread_id,
            user_id="shared",
            matter_id=matter_id,
            filters=None,
            exclude_privilege=exclude_privilege,
            dataset_doc_ids=None,
            retrieval_overrides=None,
        )
    else:
        initial_state = await QueryService.build_v1_state(
            query=body.query,
            messages=messages,
            thread_id=thread_id,
            user_id="shared",
            matter_id=matter_id,
            filters=None,
            exclude_privilege=exclude_privilege,
            db=db,
            settings=settings,
            dataset_doc_ids=None,
            retrieval_overrides=None,
        )

    config = QueryService.build_graph_config(thread_id, settings, body.query)

    if use_agentic:
        return EventSourceResponse(
            _shared_agentic_event_generator(graph, initial_state, config, db, thread_id, body.query, share["matter_id"])
        )
    else:
        return EventSourceResponse(
            _shared_v1_event_generator(graph, initial_state, config, db, thread_id, body.query, share["matter_id"])
        )


# ------------------------------------------------------------------
# SSE generators for shared queries (simplified, no debug/trace)
# ------------------------------------------------------------------

# Reuse stage maps from query router
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
    "case_context_resolve": "resolving_context",
    "investigation_agent": "investigating",
    "post_agent_extract": "extracting_results",
    "verify_citations": "verifying_citations",
}


async def _shared_v1_event_generator(
    graph: Any, initial_state: dict, config: dict, db: AsyncSession,
    thread_id: str, query_text: str, matter_id: Any,
):
    """SSE event generator for shared V1 queries."""
    final_state: dict[str, Any] = {}

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
    except GeneratorExit:
        return
    except Exception:
        logger.error("shared_stream.v1_error", thread_id=thread_id, exc_info=True)
        yield {"event": "error", "data": json.dumps({"message": "Query processing failed."})}
        return

    response_text = QueryService.extract_response(final_state, is_agentic=False)

    await ChatService.save_message(db, thread_id, "user", query_text, matter_id=matter_id)
    await ChatService.save_message(
        db, thread_id, "assistant", response_text,
        source_documents=final_state.get("source_documents", []),
        entities_mentioned=final_state.get("entities_mentioned", []),
        follow_up_questions=final_state.get("follow_up_questions", []),
        matter_id=matter_id,
        cited_claims=final_state.get("cited_claims", []),
    )
    await db.commit()

    yield {
        "event": "done",
        "data": json.dumps({
            "thread_id": thread_id,
            "follow_ups": final_state.get("follow_up_questions", []),
            "entities": final_state.get("entities_mentioned", []),
            "cited_claims": final_state.get("cited_claims", []),
        }),
    }


async def _shared_agentic_event_generator(
    graph: Any, initial_state: dict, config: dict, db: AsyncSession,
    thread_id: str, query_text: str, matter_id: Any,
):
    """SSE event generator for shared agentic queries."""
    from langchain_core.messages import AIMessageChunk

    final_state: dict[str, Any] = {}
    accumulated_text = ""

    try:
        async for stream_mode, chunk in graph.astream(
            initial_state, config, stream_mode=["messages", "updates", "custom"]
        ):
            if stream_mode == "messages":
                msg, metadata = chunk
                if isinstance(msg, AIMessageChunk) and msg.content:
                    parent = metadata.get("langgraph_node", "")
                    if parent in ("investigation_agent", "post_agent_extract"):
                        text_content = msg.content if isinstance(msg.content, str) else ""
                        if text_content:
                            accumulated_text += text_content
                            yield {"event": "token", "data": json.dumps({"text": text_content})}
            elif stream_mode == "updates":
                for node_name, update in chunk.items():
                    if update is None:
                        continue
                    stage = _STAGE_MAP.get(node_name)
                    if stage:
                        yield {"event": "status", "data": json.dumps({"stage": stage})}
                    if isinstance(update, dict):
                        final_state.update(update)
            elif stream_mode == "custom":
                if isinstance(chunk, dict):
                    if chunk.get("type") == "token":
                        yield {"event": "token", "data": json.dumps({"text": chunk["text"]})}
                    elif chunk.get("type") == "sources":
                        yield {"event": "sources", "data": json.dumps({"documents": chunk.get("documents", [])})}
    except GeneratorExit:
        return
    except Exception:
        logger.error("shared_stream.agentic_error", thread_id=thread_id, exc_info=True)
        yield {"event": "error", "data": json.dumps({"message": "Query processing failed."})}
        return

    response_text = QueryService.extract_response(final_state, is_agentic=True)

    await ChatService.save_message(db, thread_id, "user", query_text, matter_id=matter_id)
    await ChatService.save_message(
        db, thread_id, "assistant", response_text,
        source_documents=final_state.get("source_documents", []),
        entities_mentioned=final_state.get("entities_mentioned", []),
        follow_up_questions=final_state.get("follow_up_questions", []),
        matter_id=matter_id,
        cited_claims=final_state.get("cited_claims", []),
    )
    await db.commit()

    yield {
        "event": "done",
        "data": json.dumps({
            "thread_id": thread_id,
            "follow_ups": final_state.get("follow_up_questions", []),
            "entities": final_state.get("entities_mentioned", []),
            "cited_claims": final_state.get("cited_claims", []),
        }),
    }
