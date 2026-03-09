"""Tier 2 relationship extraction using Instructor + Claude.

Feature-flagged via ``settings.enable_relationship_extraction``.
Only runs on chunks with 2+ entities detected by Tier 1 (GLiNER).
"""

from __future__ import annotations

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class ExtractedRelationship(BaseModel):
    """A single relationship extracted from a text passage."""

    source_entity: str
    source_type: str
    target_entity: str
    target_type: str
    relationship_type: str
    context: str = Field(description="Brief quote supporting this relationship")
    confidence: float = Field(ge=0, le=1)
    temporal: str | None = Field(default=None, description="Date or date range if mentioned")


class RelationshipList(BaseModel):
    """Container for extracted relationships."""

    relationships: list[ExtractedRelationship] = Field(default_factory=list)


class RelationshipExtractor:
    """Extract structured relationships between entities using an LLM.

    Uses the Instructor library for structured output with automatic
    validation and retry.

    Parameters
    ----------
    api_key:
        Anthropic API key.
    model:
        Model to use for extraction.
    provider:
        LLM provider ("anthropic" or "openai").
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-5-20250929",
        provider: str = "anthropic",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._provider = provider
        self._client = None  # Lazy-loaded

    def _get_client(self):
        """Lazily initialize the Instructor-patched client."""
        if self._client is None:
            import instructor

            if self._provider == "anthropic":
                import anthropic

                self._client = instructor.from_anthropic(anthropic.Anthropic(api_key=self._api_key))
            elif self._provider == "gemini":
                import google.genai

                self._client = instructor.from_gemini(
                    google.genai.Client(api_key=self._api_key),
                    mode=instructor.Mode.GEMINI_JSON,
                )
            else:
                import openai

                self._client = instructor.from_openai(openai.OpenAI(api_key=self._api_key))
        return self._client

    async def extract(
        self,
        text: str,
        entities: list[dict],
    ) -> list[ExtractedRelationship]:
        """Extract relationships between entities found in *text*.

        Parameters
        ----------
        text:
            The chunk text containing the entities.
        entities:
            List of dicts with ``name`` and ``type`` keys (from GLiNER).

        Returns
        -------
        List of validated ExtractedRelationship objects.
        """
        if len(entities) < 2:
            return []

        entity_list = "\n".join(f"- {e['name']} ({e['type']})" for e in entities)

        prompt = (
            "Extract relationships between the entities listed below from "
            "this legal document passage. Only include relationships that are "
            "explicitly stated or strongly implied in the text.\n\n"
            f"ENTITIES:\n{entity_list}\n\n"
            f"TEXT:\n{text}\n\n"
            "For each relationship, provide:\n"
            "- source_entity and source_type\n"
            "- target_entity and target_type\n"
            "- relationship_type (e.g. ASSOCIATED_WITH, EMPLOYED_BY, TRAVELED_TO)\n"
            "- context: a brief quote from the text\n"
            "- confidence: 0-1\n"
            "- temporal: date or date range if mentioned, null otherwise"
        )

        try:
            client = self._get_client()

            if self._provider == "anthropic":
                result = client.chat.completions.create(
                    model=self._model,
                    max_tokens=16384,
                    messages=[{"role": "user", "content": prompt}],
                    response_model=RelationshipList,
                )
            else:
                result = client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    response_model=RelationshipList,
                )

            logger.info(
                "relationship_extractor.success",
                relationships=len(result.relationships),
                entities=len(entities),
            )
            return list(result.relationships)

        except Exception as exc:
            logger.error(
                "relationship_extractor.failed",
                error=str(exc),
                entities=len(entities),
            )
            return []
