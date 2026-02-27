"""Backward-compatible re-export. Use ``app.common.embedder`` directly.

The ``TextEmbedder`` class has been replaced by ``EmbeddingProvider`` and its
concrete implementations in ``app.common.embedder`` (M8b).
"""

from app.common.embedder import OpenAIEmbeddingProvider as TextEmbedder

__all__ = ["TextEmbedder"]
