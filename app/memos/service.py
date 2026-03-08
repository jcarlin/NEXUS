"""Memo drafting service -- generates structured legal memos from investigation results."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.llm import LLMClient
from app.memos.prompts import (
    MEMO_GENERATION_PROMPT,
    MEMO_SYSTEM_PROMPT,
    MEMO_TITLE_PROMPT,
    SOURCE_INDEX_INSTRUCTION,
)
from app.memos.schemas import MemoFormat, MemoResponse, MemoSection

logger = structlog.get_logger(__name__)


class MemoService:
    """Static methods for memo generation and CRUD."""

    @staticmethod
    async def generate_memo(
        db: AsyncSession,
        matter_id: UUID,
        user_id: UUID,
        llm: LLMClient,
        *,
        thread_id: str | None = None,
        query: str | None = None,
        title: str | None = None,
        memo_format: MemoFormat = MemoFormat.MARKDOWN,
        include_source_index: bool = True,
    ) -> MemoResponse:
        """Generate a legal memo from thread messages or ad-hoc query."""
        # 1. Gather context (claims + sources)
        if thread_id:
            context = await MemoService._gather_thread_context(db, thread_id)
            query_text = query or await MemoService._get_thread_query(db, thread_id)
        elif query:
            context = ""
            query_text = query
        else:
            raise ValueError("Either thread_id or query must be provided")

        # 2. Generate title if not provided
        if not title:
            title = await MemoService._generate_title(llm, query_text)

        # 3. Generate memo content
        source_index_instruction = SOURCE_INDEX_INSTRUCTION if include_source_index else ""
        prompt = MEMO_GENERATION_PROMPT.format(
            query=query_text,
            context=context,
            source_index_instruction=source_index_instruction,
        )

        content = await llm.complete(
            messages=[
                {"role": "system", "content": MEMO_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4096,
            temperature=0.2,
        )

        # 4. Parse sections from markdown
        sections = MemoService._parse_sections(content)

        # 5. Persist to database
        memo_id = uuid4()
        now = datetime.now(UTC)

        sections_json = json.dumps([s.model_dump() for s in sections])
        await db.execute(
            text("""
                INSERT INTO memos (id, matter_id, thread_id, title, sections, format, created_by, created_at)
                VALUES (:id, :matter_id, :thread_id, :title, CAST(:sections AS jsonb), :format, :created_by, :created_at)
            """),
            {
                "id": memo_id,
                "matter_id": matter_id,
                "thread_id": thread_id,
                "title": title,
                "sections": sections_json,
                "format": memo_format.value,
                "created_by": user_id,
                "created_at": now,
            },
        )

        logger.info("memo.generated", memo_id=str(memo_id), title=title)

        return MemoResponse(
            id=memo_id,
            matter_id=matter_id,
            thread_id=thread_id,
            title=title,
            sections=sections,
            format=memo_format,
            created_by=user_id,
            created_at=now,
        )

    @staticmethod
    async def list_memos(
        db: AsyncSession,
        matter_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[MemoResponse], int]:
        """List memos for a matter."""
        count_result = await db.execute(
            text("SELECT COUNT(*) FROM memos WHERE matter_id = :matter_id"),
            {"matter_id": matter_id},
        )
        total = count_result.scalar() or 0

        result = await db.execute(
            text("""
                SELECT id, matter_id, thread_id, title, sections, format,
                       created_by, created_at
                FROM memos
                WHERE matter_id = :matter_id
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {"matter_id": matter_id, "limit": limit, "offset": offset},
        )
        rows = result.all()

        memos = []
        for row in rows:
            mapping = dict(row._mapping)
            sections_data = mapping["sections"]
            if isinstance(sections_data, str):
                sections_data = json.loads(sections_data)
            sections = [MemoSection.model_validate(s) for s in sections_data]
            memos.append(
                MemoResponse(
                    id=mapping["id"],
                    matter_id=mapping["matter_id"],
                    thread_id=mapping["thread_id"],
                    title=mapping["title"],
                    sections=sections,
                    format=MemoFormat(mapping["format"]),
                    created_by=mapping["created_by"],
                    created_at=mapping["created_at"],
                )
            )

        return memos, total

    @staticmethod
    async def get_memo(
        db: AsyncSession,
        memo_id: UUID,
        matter_id: UUID,
    ) -> MemoResponse | None:
        """Get a single memo by ID (matter-scoped)."""
        result = await db.execute(
            text("""
                SELECT id, matter_id, thread_id, title, sections, format,
                       created_by, created_at
                FROM memos
                WHERE id = :memo_id AND matter_id = :matter_id
            """),
            {"memo_id": memo_id, "matter_id": matter_id},
        )
        row = result.first()
        if row is None:
            return None

        mapping = dict(row._mapping)
        sections_data = mapping["sections"]
        if isinstance(sections_data, str):
            sections_data = json.loads(sections_data)
        sections = [MemoSection.model_validate(s) for s in sections_data]

        return MemoResponse(
            id=mapping["id"],
            matter_id=mapping["matter_id"],
            thread_id=mapping["thread_id"],
            title=mapping["title"],
            sections=sections,
            format=MemoFormat(mapping["format"]),
            created_by=mapping["created_by"],
            created_at=mapping["created_at"],
        )

    @staticmethod
    async def delete_memo(
        db: AsyncSession,
        memo_id: UUID,
        matter_id: UUID,
    ) -> bool:
        """Delete a memo (matter-scoped). Returns True if deleted."""
        result = await db.execute(
            text("DELETE FROM memos WHERE id = :memo_id AND matter_id = :matter_id"),
            {"memo_id": memo_id, "matter_id": matter_id},
        )
        deleted = (result.rowcount or 0) > 0
        if deleted:
            logger.info("memo.deleted", memo_id=str(memo_id))
        return deleted

    # --- Private helpers ---

    @staticmethod
    async def _gather_thread_context(
        db: AsyncSession,
        thread_id: str,
    ) -> str:
        """Gather cited claims and source documents from a chat thread."""
        result = await db.execute(
            text("""
                SELECT content, source_documents, cited_claims
                FROM chat_messages
                WHERE thread_id = :thread_id AND role = 'assistant'
                ORDER BY created_at ASC
            """),
            {"thread_id": thread_id},
        )
        rows = result.all()

        context_parts: list[str] = []
        for row in rows:
            mapping = dict(row._mapping)

            # Add cited claims
            claims = mapping.get("cited_claims")
            if claims:
                if isinstance(claims, str):
                    claims = json.loads(claims)
                for claim in claims:
                    claim_text = claim.get("claim", "")
                    source = claim.get("source_filename", "unknown")
                    page = claim.get("page_number", "")
                    context_parts.append(f"- {claim_text} (Source: {source}, p. {page})")

            # Add source documents
            sources = mapping.get("source_documents")
            if sources:
                if isinstance(sources, str):
                    sources = json.loads(sources)
                for src in sources:
                    filename = src.get("filename", "unknown")
                    chunk = src.get("chunk_text", "")[:200]
                    page = src.get("page", "")
                    context_parts.append(f"Document: {filename} (p. {page}): {chunk}")

        return "\n".join(context_parts) if context_parts else "No context available from thread."

    @staticmethod
    async def _get_thread_query(db: AsyncSession, thread_id: str) -> str:
        """Get the first user message from a thread as the query."""
        result = await db.execute(
            text("""
                SELECT content FROM chat_messages
                WHERE thread_id = :thread_id AND role = 'user'
                ORDER BY created_at ASC LIMIT 1
            """),
            {"thread_id": thread_id},
        )
        row = result.first()
        return row._mapping["content"] if row else "Investigation memo"

    @staticmethod
    async def _generate_title(llm: LLMClient, query: str) -> str:
        """Generate a concise memo title from the query."""
        prompt = MEMO_TITLE_PROMPT.format(query=query)
        title = await llm.complete(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0,
        )
        return title.strip().strip('"').strip("'")[:80]

    @staticmethod
    def _parse_sections(content: str) -> list[MemoSection]:
        """Parse markdown content into MemoSection objects."""
        sections: list[MemoSection] = []
        current_heading = ""
        current_lines: list[str] = []

        for line in content.split("\n"):
            if line.startswith("## ") or line.startswith("# "):
                # Save previous section
                if current_heading and current_lines:
                    sections.append(
                        MemoSection(
                            heading=current_heading,
                            content="\n".join(current_lines).strip(),
                        )
                    )
                current_heading = line.lstrip("#").strip()
                current_lines = []
            else:
                current_lines.append(line)

        # Save last section
        if current_heading and current_lines:
            sections.append(
                MemoSection(
                    heading=current_heading,
                    content="\n".join(current_lines).strip(),
                )
            )

        # If no sections parsed, wrap entire content as one section
        if not sections:
            sections.append(MemoSection(heading="Memorandum", content=content.strip()))

        return sections
