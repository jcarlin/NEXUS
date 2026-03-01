"""Visual embedding via ColQwen2.5 (late-interaction multi-vector).

Lazy-loads the 3B parameter model on first use, following the same pattern
as ``SparseEmbedder`` and ``Reranker``. Synchronous inference — called via
``asyncio.to_thread()`` when used from async contexts.

Feature-flagged via ``ENABLE_VISUAL_EMBEDDINGS``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
import torch

if TYPE_CHECKING:
    from PIL import Image

logger = structlog.get_logger(__name__)


class VisualEmbedder:
    """ColQwen2.5 visual embedding generator. Model loaded lazily on first call."""

    def __init__(
        self,
        model_name: str = "vidore/colqwen2.5-v0.2",
        device: str = "mps",
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._model = None
        self._processor = None

    def _load_model(self) -> None:
        """Load the ColQwen2_5 model and processor into memory (once)."""
        if self._model is not None:
            return

        from colpali_engine.models import ColQwen2_5, ColQwen2_5_Processor

        logger.info("visual_embedder.loading", model=self._model_name, device=self._device)
        self._model = ColQwen2_5.from_pretrained(
            self._model_name,
            torch_dtype=torch.bfloat16,
            device_map=self._device,
        ).eval()
        self._processor = ColQwen2_5_Processor.from_pretrained(self._model_name)
        logger.info("visual_embedder.loaded")

    def embed_images(self, images: list[Image.Image]) -> list[list[list[float]]]:
        """Generate multi-vector embeddings for a batch of page images.

        Args:
            images: List of PIL Image objects (one per page).

        Returns:
            List of embeddings, where each embedding is a list of patch vectors
            (patches × 128d). Shape: ``[batch, patches, 128]``.
        """
        self._load_model()
        assert self._processor is not None
        assert self._model is not None

        batch = self._processor.process_images(images).to(self._model.device)

        with torch.no_grad():
            embeddings = self._model(**batch)

        return [emb.cpu().float().tolist() for emb in embeddings]

    def embed_query(self, text: str) -> list[list[float]]:
        """Generate multi-vector query embedding from text.

        Args:
            text: The query string.

        Returns:
            Query token embeddings as a list of vectors (tokens × 128d).
        """
        self._load_model()
        assert self._processor is not None
        assert self._model is not None

        batch = self._processor.process_queries([text]).to(self._model.device)

        with torch.no_grad():
            embeddings = self._model(**batch)

        return embeddings[0].cpu().float().tolist()

    @staticmethod
    def compute_max_sim(
        query_vectors: list[list[float]],
        doc_vectors: list[list[float]],
    ) -> float:
        """Compute MaxSim score between query and document multi-vectors.

        For each query token vector, find the maximum cosine similarity to any
        document patch vector. The final score is the mean of these maxima.

        Args:
            query_vectors: Query token embeddings (Q × D).
            doc_vectors: Document patch embeddings (P × D).

        Returns:
            MaxSim score (float).
        """
        q = torch.tensor(query_vectors, dtype=torch.float32)
        d = torch.tensor(doc_vectors, dtype=torch.float32)

        # Normalize for cosine similarity
        q = q / q.norm(dim=-1, keepdim=True)
        d = d / d.norm(dim=-1, keepdim=True)

        # (Q, P) similarity matrix → max per query token → mean
        sim = torch.matmul(q, d.T)
        max_sim_per_token = sim.max(dim=-1).values
        return float(max_sim_per_token.mean())
