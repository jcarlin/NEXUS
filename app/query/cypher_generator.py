"""Text-to-Cypher generation with safety validation.

Generates read-only Cypher queries from natural language questions,
validates them for safety (no writes, matter-scoped, LIMIT enforced),
and formats results for the investigation agent.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

import structlog
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.common.llm import LLMClient

logger = structlog.get_logger(__name__)

# Write operations that must be rejected
_WRITE_OPERATIONS = re.compile(
    r"\b(CREATE|SET|MERGE|DELETE|REMOVE|DROP|DETACH|CALL\s+\{)\b",
    re.IGNORECASE,
)

# Node types and relationships in the NEXUS graph schema
NEO4J_SCHEMA_DESCRIPTION = """\
Node types:
- :Entity (name, type, matter_id) — people, organizations, locations, dates
- :Document (doc_id, filename, matter_id, document_type) — ingested documents
- :Chunk (chunk_id, doc_id, matter_id) — document chunks
- :Email (message_id, subject, sender, recipients, date) — email nodes

Relationship types:
- (Entity)-[:MENTIONED_IN]->(Document) — entity appears in document
- (Entity)-[:MENTIONED_IN]->(Chunk) — entity appears in chunk
- (Entity)-[:RELATED_TO {type}]->(Entity) — extracted relationships
- (Entity)-[:SENT]->(Email) — entity sent email
- (Entity)-[:RECEIVED]->(Email) — entity received email
- (Email)-[:BELONGS_TO]->(Document) — email linked to document
- (Entity)-[:ALIAS_OF]->(Entity) — alias resolution

All data is matter-scoped. Always filter by matter_id = $matter_id."""

TEXT_TO_CYPHER_PROMPT = """\
You are a Cypher query generator for a legal investigation knowledge graph.

{schema}

Generate a READ-ONLY Cypher query to answer the following question.

Rules:
1. ALWAYS include WHERE ... matter_id = $matter_id to scope to the current matter
2. ALWAYS include a LIMIT clause (max 50 results)
3. NEVER use write operations (CREATE, SET, MERGE, DELETE, REMOVE, DROP)
4. Use parameterized queries with $matter_id (it will be injected)
5. Return meaningful properties, not just node references

Example queries:
- "Who communicated with John?" →
  MATCH (e1:Entity {{name: 'John'}})-[:SENT|RECEIVED]->(email:Email)<-[:SENT|RECEIVED]-(e2:Entity)
  WHERE e1.matter_id = $matter_id
  RETURN DISTINCT e2.name AS person, count(email) AS email_count
  ORDER BY email_count DESC LIMIT 20

- "Show all entities connected to Acme Corp" →
  MATCH (e1:Entity {{name: 'Acme Corp'}})-[r]-(e2:Entity)
  WHERE e1.matter_id = $matter_id
  RETURN e2.name AS entity, e2.type AS type, type(r) AS relationship
  LIMIT 50

Question: {question}

Respond as JSON:
{{
  "cypher": "MATCH ...",
  "params": {{}},
  "explanation": "This query ..."
}}"""


class CypherQuery(BaseModel):
    """Generated Cypher query with parameters and explanation."""

    cypher: str = Field(..., description="The Cypher query string")
    params: dict[str, Any] = Field(default_factory=dict, description="Query parameters")
    explanation: str = Field("", description="Human-readable explanation of the query")


async def generate_cypher(
    question: str,
    matter_id: str,
    llm: LLMClient,
) -> CypherQuery:
    """Generate a Cypher query from a natural language question.

    Args:
        question: The user's natural language question.
        matter_id: Current matter scope (injected into params).
        llm: LLM client for generation.

    Returns:
        CypherQuery with the generated query, params, and explanation.
    """
    prompt = TEXT_TO_CYPHER_PROMPT.format(
        schema=NEO4J_SCHEMA_DESCRIPTION,
        question=question,
    )

    raw = await llm.complete(
        [{"role": "user", "content": prompt}],
        max_tokens=800,
        temperature=0.0,
        node_name="text_to_cypher",
    )

    result = _parse_cypher_response(raw)

    # Always inject matter_id into params
    result.params["matter_id"] = matter_id

    logger.info(
        "cypher_generator.generated",
        cypher=result.cypher[:200],
        question=question[:100],
    )

    return result


def validate_cypher_safety(cypher: str) -> tuple[bool, str]:
    """Validate a Cypher query for safety before execution.

    Returns:
        Tuple of (is_safe, reason). If is_safe is False, reason explains why.
    """
    # Reject write operations
    match = _WRITE_OPERATIONS.search(cypher)
    if match:
        return False, f"Write operation detected: {match.group()}"

    # Require matter_id parameter reference
    if "$matter_id" not in cypher and "matter_id" not in cypher:
        return False, "Query does not reference matter_id — all queries must be matter-scoped"

    # Enforce LIMIT clause (inject if missing)
    if not re.search(r"\bLIMIT\b", cypher, re.IGNORECASE):
        return False, "Query missing LIMIT clause"

    return True, ""


def ensure_limit(cypher: str, max_limit: int = 50) -> str:
    """Inject or cap the LIMIT clause in a Cypher query."""
    limit_match = re.search(r"\bLIMIT\s+(\d+)", cypher, re.IGNORECASE)
    if limit_match:
        current = int(limit_match.group(1))
        if current > max_limit:
            cypher = cypher[: limit_match.start(1)] + str(max_limit) + cypher[limit_match.end(1) :]
    else:
        cypher = cypher.rstrip().rstrip(";") + f" LIMIT {max_limit}"
    return cypher


def _parse_cypher_response(raw: str) -> CypherQuery:
    """Best-effort parse a CypherQuery from LLM output."""
    # Try direct JSON parse
    try:
        data = json.loads(raw.strip())
        return CypherQuery(**data)
    except Exception:
        pass

    # Try finding JSON object in response
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(raw[start : end + 1])
            return CypherQuery(**data)
        except Exception:
            pass

    # Last resort: treat entire response as Cypher
    return CypherQuery(cypher=raw.strip(), explanation="Parsed from raw response")
