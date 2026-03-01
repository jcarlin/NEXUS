"""Deterministic fake LLM client for E2E tests.

Pattern-matches on prompt content to return canned responses that exercise
the v1 query graph nodes (classify, rewrite, synthesize, etc.) without
calling any real LLM API.
"""

from __future__ import annotations

from collections.abc import AsyncIterator


class FakeLLMClient:
    """Drop-in replacement for ``LLMClient`` with deterministic responses."""

    provider = "fake"
    model = "fake-e2e"

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        **kwargs,
    ) -> str:
        prompt = " ".join(m.get("content", "") for m in messages).lower()

        if "classify" in prompt:
            return "factual"
        if "rewrite" in prompt:
            # Echo back the user's query as the rewritten version
            user_msg = messages[-1].get("content", "")
            return user_msg
        if "follow" in prompt:
            return "What other documents mention this?\nAre there related entities?"
        if "relevance" in prompt or "relevant" in prompt:
            return "relevant"
        if "synthesize" in prompt or "answer" in prompt or "respond" in prompt:
            return (
                "Based on the evidence, the analysis shows key findings regarding "
                "the contractual obligations between the parties. The documents indicate "
                "that Smith & Associates entered into a binding agreement with Acme Corporation "
                "on January 15, 2024. [Source: sample_legal_doc.txt, page 1]"
            )
        return "Test response based on provided context."

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        **kwargs,
    ) -> AsyncIterator[str]:
        response = await self.complete(messages, max_tokens=max_tokens, temperature=temperature, **kwargs)
        for word in response.split():
            yield word + " "

    async def _log_ai_interaction(self, *args, **kwargs) -> None:
        """No-op: skip AI audit logging in E2E tests."""
