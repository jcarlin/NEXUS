"""Query and chat service layer.

Business logic extracted from query/router.py:
- QueryService: graph state construction and response extraction
- ChatService: chat message persistence (raw SQL)
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings

logger = structlog.get_logger(__name__)


def _extract_text_from_content(content: str | list) -> str:
    """Extract plain text from LLM content that may be a string or list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            if isinstance(block, dict) and block.get("type") == "text"
            else block
            if isinstance(block, str)
            else ""
            for block in content
        )
    return str(content)


class QueryService:
    """Static methods for query graph state construction and response extraction."""

    @staticmethod
    def build_agentic_state(
        *,
        query: str,
        messages: list[dict[str, Any]],
        thread_id: str,
        user_id: str,
        matter_id: str,
        filters: dict | None,
        exclude_privilege: list[str],
        dataset_doc_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build initial state for the agentic graph (MessagesState format)."""
        lc_messages = []
        for msg in messages:
            if msg["role"] == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            else:
                lc_messages.append(AIMessage(content=msg["content"]))
        lc_messages.append(HumanMessage(content=query))

        return {
            "messages": lc_messages,
            "original_query": query,
            "thread_id": thread_id,
            "user_id": user_id,
            "_case_context": "",
            "_term_map": {},
            "_filters": {**(filters or {}), "matter_id": matter_id},
            "_exclude_privilege": exclude_privilege,
            "_dataset_doc_ids": dataset_doc_ids,
            "_tier": "standard",
            "_skip_verification": False,
            "response": "",
            "source_documents": [],
            "cited_claims": [],
            "follow_up_questions": [],
            "entities_mentioned": [],
        }

    @staticmethod
    async def build_v1_state(
        *,
        query: str,
        messages: list[dict[str, Any]],
        thread_id: str,
        user_id: str,
        matter_id: str,
        filters: dict | None,
        exclude_privilege: list[str],
        db: AsyncSession,
        settings: Settings,
        dataset_doc_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build initial state for the v1 graph."""
        case_context_text = ""
        if settings.enable_case_setup_agent:
            from app.cases.context_resolver import CaseContextResolver

            ctx = await CaseContextResolver.get_context_for_matter(db, matter_id)
            if ctx:
                case_context_text = CaseContextResolver.format_context_for_prompt(ctx)

        return {
            "messages": messages,
            "thread_id": thread_id,
            "user_id": user_id,
            "original_query": query,
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
            "_filters": {**(filters or {}), "matter_id": matter_id},
            "_exclude_privilege": exclude_privilege,
            "_dataset_doc_ids": dataset_doc_ids,
        }

    @staticmethod
    def build_graph_config(thread_id: str, settings: Settings) -> dict[str, Any]:
        """Build the LangGraph config dict with checkpointer thread_id and recursion_limit."""
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        if settings.enable_agentic_pipeline:
            config["recursion_limit"] = settings.agentic_recursion_limit_standard
        return config

    @staticmethod
    def extract_response(final_state: dict[str, Any], is_agentic: bool) -> str:
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
                    content = _extract_text_from_content(msg.content)
                elif isinstance(msg, dict):
                    content = _extract_text_from_content(msg.get("content", ""))
                role = getattr(msg, "type", None) or (msg.get("role") if isinstance(msg, dict) else None)
                if role in ("ai", "assistant") and content:
                    return content

        return ""


class ChatService:
    """Static methods for chat message persistence."""

    @staticmethod
    async def save_message(
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

    @staticmethod
    async def load_thread_messages(
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
