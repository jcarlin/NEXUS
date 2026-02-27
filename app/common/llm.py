"""Unified LLM client that supports Anthropic, OpenAI, and vLLM providers.

The key insight from the architecture doc: vLLM exposes an OpenAI-compatible API,
so cloud-to-local migration is a config change (URL + model name), not a code change.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic
    from openai import AsyncOpenAI

    from app.config import Settings

logger = structlog.get_logger(__name__)


class LLMClient:
    """Swap providers via config, not code."""

    def __init__(self, settings: Settings) -> None:
        self.provider = settings.llm_provider
        self.model = settings.llm_model
        self._client: AsyncAnthropic | AsyncOpenAI

        if self.provider == "anthropic":
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        elif self.provider in ("openai", "vllm"):
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=settings.openai_api_key or "not-needed",
                base_url=settings.vllm_base_url if self.provider == "vllm" else None,
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

        logger.info("llm.init", provider=self.provider, model=self.model)

    # ------------------------------------------------------------------
    # Completion (non-streaming)
    # ------------------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=30), reraise=True)
    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        **kwargs: Any,
    ) -> str:
        """Send *messages* and return the full response text."""
        logger.debug("llm.complete.start", provider=self.provider, model=self.model, message_count=len(messages))

        if self.provider == "anthropic":
            return await self._complete_anthropic(messages, max_tokens=max_tokens, temperature=temperature, **kwargs)
        return await self._complete_openai(messages, max_tokens=max_tokens, temperature=temperature, **kwargs)

    async def _complete_anthropic(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        from anthropic import AsyncAnthropic

        client: AsyncAnthropic = self._client  # type: ignore[assignment]

        # Anthropic requires a separate system param; extract it if present.
        system_text = ""
        chat_messages: list[dict[str, str]] = []
        for msg in messages:
            if msg["role"] == "system":
                system_text = msg["content"]
            else:
                chat_messages.append(msg)

        response = await client.messages.create(
            model=self.model,
            max_tokens=kwargs.get("max_tokens", 4096),
            temperature=kwargs.get("temperature", 0.1),
            system=system_text or "You are a helpful assistant.",
            messages=chat_messages,  # type: ignore[arg-type]
        )
        return response.content[0].text

    async def _complete_openai(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        from openai import AsyncOpenAI

        client: AsyncOpenAI = self._client  # type: ignore[assignment]
        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=kwargs.get("max_tokens", 4096),
            temperature=kwargs.get("temperature", 0.1),
        )
        choice = response.choices[0]
        return choice.message.content or ""

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=30), reraise=True)
    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Yield response tokens one-at-a-time for SSE streaming."""
        logger.debug("llm.stream.start", provider=self.provider, model=self.model)

        if self.provider == "anthropic":
            async for token in self._stream_anthropic(messages, max_tokens=max_tokens, temperature=temperature, **kwargs):
                yield token
        else:
            async for token in self._stream_openai(messages, max_tokens=max_tokens, temperature=temperature, **kwargs):
                yield token

    async def _stream_anthropic(self, messages: list[dict[str, str]], **kwargs: Any) -> AsyncIterator[str]:
        from anthropic import AsyncAnthropic

        client: AsyncAnthropic = self._client  # type: ignore[assignment]

        system_text = ""
        chat_messages: list[dict[str, str]] = []
        for msg in messages:
            if msg["role"] == "system":
                system_text = msg["content"]
            else:
                chat_messages.append(msg)

        async with client.messages.stream(
            model=self.model,
            max_tokens=kwargs.get("max_tokens", 4096),
            temperature=kwargs.get("temperature", 0.1),
            system=system_text or "You are a helpful assistant.",
            messages=chat_messages,  # type: ignore[arg-type]
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def _stream_openai(self, messages: list[dict[str, str]], **kwargs: Any) -> AsyncIterator[str]:
        from openai import AsyncOpenAI

        client: AsyncOpenAI = self._client  # type: ignore[assignment]
        stream = await client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=kwargs.get("max_tokens", 4096),
            temperature=kwargs.get("temperature", 0.1),
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
