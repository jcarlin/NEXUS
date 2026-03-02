"""Case intelligence service layer.

Raw SQL CRUD operations for case contexts, claims, parties, defined terms,
and investigation sessions.  All queries are matter-scoped.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class CaseService:
    """Static methods for case context CRUD, following the existing service pattern."""

    @staticmethod
    async def create_case_context(
        db: AsyncSession,
        matter_id: str,
        anchor_document_id: str,
        created_by: str,
        job_id: str,
    ) -> dict[str, Any]:
        """Insert a new case_contexts row and return it."""
        context_id = str(uuid.uuid4())
        result = await db.execute(
            text("""
                INSERT INTO case_contexts
                    (id, matter_id, anchor_document_id, status, created_by, job_id,
                     created_at, updated_at)
                VALUES
                    (:id, :matter_id, :anchor_document_id, 'processing', :created_by,
                     :job_id, now(), now())
                RETURNING id, matter_id, anchor_document_id, status, created_by,
                          job_id, created_at, updated_at
            """),
            {
                "id": context_id,
                "matter_id": matter_id,
                "anchor_document_id": anchor_document_id,
                "created_by": created_by,
                "job_id": job_id,
            },
        )
        row = result.mappings().first()
        return dict(row) if row else {}

    @staticmethod
    async def get_case_context(
        db: AsyncSession,
        matter_id: str,
    ) -> dict[str, Any] | None:
        """Fetch the case context row for a matter (without claims/parties/terms)."""
        result = await db.execute(
            text("""
                SELECT id, matter_id, anchor_document_id, status, created_by,
                       confirmed_by, confirmed_at, job_id, timeline,
                       created_at, updated_at
                FROM case_contexts
                WHERE matter_id = :matter_id
            """),
            {"matter_id": matter_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    @staticmethod
    async def get_full_context(
        db: AsyncSession,
        matter_id: str,
    ) -> dict[str, Any] | None:
        """Fetch case context joined with claims, parties, and defined terms."""
        # Fetch context
        context = await CaseService.get_case_context(db, matter_id)
        if context is None:
            return None

        context_id = str(context["id"])

        # Fetch claims
        claims_result = await db.execute(
            text("""
                SELECT id, claim_number, claim_label, claim_text,
                       legal_elements, source_pages, created_at, updated_at
                FROM case_claims
                WHERE case_context_id = :context_id
                ORDER BY claim_number
            """),
            {"context_id": context_id},
        )
        claims = [dict(r) for r in claims_result.mappings().all()]

        # Fetch parties
        parties_result = await db.execute(
            text("""
                SELECT id, name, role, description, aliases, entity_id,
                       source_pages, created_at, updated_at
                FROM case_parties
                WHERE case_context_id = :context_id
                ORDER BY name
            """),
            {"context_id": context_id},
        )
        parties = [dict(r) for r in parties_result.mappings().all()]

        # Fetch defined terms
        terms_result = await db.execute(
            text("""
                SELECT id, term, definition, entity_id, source_pages,
                       created_at, updated_at
                FROM case_defined_terms
                WHERE case_context_id = :context_id
                ORDER BY term
            """),
            {"context_id": context_id},
        )
        defined_terms = [dict(r) for r in terms_result.mappings().all()]

        context["claims"] = claims
        context["parties"] = parties
        context["defined_terms"] = defined_terms

        # Parse timeline JSONB
        timeline_raw = context.get("timeline")
        if isinstance(timeline_raw, str):
            try:
                context["timeline"] = json.loads(timeline_raw)
            except (json.JSONDecodeError, TypeError):
                context["timeline"] = []
        elif timeline_raw is None:
            context["timeline"] = []

        return context

    @staticmethod
    async def update_case_context_status(
        db: AsyncSession,
        context_id: str,
        status: str,
        confirmed_by: str | None = None,
    ) -> dict[str, Any] | None:
        """Update the status of a case context."""
        if confirmed_by and status == "confirmed":
            result = await db.execute(
                text("""
                    UPDATE case_contexts
                    SET status = :status,
                        confirmed_by = :confirmed_by,
                        confirmed_at = now(),
                        updated_at = now()
                    WHERE id = :context_id
                    RETURNING id, matter_id, status, confirmed_by, confirmed_at, updated_at
                """),
                {
                    "context_id": context_id,
                    "status": status,
                    "confirmed_by": confirmed_by,
                },
            )
        else:
            result = await db.execute(
                text("""
                    UPDATE case_contexts
                    SET status = :status,
                        updated_at = now()
                    WHERE id = :context_id
                    RETURNING id, matter_id, status, updated_at
                """),
                {"context_id": context_id, "status": status},
            )
        row = result.mappings().first()
        return dict(row) if row else None

    @staticmethod
    async def upsert_claims(
        db: AsyncSession,
        context_id: str,
        claims: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Delete existing claims and insert new ones (full-replace semantics)."""
        await db.execute(
            text("DELETE FROM case_claims WHERE case_context_id = :context_id"),
            {"context_id": context_id},
        )

        inserted: list[dict[str, Any]] = []
        for claim in claims:
            claim_id = str(uuid.uuid4())
            result = await db.execute(
                text("""
                    INSERT INTO case_claims
                        (id, case_context_id, claim_number, claim_label, claim_text,
                         legal_elements, source_pages, created_at, updated_at)
                    VALUES
                        (:id, :context_id, :claim_number, :claim_label, :claim_text,
                         :legal_elements, :source_pages, now(), now())
                    RETURNING id, claim_number, claim_label, claim_text,
                              legal_elements, source_pages
                """),
                {
                    "id": claim_id,
                    "context_id": context_id,
                    "claim_number": claim["claim_number"],
                    "claim_label": claim["claim_label"],
                    "claim_text": claim["claim_text"],
                    "legal_elements": json.dumps(claim.get("legal_elements", [])),
                    "source_pages": json.dumps(claim.get("source_pages", [])),
                },
            )
            row = result.mappings().first()
            if row:
                inserted.append(dict(row))

        return inserted

    @staticmethod
    async def upsert_parties(
        db: AsyncSession,
        context_id: str,
        parties: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Delete existing parties and insert new ones (full-replace semantics)."""
        await db.execute(
            text("DELETE FROM case_parties WHERE case_context_id = :context_id"),
            {"context_id": context_id},
        )

        inserted: list[dict[str, Any]] = []
        for party in parties:
            party_id = str(uuid.uuid4())
            result = await db.execute(
                text("""
                    INSERT INTO case_parties
                        (id, case_context_id, name, role, description, aliases,
                         entity_id, source_pages, created_at, updated_at)
                    VALUES
                        (:id, :context_id, :name, :role, :description, :aliases,
                         :entity_id, :source_pages, now(), now())
                    RETURNING id, name, role, description, aliases, entity_id, source_pages
                """),
                {
                    "id": party_id,
                    "context_id": context_id,
                    "name": party["name"],
                    "role": party["role"],
                    "description": party.get("description"),
                    "aliases": json.dumps(party.get("aliases", [])),
                    "entity_id": party.get("entity_id"),
                    "source_pages": json.dumps(party.get("source_pages", [])),
                },
            )
            row = result.mappings().first()
            if row:
                inserted.append(dict(row))

        return inserted

    @staticmethod
    async def upsert_defined_terms(
        db: AsyncSession,
        context_id: str,
        terms: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Delete existing terms and insert new ones (full-replace semantics)."""
        await db.execute(
            text("DELETE FROM case_defined_terms WHERE case_context_id = :context_id"),
            {"context_id": context_id},
        )

        inserted: list[dict[str, Any]] = []
        for term in terms:
            term_id = str(uuid.uuid4())
            result = await db.execute(
                text("""
                    INSERT INTO case_defined_terms
                        (id, case_context_id, term, definition, entity_id,
                         source_pages, created_at, updated_at)
                    VALUES
                        (:id, :context_id, :term, :definition, :entity_id,
                         :source_pages, now(), now())
                    RETURNING id, term, definition, entity_id, source_pages
                """),
                {
                    "id": term_id,
                    "context_id": context_id,
                    "term": term["term"],
                    "definition": term["definition"],
                    "entity_id": term.get("entity_id"),
                    "source_pages": json.dumps(term.get("source_pages", [])),
                },
            )
            row = result.mappings().first()
            if row:
                inserted.append(dict(row))

        return inserted

    @staticmethod
    async def update_timeline(
        db: AsyncSession,
        context_id: str,
        timeline: list[dict[str, Any]],
    ) -> None:
        """Update the timeline JSONB column on the case context."""
        await db.execute(
            text("""
                UPDATE case_contexts
                SET timeline = CAST(:timeline AS jsonb),
                    updated_at = now()
                WHERE id = :context_id
            """),
            {
                "context_id": context_id,
                "timeline": json.dumps(timeline),
            },
        )

    @staticmethod
    async def create_investigation_session(
        db: AsyncSession,
        matter_id: str,
        user_id: str,
        case_context_id: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Create a new investigation session."""
        session_id = str(uuid.uuid4())
        result = await db.execute(
            text("""
                INSERT INTO investigation_sessions
                    (id, matter_id, case_context_id, user_id, title,
                     status, created_at, updated_at)
                VALUES
                    (:id, :matter_id, :case_context_id, :user_id, :title,
                     'active', now(), now())
                RETURNING id, matter_id, case_context_id, user_id, title,
                          findings, status, created_at, updated_at
            """),
            {
                "id": session_id,
                "matter_id": matter_id,
                "case_context_id": case_context_id,
                "user_id": user_id,
                "title": title,
            },
        )
        row = result.mappings().first()
        return dict(row) if row else {}
