"""Sentiment scoring and hot document detection using Instructor + LLM.

Mirrors the Instructor pattern from ``app/entities/relationship_extractor.py``.
"""

from __future__ import annotations

import asyncio

import structlog

from app.analysis.prompts import SENTIMENT_SCORING_PROMPT
from app.analysis.schemas import DocumentSentimentResult

logger = structlog.get_logger(__name__)

# Maximum characters to send to the LLM for scoring.
_MAX_TEXT_LENGTH = 8000


class SentimentScorer:
    """Score documents across sentiment dimensions and hot-doc signals.

    Uses Instructor for structured LLM output with automatic validation.

    Parameters
    ----------
    api_key:
        API key for the configured LLM provider.
    model:
        Model to use for scoring.
    provider:
        LLM provider ("anthropic" or "openai").
    """

    def __init__(
        self,
        api_key: str,
        model: str = "",
        provider: str = "anthropic",
    ) -> None:
        from app.config import Settings

        settings = Settings()
        self._api_key = api_key
        self._model = model or settings.llm_model
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

                self._client = instructor.from_genai(
                    google.genai.Client(api_key=self._api_key),
                    mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS,
                )
            else:
                import openai

                self._client = instructor.from_openai(openai.OpenAI(api_key=self._api_key))
        return self._client

    async def score_document(self, text: str) -> DocumentSentimentResult:
        """Score a document's sentiment dimensions and hot-doc signals.

        Parameters
        ----------
        text:
            Document text to analyze. Truncated to first 8000 characters.

        Returns
        -------
        Validated DocumentSentimentResult with all dimension scores.
        """
        truncated = text[:_MAX_TEXT_LENGTH]
        prompt = SENTIMENT_SCORING_PROMPT.format(text=truncated)

        client = self._get_client()

        if self._provider == "anthropic":
            result = await asyncio.to_thread(
                client.chat.completions.create,
                model=self._model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
                response_model=DocumentSentimentResult,
            )
        else:
            result = await asyncio.to_thread(
                client.chat.completions.create,
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                response_model=DocumentSentimentResult,
            )

        logger.info(
            "sentiment_scorer.success",
            hot_doc_score=result.hot_doc_score,
            text_length=len(truncated),
        )
        return result
