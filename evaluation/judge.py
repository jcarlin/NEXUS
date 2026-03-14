"""LLM-as-judge quality scorer for QA evaluation.

Uses Instructor for structured extraction of 5-dimension quality scores.
Reads provider config from .env, supports fallback across providers.
"""

from __future__ import annotations

import os
from pathlib import Path

import structlog

from evaluation.prompts import (
    JUDGE_SYSTEM_PROMPT,
    JUDGE_USER_PROMPT,
)
from evaluation.schemas import JudgeScore

logger = structlog.get_logger(__name__)


def _compute_composite(
    relevance: float,
    completeness: float,
    accuracy: float,
    citation_support: float,
    conciseness: float,
) -> float:
    """Weighted average: accuracy and citation_support weighted higher for legal QA."""
    weights = {
        "relevance": 0.20,
        "completeness": 0.15,
        "accuracy": 0.25,
        "citation_support": 0.25,
        "conciseness": 0.15,
    }
    return round(
        relevance * weights["relevance"]
        + completeness * weights["completeness"]
        + accuracy * weights["accuracy"]
        + citation_support * weights["citation_support"]
        + conciseness * weights["conciseness"],
        2,
    )


def score_empty_response() -> JudgeScore:
    """Return a zero-score for empty or error responses."""
    return JudgeScore(
        relevance=0.0,
        completeness=0.0,
        accuracy=0.0,
        citation_support=0.0,
        conciseness=0.0,
        composite=0.0,
        rationale="Empty or error response — no content to evaluate.",
    )


# ---------------------------------------------------------------------------
# Provider auto-detection from .env
# ---------------------------------------------------------------------------

# Provider preference order for the judge (quality-first)
_PROVIDER_PRIORITY = [
    ("anthropic", "ANTHROPIC_API_KEY", "claude-sonnet-4-20250514"),
    ("openai", "OPENAI_API_KEY", "gpt-4o"),
    ("gemini", "GEMINI_API_KEY", "gemini-2.0-flash"),
]


