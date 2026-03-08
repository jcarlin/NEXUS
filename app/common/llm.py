"""Unified LLM client that supports Anthropic, OpenAI, vLLM, and Ollama providers.

The key insight from the architecture doc: vLLM and Ollama expose OpenAI-compatible APIs,
so cloud-to-local migration is a config change (URL + model name), not a code change.
"""

from __future__ import annotations

import hashlib
import time
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
        elif self.provider in ("openai", "vllm", "ollama"):
            from openai import AsyncOpenAI

            base_url = None
            if self.provider == "vllm":
                base_url = settings.vllm_base_url
            elif self.provider == "ollama":
                base_url = settings.ollama_base_url

            self._client = AsyncOpenAI(
                api_key=settings.openai_api_key or "not-needed",
                base_url=base_url,
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

        logger.info("llm.init", provider=self.provider, model=self.model)

    # ------------------------------------------------------------------
    # AI audit logging (fire-and-forget)
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_prompt(messages: list[dict[str, str]]) -> str:
        """Deterministic SHA-256 hash of the prompt messages."""
        content = "".join(f"{m.get('role', '')}:{m.get('content', '')}" for m in messages)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    async def _log_ai_interaction(
        self,
        messages: list[dict[str, str]],
        *,
        call_type: str = "completion",
        latency_ms: float,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        node_name: str | None = None,
        status: str = "success",
        error_message: str | None = None,
    ) -> None:
        """Write an AI audit log entry in its own session (fire-and-forget).

        Same pattern as AuditLoggingMiddleware._write_audit_log: creates its own
        session, swallows exceptions with a warning log.
        """
        try:
            from app.dependencies import get_settings

            settings = get_settings()
            if not settings.enable_ai_audit_logging:
                return

            from sqlalchemy import text as sa_text

            from app.dependencies import get_session_factory

            ctx = structlog.contextvars.get_contextvars()
            request_id = ctx.get("request_id")
            session_id = ctx.get("session_id")

            prompt_hash = self._hash_prompt(messages)
            total_tokens = None
            if input_tokens is not None and output_tokens is not None:
                total_tokens = input_tokens + output_tokens

            factory = get_session_factory()
            async with factory() as session:
                await session.execute(
                    sa_text("""
                        INSERT INTO ai_audit_log
                            (request_id, session_id, call_type, provider, model,
                             node_name, prompt_hash, input_tokens, output_tokens,
                             total_tokens, latency_ms, status, error_message)
                        VALUES
                            (:request_id, :session_id, :call_type, :provider, :model,
                             :node_name, :prompt_hash, :input_tokens, :output_tokens,
                             :total_tokens, :latency_ms, :status, :error_message)
                    """),
                    {
                        "request_id": request_id,
                        "session_id": session_id,
                        "call_type": call_type,
                        "provider": self.provider,
                        "model": self.model,
                        "node_name": node_name,
                        "prompt_hash": prompt_hash,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": total_tokens,
                        "latency_ms": latency_ms,
                        "status": status,
                        "error_message": error_message,
                    },
                )
                await session.commit()
        except Exception:
            logger.warning("ai_audit_log.write_failed", exc_info=True)

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

        node_name = kwargs.pop("node_name", None)
        start = time.perf_counter()
        input_tokens: int | None = None
        output_tokens: int | None = None

        try:
            if self.provider == "anthropic":
                result, input_tokens, output_tokens = await self._complete_anthropic(
                    messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **kwargs,
                )
            else:
                result, input_tokens, output_tokens = await self._complete_openai(
                    messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **kwargs,
                )
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            await self._log_ai_interaction(
                messages,
                latency_ms=latency_ms,
                node_name=node_name,
                status="error",
                error_message=str(exc),
            )
            raise

        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "llm.complete",
            node=node_name,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        # --- Prometheus metrics ---
        from app.common.metrics import LLM_CALLS_TOTAL, LLM_DURATION, LLM_TOKENS_TOTAL

        LLM_CALLS_TOTAL.labels(provider=self.provider, model=self.model).inc()
        LLM_DURATION.labels(provider=self.provider, model=self.model).observe(latency_ms / 1000)
        if input_tokens is not None:
            LLM_TOKENS_TOTAL.labels(provider=self.provider, model=self.model, type="input").inc(input_tokens)
        if output_tokens is not None:
            LLM_TOKENS_TOTAL.labels(provider=self.provider, model=self.model, type="output").inc(output_tokens)

        await self._log_ai_interaction(
            messages,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            node_name=node_name,
        )
        return result

    async def _complete_anthropic(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> tuple[str, int | None, int | None]:
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
        input_tokens = getattr(response.usage, "input_tokens", None)
        output_tokens = getattr(response.usage, "output_tokens", None)
        from anthropic.types import TextBlock

        content_block = response.content[0]
        if not isinstance(content_block, TextBlock):
            raise ValueError(f"Expected TextBlock, got {type(content_block).__name__}")
        return content_block.text, input_tokens, output_tokens

    async def _complete_openai(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> tuple[str, int | None, int | None]:
        client: AsyncOpenAI = self._client  # type: ignore[assignment]
        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=kwargs.get("max_tokens", 4096),
            temperature=kwargs.get("temperature", 0.1),
        )
        choice = response.choices[0]
        input_tokens = getattr(response.usage, "prompt_tokens", None) if response.usage else None
        output_tokens = getattr(response.usage, "completion_tokens", None) if response.usage else None
        return choice.message.content or "", input_tokens, output_tokens

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

        node_name = kwargs.pop("node_name", None)
        start = time.perf_counter()

        try:
            if self.provider == "anthropic":
                async for token in self._stream_anthropic(
                    messages, max_tokens=max_tokens, temperature=temperature, **kwargs
                ):
                    yield token
            else:
                async for token in self._stream_openai(
                    messages, max_tokens=max_tokens, temperature=temperature, **kwargs
                ):
                    yield token
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            await self._log_ai_interaction(
                messages,
                call_type="stream",
                latency_ms=latency_ms,
                node_name=node_name,
                status="error",
                error_message=str(exc),
            )
            raise

        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info("llm.stream", node=node_name, latency_ms=latency_ms)

        # --- Prometheus metrics ---
        from app.common.metrics import LLM_CALLS_TOTAL, LLM_DURATION

        LLM_CALLS_TOTAL.labels(provider=self.provider, model=self.model).inc()
        LLM_DURATION.labels(provider=self.provider, model=self.model).observe(latency_ms / 1000)

        await self._log_ai_interaction(
            messages,
            call_type="stream",
            latency_ms=latency_ms,
            node_name=node_name,
        )

    async def _stream_anthropic(self, messages: list[dict[str, str]], **kwargs: Any) -> AsyncIterator[str]:
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
        client: AsyncOpenAI = self._client  # type: ignore[assignment]
        stream = await client.chat.completions.create(  # type: ignore[assignment]
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=kwargs.get("max_tokens", 4096),
            temperature=kwargs.get("temperature", 0.1),
            stream=True,
        )
        async for chunk in stream:  # type: ignore[union-attr]
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
