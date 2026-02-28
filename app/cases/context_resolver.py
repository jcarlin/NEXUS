"""Case context resolution for the query pipeline.

Maps defined terms, party aliases, and claim references to their full
definitions so the rewrite and synthesize nodes can use case-aware context.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.cases.service import CaseService


class CaseContextResolver:
    """Stateless resolver that loads case context and expands references."""

    @staticmethod
    async def get_context_for_matter(
        db: AsyncSession,
        matter_id: str,
    ) -> dict[str, Any] | None:
        """Load the full case context for a matter, if one exists."""
        return await CaseService.get_full_context(db, matter_id)

    @staticmethod
    def build_term_map(context: dict[str, Any]) -> dict[str, str]:
        """Build a lowercase term/alias -> definition/full name map.

        Sources:
        - Defined terms: "the company" -> "Acme Corp, a Delaware corporation"
        - Party aliases: "defendant a" -> "John Smith (defendant)"
        - Claim references: "claim 1", "count i" -> full claim label
        """
        term_map: dict[str, str] = {}

        # Defined terms
        for dt in context.get("defined_terms", []):
            term = dt.get("term", "")
            definition = dt.get("definition", "")
            if term and definition:
                term_map[term.lower()] = definition

        # Party aliases
        for party in context.get("parties", []):
            name = party.get("name", "")
            role = party.get("role", "")
            full_ref = f"{name} ({role})" if role else name

            # Map each alias to the full party reference
            aliases = party.get("aliases", [])
            if isinstance(aliases, list):
                for alias in aliases:
                    if alias:
                        term_map[alias.lower()] = full_ref

        # Claim references (e.g., "claim 1" -> "Fraud (Claim 1)")
        for claim in context.get("claims", []):
            claim_number = claim.get("claim_number", 0)
            claim_label = claim.get("claim_label", "")
            if claim_number and claim_label:
                term_map[f"claim {claim_number}"] = f"{claim_label} (Claim {claim_number})"
                # Roman numeral variants
                roman = _to_roman(claim_number)
                if roman:
                    term_map[f"count {roman.lower()}"] = f"{claim_label} (Count {roman})"

        return term_map

    @staticmethod
    def expand_references(query: str, term_map: dict[str, str]) -> str:
        """Expand known terms in a query by appending context.

        Does case-insensitive matching.  When a known term is found in the
        query, an expansion note is appended rather than replacing inline
        (to preserve the user's original phrasing).
        """
        if not term_map:
            return query

        expansions: list[str] = []
        query_lower = query.lower()

        for term, definition in term_map.items():
            if term in query_lower:
                expansions.append(f'"{term}" = {definition}')

        if not expansions:
            return query

        expansion_text = "; ".join(expansions)
        return f"{query}\n\n[Case context: {expansion_text}]"

    @staticmethod
    def format_context_for_prompt(context: dict[str, Any]) -> str:
        """Format case context as a text block for LLM prompts.

        Includes sections for claims, parties, and defined terms.
        """
        sections: list[str] = []

        # Claims
        claims = context.get("claims", [])
        if claims:
            lines = ["CASE CLAIMS:"]
            for claim in claims:
                num = claim.get("claim_number", "?")
                label = claim.get("claim_label", "")
                text = claim.get("claim_text", "")
                lines.append(f"  Claim {num}: {label} — {text[:200]}")
            sections.append("\n".join(lines))

        # Parties
        parties = context.get("parties", [])
        if parties:
            lines = ["CASE PARTIES:"]
            for party in parties:
                name = party.get("name", "")
                role = party.get("role", "")
                desc = party.get("description", "") or ""
                aliases = party.get("aliases", [])
                alias_str = f" (aka {', '.join(aliases)})" if aliases else ""
                lines.append(f"  {name}{alias_str} — {role}: {desc[:100]}")
            sections.append("\n".join(lines))

        # Defined terms
        terms = context.get("defined_terms", [])
        if terms:
            lines = ["DEFINED TERMS:"]
            for term in terms:
                t = term.get("term", "")
                d = term.get("definition", "")
                lines.append(f'  "{t}" = {d[:150]}')
            sections.append("\n".join(lines))

        # Timeline
        timeline = context.get("timeline", [])
        if timeline:
            lines = ["KEY TIMELINE:"]
            for event in timeline[:10]:
                date = event.get("date", "?")
                text = event.get("event_text", "")
                lines.append(f"  {date}: {text[:150]}")
            sections.append("\n".join(lines))

        return "\n\n".join(sections)


def _to_roman(n: int) -> str | None:
    """Convert an integer (1-20) to a Roman numeral string."""
    if n < 1 or n > 20:
        return None
    numerals = [
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ]
    result = ""
    for value, numeral in numerals:
        while n >= value:
            result += numeral
            n -= value
    return result