def _load_dotenv_keys() -> dict[str, str]:
    """Read .env file and extract all API keys (including commented-out ones)."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    keys: dict[str, str] = {}
    if not env_path.exists():
        return keys
    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        # Skip empty lines
        if not stripped:
            continue
        # Handle commented-out keys — strip leading #
        if stripped.startswith("#"):
            stripped = stripped.lstrip("# ")
        if "=" in stripped and not stripped.startswith("["):
            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.strip()
            if key and value and key.endswith("_API_KEY"):
                keys[key] = value
    return keys


def detect_judge_provider() -> tuple[str, str, str]:
    """Detect the best available LLM provider for judge scoring.

    Returns (provider, api_key, model).
    Checks env vars first, then reads .env file (including commented-out keys).
    """
    dotenv_keys = _load_dotenv_keys()

    for provider, key_name, default_model in _PROVIDER_PRIORITY:
        # Check environment first
        api_key = os.environ.get(key_name) or dotenv_keys.get(key_name)
        if api_key:
            logger.info("judge.provider_detected", provider=provider, model=default_model)
            return provider, api_key, default_model

    raise RuntimeError(
        "No LLM API key found for judge scoring. " "Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY in .env"
    )


class JudgeScorer:
    """LLM-based answer quality scorer using Instructor structured extraction."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        provider: str | None = None,
    ) -> None:
        if provider and api_key:
            self.provider = provider
            self.model = model or "claude-sonnet-4-20250514"
            self._api_key = api_key
        else:
            self.provider, self._api_key, self.model = detect_judge_provider()
            if model:
                self.model = model

        self._client = _build_instructor_client(
            provider=self.provider,
            api_key=self._api_key,
            base_url=base_url,
            model=self.model,
        )
        logger.info("judge.init", provider=self.provider, model=self.model)

    @property
    def provider_info(self) -> dict[str, str]:
        """Return provider metadata for inclusion in reports."""
        return {
            "judge_provider": self.provider,
            "judge_model": self.model,
        }

    async def score_answer(
        self,
        question: str,
        answer: str,
        source_excerpts: list[str] | None = None,
    ) -> JudgeScore:
        """Score an answer on 5 quality dimensions.

        Returns JudgeScore with composite. Returns score_empty_response() for
        empty answers.
        """
        if not answer or not answer.strip():
            return score_empty_response()

        sources_text = "\n---\n".join(source_excerpts or ["(no sources provided)"])
        user_msg = JUDGE_USER_PROMPT.format(
            question=question,
            answer=answer,
            sources=sources_text,
        )

        try:
            result = await self._call_llm(user_msg)
            return result
        except Exception:
            logger.warning("judge.score_failed", question=question[:80], exc_info=True)
            return JudgeScore(
                relevance=0.0,
                completeness=0.0,
                accuracy=0.0,
                citation_support=0.0,
                conciseness=0.0,
                composite=0.0,
                rationale="Judge scoring failed due to LLM error.",
            )

    async def _call_llm(self, user_msg: str) -> JudgeScore:
        """Call the LLM via Instructor for structured extraction."""
        if self.provider == "anthropic":
            raw = await self._client.messages.create(
                model=self.model,
                max_tokens=512,
                messages=[{"role": "user", "content": user_msg}],
                system=JUDGE_SYSTEM_PROMPT,
                response_model=_JudgeExtraction,
            )
        elif self.provider == "gemini":
            raw = await self._call_gemini(user_msg)
        else:
            raw = await self._client.chat.completions.create(
                model=self.model,
                max_tokens=512,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                response_model=_JudgeExtraction,
            )

        composite = _compute_composite(
            raw.relevance,
            raw.completeness,
            raw.accuracy,
            raw.citation_support,
            raw.conciseness,
        )
        return JudgeScore(
            relevance=raw.relevance,
            completeness=raw.completeness,
            accuracy=raw.accuracy,
            citation_support=raw.citation_support,
            conciseness=raw.conciseness,
            composite=composite,
            rationale=raw.rationale,
        )

    async def _call_gemini(self, user_msg: str) -> _JudgeExtraction:
        """Call Gemini via google-genai and parse structured output."""
        import json as json_mod

        from google import genai

        client = genai.Client(api_key=self._api_key)
        response = client.models.generate_content(
            model=self.model,
            contents=f"{JUDGE_SYSTEM_PROMPT}\n\n{user_msg}\n\nRespond with JSON matching this schema: "
            '{"relevance": float, "completeness": float, "accuracy": float, '
            '"citation_support": float, "conciseness": float, "rationale": string}. '
            "All scores 1.0-5.0.",
        )
        # Parse the JSON from the response
        text = response.text
        # Try to find JSON in the response
        if "{" in text:
            json_str = text[text.index("{") : text.rindex("}") + 1]
            data = json_mod.loads(json_str)
            return _JudgeExtraction(**data)
        raise ValueError(f"Could not parse JSON from Gemini response: {text[:200]}")


# ---------------------------------------------------------------------------
# Instructor integration
# ---------------------------------------------------------------------------

from pydantic import BaseModel, Field  # noqa: E402


class _JudgeExtraction(BaseModel):
    """Instructor extraction model for the judge LLM response."""

    relevance: float = Field(..., ge=1.0, le=5.0)
    completeness: float = Field(..., ge=1.0, le=5.0)
    accuracy: float = Field(..., ge=1.0, le=5.0)
    citation_support: float = Field(..., ge=1.0, le=5.0)
    conciseness: float = Field(..., ge=1.0, le=5.0)
    rationale: str = Field(default="", description="Brief rationale for the scores")


def _build_instructor_client(
    *,
    provider: str,
    api_key: str | None,
    base_url: str | None,
    model: str,
):
    """Build an Instructor-patched client for the specified provider."""
    if provider == "gemini":
        # Gemini uses direct google-genai calls, no instructor wrapper
        return None

    import instructor

    if provider == "anthropic":
        from anthropic import AsyncAnthropic

        raw = AsyncAnthropic(api_key=api_key)
        return instructor.from_anthropic(raw)
    else:
        from openai import AsyncOpenAI

        raw = AsyncOpenAI(api_key=api_key or "not-needed", base_url=base_url)
        return instructor.from_openai(raw)
