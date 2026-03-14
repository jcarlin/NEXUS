"""Business logic for deposition preparation workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from fastapi import HTTPException
from sqlalchemy import text

from app.depositions.prompts import DEPOSITION_QUESTIONS_PROMPT
from app.depositions.schemas import (
    DepositionPrepResponse,
    QuestionCategory,
    SuggestedQuestion,
    WitnessProfile,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.common.llm import LLMClient
    from app.entities.graph_service import GraphService

logger = structlog.get_logger(__name__)


class DepositionService:
    """Deposition preparation: witness profiling and question generation."""

    @staticmethod
    async def list_witnesses(
        db: AsyncSession,
        matter_id: UUID,
        graph_service: GraphService,
    ) -> tuple[list[WitnessProfile], int]:
        """List all person entities as potential deposition witnesses.

        Queries Neo4j for person entities with MENTIONED_IN relationships,
        returning profiles with document and connection counts.
        """
        matter_str = str(matter_id)

        # Query Neo4j for person entities in this matter
        cypher = """
        MATCH (e:Entity)
        WHERE e.type = 'person' AND e.matter_id = $matter_id
        OPTIONAL MATCH (e)-[:MENTIONED_IN]->(d:Document)
        WITH e, count(DISTINCT d) AS doc_count
        OPTIONAL MATCH (e)-[r]-(connected:Entity)
        WHERE connected.matter_id = $matter_id
        WITH e, doc_count, count(DISTINCT connected) AS conn_count
        RETURN e.name AS name,
               e.type AS type,
               doc_count,
               conn_count,
               coalesce(e.party_role, '') AS party_role
        ORDER BY doc_count DESC
        """

        try:
            records = await graph_service._run_query(cypher, {"matter_id": matter_str})
        except Exception:
            logger.error("depositions.list_witnesses.graph_failed", matter_id=matter_str)
            raise

        witnesses: list[WitnessProfile] = []
        for record in records:
            roles = []
            party_role = record.get("party_role", "")
            if party_role:
                roles.append(party_role)

            witnesses.append(
                WitnessProfile(
                    name=record["name"],
                    entity_type=record.get("type", "person"),
                    document_count=record.get("doc_count", 0),
                    connection_count=record.get("conn_count", 0),
                    roles=roles,
                )
            )

        logger.info("depositions.list_witnesses", count=len(witnesses), matter_id=matter_str)
        return witnesses, len(witnesses)

    @staticmethod
    async def build_witness_profile(
        db: AsyncSession,
        matter_id: UUID,
        witness_name: str,
        graph_service: GraphService,
    ) -> WitnessProfile:
        """Build a full witness profile from Neo4j entity data and document mentions."""
        matter_str = str(matter_id)

        # 1. Get entity by name from Neo4j
        entity = await graph_service.get_entity_by_name(
            name=witness_name,
            entity_type="person",
            matter_id=matter_str,
        )
        if entity is None:
            raise HTTPException(
                status_code=404,
                detail=f"Witness '{witness_name}' not found in knowledge graph",
            )

        # 2. Get entity connections
        connections = await graph_service.get_entity_connections(
            entity_name=witness_name,
            matter_id=matter_str,
            limit=50,
        )

        connected_entities = [
            {
                "name": conn.get("target", ""),
                "relationship": conn.get("relationship_type", ""),
                "labels": conn.get("target_labels", []),
            }
            for conn in connections
        ]

        # 3. Get document mentions via SQL
        result = await db.execute(
            text(
                """
                SELECT DISTINCT d.id, d.filename, d.summary,
                       d.page_count, d.created_at
                FROM documents d
                JOIN chunks c ON c.document_id = d.id
                JOIN chunk_entities ce ON ce.chunk_id = c.id
                WHERE d.matter_id = :matter_id
                  AND LOWER(ce.entity_name) = LOWER(:witness_name)
                ORDER BY d.created_at
                """
            ),
            {"matter_id": str(matter_id), "witness_name": witness_name},
        )
        doc_rows = result.all()

        document_mentions = [
            {
                "document_id": str(row._mapping["id"]),
                "filename": row._mapping["filename"],
                "summary": row._mapping.get("summary"),
                "page_count": row._mapping.get("page_count"),
            }
            for row in doc_rows
        ]

        # 4. Determine roles from graph data
        roles: list[str] = []
        party_role = entity.get("party_role") or ""
        if party_role:
            roles.append(party_role)

        # Check for role-indicating relationships
        for conn in connections:
            rel_type = conn.get("relationship_type", "")
            if rel_type in ("EMPLOYED_BY", "WORKS_FOR"):
                roles.append(f"employee of {conn.get('target', '')}")
            elif rel_type in ("REPORTS_TO",):
                roles.append(f"reports to {conn.get('target', '')}")

        logger.info(
            "depositions.build_profile",
            witness=witness_name,
            documents=len(document_mentions),
            connections=len(connected_entities),
        )

        return WitnessProfile(
            name=witness_name,
            entity_type=entity.get("type", "person"),
            document_count=len(document_mentions),
            connection_count=len(connected_entities),
            connected_entities=connected_entities,
            document_mentions=document_mentions,
            roles=roles,
        )

    @staticmethod
    async def generate_prep_package(
        db: AsyncSession,
        matter_id: UUID,
        witness_name: str,
        graph_service: GraphService,
        llm: LLMClient,
        max_questions: int = 15,
        focus_categories: list[QuestionCategory] | None = None,
    ) -> DepositionPrepResponse:
        """Build a full deposition preparation package.

        1. Build witness profile (Neo4j + SQL)
        2. Gather document summaries
        3. Generate targeted questions via LLM with structured output
        """
        # 1. Build witness profile
        profile = await DepositionService.build_witness_profile(
            db=db,
            matter_id=matter_id,
            witness_name=witness_name,
            graph_service=graph_service,
        )

        # 2. Gather document summaries from SQL
        result = await db.execute(
            text(
                """
                SELECT d.id, d.filename, d.summary
                FROM documents d
                JOIN chunks c ON c.document_id = d.id
                JOIN chunk_entities ce ON ce.chunk_id = c.id
                WHERE d.matter_id = :matter_id
                  AND LOWER(ce.entity_name) = LOWER(:witness_name)
                  AND d.summary IS NOT NULL
                ORDER BY d.created_at
                LIMIT 50
                """
            ),
            {"matter_id": str(matter_id), "witness_name": witness_name},
        )
        summary_rows = result.all()

        document_summaries = [
            {
                "document_id": str(row._mapping["id"]),
                "filename": row._mapping["filename"],
                "summary": row._mapping["summary"],
            }
            for row in summary_rows
        ]

        # 3. Format context for LLM
        doc_summaries_text = "\n".join(
            f"- [{s['filename']}] (ID: {s['document_id']}): {s['summary']}" for s in document_summaries
        )
        if not doc_summaries_text:
            doc_summaries_text = "No document summaries available."

        entity_connections_text = "\n".join(
            f"- {c['name']} ({c['relationship']})" for c in profile.connected_entities[:20]
        )
        if not entity_connections_text:
            entity_connections_text = "No entity connections found."

        focus_instruction = ""
        if focus_categories:
            cats = ", ".join(c.value for c in focus_categories)
            focus_instruction = f"Focus primarily on these question categories: {cats}."

        prompt = DEPOSITION_QUESTIONS_PROMPT.format(
            witness_name=witness_name,
            witness_roles=", ".join(profile.roles) if profile.roles else "Unknown",
            connected_entities=entity_connections_text,
            document_count=profile.document_count,
            document_summaries=doc_summaries_text,
            entity_connections=entity_connections_text,
            max_questions=max_questions,
            focus_instruction=focus_instruction,
        )

        # 4. Generate questions via LLM
        raw_response = await llm.complete(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.3,
        )

        questions = _parse_questions(raw_response, max_questions)

        logger.info(
            "depositions.prep_generated",
            witness=witness_name,
            questions=len(questions),
            documents=len(document_summaries),
        )

        return DepositionPrepResponse(
            witness=profile,
            questions=questions,
            document_summaries=document_summaries,
        )


def _parse_questions(raw_response: str, max_questions: int) -> list[SuggestedQuestion]:
    """Parse LLM response into SuggestedQuestion objects."""
    import json

    # Try to extract JSON array from response
    text = raw_response.strip()

    # Find JSON array boundaries
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        logger.warning("depositions.parse_questions.no_json_array")
        return []

    json_str = text[start : end + 1]

    try:
        items: list[dict[str, Any]] = json.loads(json_str)
    except json.JSONDecodeError:
        logger.warning("depositions.parse_questions.json_decode_error")
        return []

    questions: list[SuggestedQuestion] = []
    for item in items[:max_questions]:
        try:
            # Validate category
            category = item.get("category", "document_specific")
            if category not in QuestionCategory.__members__:
                category = "document_specific"

            questions.append(
                SuggestedQuestion(
                    question=item["question"],
                    category=QuestionCategory(category),
                    basis_document_ids=item.get("basis_document_ids", []),
                    rationale=item.get("rationale", ""),
                )
            )
        except (KeyError, ValueError):
            logger.warning("depositions.parse_questions.invalid_item", item=str(item)[:100])
            continue

    return questions
