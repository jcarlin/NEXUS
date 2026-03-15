"""Protocol definitions for core infrastructure abstractions.

These Protocols document the expected interface of infrastructure clients
(LLM, vector store, object storage, graph database) without requiring
explicit inheritance.  Existing concrete implementations
(:class:`~app.common.llm.LLMClient`, :class:`~app.common.vector_store.VectorStoreClient`,
:class:`~app.common.storage.StorageClient`, :class:`~app.entities.graph_service.GraphService`)
already satisfy these protocols via structural subtyping.

Use these Protocols in type annotations when a function only needs a subset
of the full client interface (e.g. a service that only calls ``complete``
doesn't need to know about streaming).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal interface for LLM completion and streaming."""

    provider: str
    model: str

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        **kwargs: Any,
    ) -> str: ...

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        **kwargs: Any,
    ) -> AsyncIterator[str]: ...


# ---------------------------------------------------------------------------
# Vector store
# ---------------------------------------------------------------------------


@runtime_checkable
class VectorStore(Protocol):
    """Minimal interface for vector search and indexing."""

    async def ensure_collections(self) -> None: ...

    async def upsert_chunks(
        self,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
        *,
        matter_id: str,
        **kwargs: Any,
    ) -> int: ...

    async def search(
        self,
        query_embedding: list[float],
        *,
        matter_id: str,
        limit: int = 10,
        **kwargs: Any,
    ) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# Object storage
# ---------------------------------------------------------------------------


@runtime_checkable
class ObjectStorage(Protocol):
    """Minimal interface for S3-compatible object storage."""

    async def ensure_bucket(self) -> None: ...

    async def upload_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str: ...

    async def download_bytes(self, key: str) -> bytes: ...

    async def delete_object(self, key: str) -> None: ...


# ---------------------------------------------------------------------------
# Graph database
# ---------------------------------------------------------------------------


@runtime_checkable
class GraphDatabase(Protocol):
    """Minimal interface for knowledge graph operations."""

    async def create_document_node(
        self,
        *,
        doc_id: str,
        filename: str,
        matter_id: str,
        **kwargs: Any,
    ) -> None: ...

    async def create_entity_node(
        self,
        *,
        name: str,
        entity_type: str,
        matter_id: str,
        **kwargs: Any,
    ) -> None: ...

    async def query_entity_connections(
        self,
        entity_name: str,
        *,
        matter_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]: ...
