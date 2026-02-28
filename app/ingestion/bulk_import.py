"""Bulk import data model, adapter protocol, and helpers.

Defines the ``ImportDocument`` schema for pre-parsed documents and the
``DatasetAdapter`` protocol that all import adapters must satisfy.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class ImportDocument(BaseModel):
    """A single document ready for import (text already extracted)."""

    source_id: str = ""
    filename: str
    text: str
    content_hash: str = ""
    source: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    page_count: int = 1
    doc_type: str = "document"
    email_headers: dict[str, str] | None = None


# ---------------------------------------------------------------------------
# Adapter protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class DatasetAdapter(Protocol):
    """Interface for dataset import adapters.

    Mirrors the ``EmbeddingProvider`` pattern in ``app/common/embedder.py``.
    """

    @property
    def name(self) -> str:
        """Short identifier for this adapter (e.g. ``"directory"``)."""
        ...

    def iter_documents(self, *, limit: int | None = None) -> Iterator[ImportDocument]:
        """Yield ``ImportDocument`` instances from the data source.

        If *limit* is set, yield at most *limit* documents.
        """
        ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def compute_content_hash(text: str) -> str:
    """Return a truncated SHA-256 hex digest (16 chars) of *text*."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
