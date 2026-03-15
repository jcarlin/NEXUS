"""Domain-specific exception classes.

Decouple the service layer from HTTP semantics by raising typed exceptions
that routers can translate into appropriate ``HTTPException`` responses.
"""

from __future__ import annotations


class NexusError(Exception):
    """Base class for all NEXUS domain exceptions."""


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------


class DocumentNotFoundError(NexusError):
    """Raised when a document ID cannot be resolved."""


class MatterNotFoundError(NexusError):
    """Raised when a matter ID cannot be resolved."""


class ChunkNotFoundError(NexusError):
    """Raised when a chunk ID cannot be resolved."""


# ---------------------------------------------------------------------------
# Security & authorization
# ---------------------------------------------------------------------------


class PrivilegeViolationError(NexusError):
    """Raised when an operation is denied by privilege enforcement."""


class MatterScopeError(NexusError):
    """Raised when a cross-matter access attempt is detected."""


# ---------------------------------------------------------------------------
# Ingestion & processing
# ---------------------------------------------------------------------------


class IngestionError(NexusError):
    """Raised when document ingestion fails."""


class RedactionError(NexusError):
    """Raised when redaction processing fails.

    Per CLAUDE.md rule 37, redaction failures must raise — never silently
    skip pages that fail to parse.
    """


class ParsingError(NexusError):
    """Raised when document parsing (Docling) fails."""


# ---------------------------------------------------------------------------
# LLM & AI
# ---------------------------------------------------------------------------


class LLMProviderError(NexusError):
    """Raised when an LLM provider call fails after retries."""


class EmbeddingError(NexusError):
    """Raised when embedding generation fails."""


# ---------------------------------------------------------------------------
# Export & external
# ---------------------------------------------------------------------------


class ExportError(NexusError):
    """Raised when an export operation fails."""


class StorageError(NexusError):
    """Raised when object storage (MinIO) operations fail."""
