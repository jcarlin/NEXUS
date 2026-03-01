"""Completeness analysis for detecting context gaps in documents.

Mirrors the Instructor pattern from ``app/entities/relationship_extractor.py``.
"""

from __future__ import annotations

import structlog

from app.analysis.prompts import COMPLETENESS_ANALYSIS_PROMPT
from app.analysis.schemas import CompletenessResult

logger = structlog.get_logger(__name__)


class CompletenessAnalyzer:
    """Detect context gaps and missing information in documents.

    Uses Instructor for structured LLM output with automatic validation.

    Parameters
    ----------
    api_key:
        API key for the configured LLM provider.
    model:
        Model to use for analysis.
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
            else:
                import openai

                self._client = instructor.from_openai(openai.OpenAI(api_key=self._api_key))
        return self._client

    async def analyze(
        self,
        text: str,
        thread_context: str = "",
    ) -> CompletenessResult:
        """Analyze a document for context gaps and missing information.

        Parameters
        ----------
        text:
            Document text to analyze.
        thread_context:
            Optional surrounding messages for email threads.

        Returns
        -------
        Validated CompletenessResult with gap detections.
        """
        prompt = COMPLETENESS_ANALYSIS_PROMPT.format(
            text=text,
            thread_context=thread_context or "(No thread context available)",
        )

        client = self._get_client()

        if self._provider == "anthropic":
            result = client.chat.completions.create(
                model=self._model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
                response_model=CompletenessResult,
            )
        else:
            result = client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                response_model=CompletenessResult,
            )

        logger.info(
            "completeness_analyzer.success",
            context_gap_score=result.context_gap_score,
            gap_count=len(result.gaps),
        )
        return result
