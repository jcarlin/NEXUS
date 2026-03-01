"""Neo4j schema management for the M11 enhanced knowledge graph.

Provides:
- ``ENTITY_TYPE_TO_LABEL`` — mapping from GLiNER entity types to Neo4j labels
- ``ensure_schema()``     — idempotent constraint/index creation
- ``migrate_existing_entities()`` — one-time typed label + matter_id propagation
- ``parse_email_address()`` / ``parse_recipient_list()`` — email header utilities
"""

from __future__ import annotations

import re

import structlog
from neo4j import AsyncDriver

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# GLiNER type → Neo4j secondary label mapping
# ---------------------------------------------------------------------------
# All nodes keep the primary `:Entity` label for backward compat.
# The secondary label enables type-specific Cypher queries like
# ``MATCH (p:Person)`` alongside ``MATCH (e:Entity {type: "person"})``.

ENTITY_TYPE_TO_LABEL: dict[str, str] = {
    "person": "Person",
    "organization": "Organization",
    "court": "Organization",  # Courts are a subtype of organization
    "location": "Location",
    "date": "Event",
    "event": "Event",
    "money": "Financial",
    "financial": "Financial",
    "legal_reference": "LegalReference",
    "case_number": "LegalReference",
    "law": "LegalReference",
    "statute": "LegalReference",
    "regulation": "LegalReference",
    "phone_number": "ContactInfo",
    "email": "ContactInfo",
    "address": "ContactInfo",
    "url": "ContactInfo",
}

# Valid labels that get constraints/indexes
NODE_LABELS: list[str] = [
    "Entity",
    "Person",
    "Organization",
    "Location",
    "Event",
    "Financial",
    "LegalReference",
    "ContactInfo",
    "Email",
    "Topic",
    "Document",
    "Chunk",
]

# Valid temporal relationship types
TEMPORAL_RELATIONSHIP_TYPES: set[str] = {
    "MANAGES",
    "HAS_ROLE",
    "MEMBER_OF",
    "BOARD_MEMBER",
    "REPORTS_TO",
}


def get_neo4j_label(entity_type: str) -> str | None:
    """Return the Neo4j secondary label for a GLiNER entity type, or None."""
    return ENTITY_TYPE_TO_LABEL.get(entity_type.lower())


# ---------------------------------------------------------------------------
# Schema initialisation (idempotent)
# ---------------------------------------------------------------------------


async def ensure_schema(driver: AsyncDriver) -> None:
    """Create all constraints and indexes for the M11 graph schema.

    Safe to call on every startup — all statements use ``IF NOT EXISTS``.
    """
    async with driver.session() as session:
        # Uniqueness constraints
        constraints = [
            "CREATE CONSTRAINT entity_name_type IF NOT EXISTS FOR (e:Entity) REQUIRE (e.name, e.type) IS UNIQUE",
            "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT email_id IF NOT EXISTS FOR (em:Email) REQUIRE em.id IS UNIQUE",
            "CREATE CONSTRAINT topic_name_matter IF NOT EXISTS FOR (t:Topic) REQUIRE (t.name, t.matter_id) IS UNIQUE",
        ]
        for stmt in constraints:
            await session.run(stmt)

        # Indexes for matter-scoped lookups
        indexes = [
            "CREATE INDEX entity_matter IF NOT EXISTS FOR (e:Entity) ON (e.matter_id)",
            "CREATE INDEX document_matter IF NOT EXISTS FOR (d:Document) ON (d.matter_id)",
            "CREATE INDEX email_matter IF NOT EXISTS FOR (em:Email) ON (em.matter_id)",
            "CREATE INDEX topic_matter IF NOT EXISTS FOR (t:Topic) ON (t.matter_id)",
            "CREATE INDEX person_name IF NOT EXISTS FOR (p:Person) ON (p.name)",
            "CREATE INDEX org_name IF NOT EXISTS FOR (o:Organization) ON (o.name)",
            "CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.type)",
        ]
        for stmt in indexes:
            await session.run(stmt)

    logger.info("graph.schema.ensured", constraints=len(constraints), indexes=len(indexes))


# ---------------------------------------------------------------------------
# One-time migration for existing entities
# ---------------------------------------------------------------------------


async def migrate_existing_entities(driver: AsyncDriver) -> int:
    """Add typed secondary labels and propagate ``matter_id`` to existing Entity nodes.

    Idempotent: re-running is safe (labels are additive, matter_id SET is a no-op
    when already present).

    Returns the number of entities updated.
    """
    updated = 0
    async with driver.session() as session:
        # Step 1: Add typed secondary labels
        for gliner_type, label in ENTITY_TYPE_TO_LABEL.items():
            result = await session.run(
                f"""
                MATCH (e:Entity)
                WHERE e.type = $type AND NOT e:{label}
                SET e:{label}
                RETURN count(e) AS cnt
                """,
                {"type": gliner_type},
            )
            record = await result.single()
            if record:
                updated += record["cnt"]

        # Step 2: Propagate matter_id from Documents via MENTIONED_IN
        result = await session.run(
            """
            MATCH (e:Entity)-[:MENTIONED_IN]->(d:Document)
            WHERE e.matter_id IS NULL AND d.matter_id IS NOT NULL
            SET e.matter_id = d.matter_id
            RETURN count(e) AS cnt
            """
        )
        record = await result.single()
        if record:
            updated += record["cnt"]

    logger.info("graph.migration.complete", entities_updated=updated)
    return updated


# ---------------------------------------------------------------------------
# Email address parsing utilities
# ---------------------------------------------------------------------------

# RFC 5322 simplified: captures "Display Name <addr>" or bare "addr"
_EMAIL_RE = re.compile(
    r"""
    (?:                         # Optional display name
        "?([^"<]*?)"?           # Group 1: display name (unquoted or quoted)
        \s*<([^>]+)>            # Group 2: angle-bracketed address
    )
    |
    ([\w.+-]+@[\w.-]+\.\w+)     # Group 3: bare email address
    """,
    re.VERBOSE,
)


def parse_email_address(raw: str) -> tuple[str, str]:
    """Parse a single email address into ``(display_name, email)``.

    Handles formats:
    - ``"John Doe" <john@example.com>``
    - ``John Doe <john@example.com>``
    - ``john@example.com``

    Returns ``("", "")`` if parsing fails.
    """
    raw = raw.strip()
    if not raw:
        return ("", "")

    m = _EMAIL_RE.search(raw)
    if not m:
        return ("", "")

    if m.group(3):
        # Bare address
        return ("", m.group(3).strip())

    display = (m.group(1) or "").strip()
    addr = (m.group(2) or "").strip()
    return (display, addr)


def parse_recipient_list(raw: str) -> list[tuple[str, str]]:
    """Parse a comma/semicolon-separated list of email addresses.

    Returns a list of ``(display_name, email)`` tuples.
    """
    if not raw:
        return []

    # Split on comma or semicolon
    parts = re.split(r"[;,]", raw)
    results: list[tuple[str, str]] = []
    for part in parts:
        name, addr = parse_email_address(part)
        if addr:
            results.append((name, addr))
    return results
