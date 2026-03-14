"""SPLADE v3 sparse embedding provider.

Lazy-loads naver/splade-v3-doc (document encoder) and naver/splade-v3-query
(query encoder) from HuggingFace. Uses asymmetric encoding: different models
for documents vs queries for optimal retrieval.
"""

from __future__ import annotations

import structlog
import torch
from transformers import AutoModelForMaskedLM, AutoTokenizer

logger = structlog.get_logger(__name__)


class SPLADEProvider:
    """SPLADE v3 sparse embedding provider with asymmetric doc/query encoding."""

    def __init__(
        self,
        doc_model: str = "naver/splade-v3-doc",
        query_model: str = "naver/splade-v3-query",
        max_length: int = 512,
    ) -> None:
        self._doc_model_name = doc_model
        self._query_model_name = query_model
        self._max_length = max_length
        self._doc_tokenizer: AutoTokenizer | None = None
        self._doc_model: AutoModelForMaskedLM | None = None
        self._query_tokenizer: AutoTokenizer | None = None
        self._query_model: AutoModelForMaskedLM | None = None

    def _ensure_doc_model(self) -> None:
        """Lazy-load document encoder."""
        if self._doc_model is None:
            logger.info("splade.loading_doc_model", model=self._doc_model_name)
            self._doc_tokenizer = AutoTokenizer.from_pretrained(self._doc_model_name)
            self._doc_model = AutoModelForMaskedLM.from_pretrained(self._doc_model_name)
            self._doc_model.eval()

    def _ensure_query_model(self) -> None:
        """Lazy-load query encoder."""
        if self._query_model is None:
            logger.info("splade.loading_query_model", model=self._query_model_name)
            self._query_tokenizer = AutoTokenizer.from_pretrained(self._query_model_name)
            self._query_model = AutoModelForMaskedLM.from_pretrained(self._query_model_name)
            self._query_model.eval()

    def _encode_sparse(
        self,
        text: str,
        tokenizer: AutoTokenizer,
        model: AutoModelForMaskedLM,
    ) -> tuple[list[int], list[float]]:
        """Encode text to sparse vector using ReLU+log activation."""
        tokens = tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=self._max_length,
            padding=True,
        )
        with torch.no_grad():
            output = model(**tokens)
        # ReLU + log(1 + x) activation, max-pool over sequence
        logits = output.logits  # (1, seq_len, vocab_size)
        activated = torch.log1p(torch.relu(logits))
        sparse_vec = activated.max(dim=1).values.squeeze()  # (vocab_size,)
        # Extract non-zero indices and values
        nonzero = sparse_vec.nonzero().squeeze(-1)
        indices = nonzero.tolist()
        values = sparse_vec[nonzero].tolist()
        # Handle single element case
        if isinstance(indices, int):
            indices = [indices]
            values = [values]
        return indices, values

    def embed_texts(self, texts: list[str]) -> list[tuple[list[int], list[float]]]:
        """Embed documents using the document model."""
        self._ensure_doc_model()
        results = []
        for text in texts:
            indices, values = self._encode_sparse(text, self._doc_tokenizer, self._doc_model)
            results.append((indices, values))
        return results

    def embed_single(self, text: str) -> tuple[list[int], list[float]]:
        """Embed a single document text."""
        return self.embed_texts([text])[0]

    def embed_query_sparse(self, text: str) -> tuple[list[int], list[float]]:
        """Embed a query using the query model (asymmetric encoding)."""
        self._ensure_query_model()
        return self._encode_sparse(text, self._query_tokenizer, self._query_model)
