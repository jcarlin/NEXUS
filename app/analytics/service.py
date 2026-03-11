"""Communication analytics service (M10c).

Pre-computes sender-recipient matrices from email metadata in PostgreSQL,
exposes network centrality via Neo4j GDS, and manages org chart data.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.schemas import (
    CommunicationMatrixResponse,
    CommunicationPair,
    EntityCentrality,
    NetworkCentralityResponse,
    OrgChartEntry,
    OrgChartImportResponse,
)
from app.entities.graph_service import GraphService

logger = structlog.get_logger(__name__)


class AnalyticsService:
    """Static service methods for communication analytics.

    All methods are ``@staticmethod`` async, following the project pattern.
    """

    # ------------------------------------------------------------------
    # Communication pairs — compute from email metadata JSONB
    # ------------------------------------------------------------------

    @staticmethod
    async def compute_communication_pairs(
        db: AsyncSession,
        matter_id: str,
        limit: int = 1000,
        offset: int = 0,
    ) -> int:
        """Extract sender/recipient pairs from email document metadata and UPSERT.

        Reads the ``metadata_`` JSONB column from the ``documents`` table for
        emails in the given matter.  Extracts ``from``, ``to``, ``cc`` fields
        and upserts into ``communication_pairs``.

        Returns the number of pairs upserted.
        """
        # Fetch email documents with their metadata
        result = await db.execute(
            text(
                """
                SELECT id, metadata_
                FROM documents
                WHERE matter_id = :matter_id
                  AND document_type = 'email'
                  AND metadata_ IS NOT NULL
                  AND metadata_ != '{}'
                ORDER BY id
                LIMIT :limit OFFSET :offset
                """
            ),
            {"matter_id": matter_id, "limit": limit, "offset": offset},
        )
        rows = result.fetchall()

        upsert_count = 0
        for row in rows:
            meta = row.metadata_
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except (json.JSONDecodeError, TypeError):
                    continue
            if not isinstance(meta, dict):
                continue

            sender_name = meta.get("from_name", "") or meta.get("sender", "")
            sender_email = meta.get("from_email", "") or meta.get("from", "")
            if not sender_email:
                continue

            email_date = meta.get("date")

            # Process to/cc/bcc recipients
            for rel_type, field in [("to", "to"), ("cc", "cc"), ("bcc", "bcc")]:
                recipients = meta.get(field, "")
                if not recipients:
                    continue

                # Recipients may be a string (comma-separated) or a list
                if isinstance(recipients, str):
                    recip_list = [r.strip() for r in recipients.split(",") if r.strip()]
                elif isinstance(recipients, list):
                    recip_list = recipients
                else:
                    continue

                for recip in recip_list:
                    # Parse "Name <email>" or bare email
                    recip_name = ""
                    recip_email = recip
                    if "<" in recip and ">" in recip:
                        parts = recip.split("<")
                        recip_name = parts[0].strip().strip('"')
                        recip_email = parts[1].rstrip(">").strip()
                    elif " " not in recip and "@" in recip:
                        recip_email = recip
                    else:
                        recip_email = recip

                    if not recip_email:
                        continue

                    await db.execute(
                        text(
                            """
                            INSERT INTO communication_pairs
                                (matter_id, sender_name, sender_email,
                                 recipient_name, recipient_email,
                                 relationship_type, message_count,
                                 earliest, latest)
                            VALUES
                                (:matter_id, :sender_name, :sender_email,
                                 :recipient_name, :recipient_email,
                                 :rel_type, 1,
                                 :email_date, :email_date)
                            ON CONFLICT (matter_id, sender_email, recipient_email, relationship_type)
                            DO UPDATE SET
                                message_count = communication_pairs.message_count + 1,
                                earliest = LEAST(communication_pairs.earliest, EXCLUDED.earliest),
                                latest = GREATEST(communication_pairs.latest, EXCLUDED.latest),
                                updated_at = now()
                            """
                        ),
                        {
                            "matter_id": matter_id,
                            "sender_name": sender_name,
                            "sender_email": sender_email,
                            "recipient_name": recip_name,
                            "recipient_email": recip_email,
                            "rel_type": rel_type,
                            "email_date": email_date,
                        },
                    )
                    upsert_count += 1

        logger.info(
            "analytics.communication_pairs.computed",
            matter_id=matter_id,
            pairs_upserted=upsert_count,
        )
        return upsert_count

    # ------------------------------------------------------------------
    # Communication matrix — read pre-computed pairs
    # ------------------------------------------------------------------

    @staticmethod
    async def get_communication_matrix(
        db: AsyncSession,
        matter_id: str,
        entity_name: str | None = None,
    ) -> CommunicationMatrixResponse:
        """Read pre-computed communication pairs for a matter.

        Optionally filter to pairs involving a specific entity name.
        """
        params: dict[str, Any] = {"matter_id": matter_id}

        entity_filter = ""
        if entity_name:
            entity_filter = (
                " AND (LOWER(sender_name) = LOWER(:entity_name)"
                " OR LOWER(recipient_name) = LOWER(:entity_name)"
                " OR LOWER(sender_email) = LOWER(:entity_name)"
                " OR LOWER(recipient_email) = LOWER(:entity_name))"
            )
            params["entity_name"] = entity_name

        result = await db.execute(
            text(
                f"""
                SELECT sender_name, sender_email, recipient_name, recipient_email,
                       relationship_type, message_count, earliest, latest
                FROM communication_pairs
                WHERE matter_id = :matter_id{entity_filter}
                ORDER BY message_count DESC
                """
            ),
            params,
        )
        rows = result.fetchall()

        pairs = [
            CommunicationPair(
                sender_name=r.sender_name,
                sender_email=r.sender_email,
                recipient_name=r.recipient_name,
                recipient_email=r.recipient_email,
                relationship_type=r.relationship_type,
                message_count=r.message_count,
                earliest=r.earliest,
                latest=r.latest,
            )
            for r in rows
        ]

        senders = {p.sender_email or p.sender_name for p in pairs}
        recipients = {p.recipient_email or p.recipient_name for p in pairs}
        total = sum(p.message_count for p in pairs)

        return CommunicationMatrixResponse(
            matter_id=UUID(matter_id),
            pairs=pairs,
            total_messages=total,
            unique_senders=len(senders),
            unique_recipients=len(recipients),
        )

    # ------------------------------------------------------------------
    # Network centrality (delegates to GraphService)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_network_centrality(
        gs: GraphService,
        matter_id: str,
        metric: str,
    ) -> NetworkCentralityResponse:
        """Compute network centrality via Neo4j GDS and return ranked entities."""
        from app.analytics.schemas import CentralityMetric

        results = await gs.compute_centrality(matter_id, metric)

        entities = [
            EntityCentrality(
                name=r["name"],
                entity_type=r.get("type"),
                score=r["score"],
                rank=i + 1,
            )
            for i, r in enumerate(results)
        ]

        return NetworkCentralityResponse(
            matter_id=UUID(matter_id),
            metric=CentralityMetric(metric),
            entities=entities,
            total_entities=len(entities),
        )

    # ------------------------------------------------------------------
    # Org chart import
    # ------------------------------------------------------------------

    @staticmethod
    async def import_org_chart(
        db: AsyncSession,
        matter_id: str,
        entries: list[OrgChartEntry],
    ) -> OrgChartImportResponse:
        """Insert org chart entries into the database."""
        imported = 0
        for entry in entries:
            await db.execute(
                text(
                    """
                    INSERT INTO org_chart_entries
                        (matter_id, person_name, person_email,
                         reports_to_name, reports_to_email,
                         title, department, source, confidence)
                    VALUES
                        (:matter_id, :person_name, :person_email,
                         :reports_to_name, :reports_to_email,
                         :title, :department, :source, :confidence)
                    """
                ),
                {
                    "matter_id": matter_id,
                    "person_name": entry.person_name,
                    "person_email": entry.person_email,
                    "reports_to_name": entry.reports_to_name,
                    "reports_to_email": entry.reports_to_email,
                    "title": entry.title,
                    "department": entry.department,
                    "source": entry.source,
                    "confidence": entry.confidence,
                },
            )
            imported += 1

        logger.info(
            "analytics.org_chart.imported",
            matter_id=matter_id,
            count=imported,
        )
        return OrgChartImportResponse(
            matter_id=UUID(matter_id),
            imported_count=imported,
            total_entries=len(entries),
        )

    # ------------------------------------------------------------------
    # Org hierarchy inference
    # ------------------------------------------------------------------

    @staticmethod
    async def infer_org_hierarchy(
        db: AsyncSession,
        matter_id: str,
    ) -> list[OrgChartEntry]:
        """Infer REPORTS_TO relationships from asymmetric communication patterns.

        Heuristic: if A sends significantly more messages TO B than B sends
        to A, B may be A's superior.  Returns entries with source='inferred'
        and confidence scores.
        """
        result = await db.execute(
            text(
                """
                WITH pair_counts AS (
                    SELECT sender_email, sender_name,
                           recipient_email, recipient_name,
                           SUM(message_count) AS sent_count
                    FROM communication_pairs
                    WHERE matter_id = :matter_id
                      AND relationship_type = 'to'
                      AND sender_email IS NOT NULL
                      AND recipient_email IS NOT NULL
                    GROUP BY sender_email, sender_name,
                             recipient_email, recipient_name
                ),
                directional_pairs AS (
                    SELECT a.sender_name AS subordinate_name,
                           a.sender_email AS subordinate_email,
                           a.recipient_name AS superior_name,
                           a.recipient_email AS superior_email,
                           a.sent_count AS a_to_b,
                           COALESCE(b.sent_count, 0) AS b_to_a
                    FROM pair_counts a
                    LEFT JOIN pair_counts b
                        ON a.sender_email = b.recipient_email
                       AND a.recipient_email = b.sender_email
                    WHERE a.sent_count > COALESCE(b.sent_count, 0) * 2
                      AND a.sent_count >= 3
                )
                SELECT subordinate_name, subordinate_email,
                       superior_name, superior_email,
                       a_to_b, b_to_a,
                       CASE WHEN b_to_a = 0 THEN 0.9
                            ELSE ROUND((a_to_b::numeric - b_to_a) / (a_to_b + b_to_a), 2)
                       END AS confidence
                FROM directional_pairs
                ORDER BY confidence DESC
                """
            ),
            {"matter_id": matter_id},
        )
        rows = result.fetchall()

        entries = [
            OrgChartEntry(
                person_name=r.subordinate_name,
                person_email=r.subordinate_email,
                reports_to_name=r.superior_name,
                reports_to_email=r.superior_email,
                source="inferred",
                confidence=float(r.confidence),
            )
            for r in rows
        ]

        logger.info(
            "analytics.org_hierarchy.inferred",
            matter_id=matter_id,
            inferred_count=len(entries),
        )
        return entries
