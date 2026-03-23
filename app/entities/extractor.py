"""Zero-shot NER using GLiNER.

The model is lazy-loaded on first use (~600MB, runs on CPU).
Extracts: person, organization, location, date, monetary_amount,
case_number, court, vehicle, phone_number, email_address, flight_number, address.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)

# Entity types for GLiNER (from CLAUDE.md Section 7.3)
GLINER_ENTITY_TYPES: list[str] = [
    "person",
    "organization",
    "location",
    "date",
    "monetary_amount",
    "case_number",
    "court",
    "vehicle",
    "phone_number",
    "email_address",
    "flight_number",
    "address",
]


@dataclass
class ExtractedEntity:
    """A single entity extracted from text by GLiNER."""

    text: str  # The surface form ("Jeffrey Epstein")
    type: str  # Entity type ("person")
    score: float  # Confidence score (0-1)
    start: int  # Character offset start
    end: int  # Character offset end


class EntityExtractor:
    """GLiNER-based zero-shot NER.  Model loaded lazily on first call.

    Usage::

        extractor = EntityExtractor()                   # no I/O yet
        entities  = extractor.extract("Some legal text") # loads model on first call
    """

    def __init__(self, model_name: str = "urchade/gliner_multi_pii-v1") -> None:
        self._model_name = model_name
        self._model = None  # Lazy load — avoids 600 MB hit at import time

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_model(self):
        """Load the GLiNER model into memory (once)."""
        if self._model is None:
            from gliner import GLiNER  # Heavy import deferred until needed

            logger.info("extractor.gliner.loading", model=self._model_name)
            self._model = GLiNER.from_pretrained(self._model_name)
            logger.info("extractor.gliner.loaded")
        return self._model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(
        self,
        text: str,
        *,
        entity_types: list[str] | None = None,
        threshold: float = 0.3,
    ) -> list[ExtractedEntity]:
        """Extract entities from *text* using GLiNER.

        Args:
            text: Input text (typically a single chunk, ~512 tokens).
            entity_types: Override the default ``GLINER_ENTITY_TYPES`` if you
                only need a subset.
            threshold: Minimum confidence score for returned entities.

        Returns:
            List of :class:`ExtractedEntity` with text, type, score, and
            character offsets.
        """
        model = self._load_model()
        labels = entity_types or GLINER_ENTITY_TYPES

        # GLiNER has a practical input-length limit.  Most chunks are ~512
        # tokens which is well within bounds, but we truncate defensively.
        max_chars = 4_000
        truncated = text[:max_chars] if len(text) > max_chars else text

        try:
            raw_entities = model.predict_entities(
                truncated,
                labels,
                threshold=threshold,
            )

            results: list[ExtractedEntity] = [
                ExtractedEntity(
                    text=ent["text"],
                    type=ent["label"],
                    score=round(ent["score"], 4),
                    start=ent["start"],
                    end=ent["end"],
                )
                for ent in raw_entities
            ]

            logger.debug(
                "extractor.extracted",
                count=len(results),
                text_len=len(truncated),
            )
            return results

        except Exception as exc:
            logger.error("extractor.failed", error=str(exc))
            return []

    def extract_batch(
        self,
        texts: list[str],
        *,
        entity_types: list[str] | None = None,
        threshold: float = 0.3,
        batch_size: int = 8,
    ) -> list[list[ExtractedEntity]]:
        """Extract entities from multiple texts using batched inference.

        GLiNER's ``batch_predict_entities`` processes multiple texts in a
        single forward pass, amortising model overhead across the batch.

        Args:
            texts: Input texts (typically chunks, ~512 tokens each).
            entity_types: Override the default ``GLINER_ENTITY_TYPES``.
            threshold: Minimum confidence score for returned entities.
            batch_size: Number of texts per forward pass (default 8).

        Returns:
            List of entity lists, one per input text.
        """
        if not texts:
            return []

        model = self._load_model()
        labels = entity_types or GLINER_ENTITY_TYPES
        max_chars = 4_000

        truncated = [t[:max_chars] if len(t) > max_chars else t for t in texts]

        all_results: list[list[ExtractedEntity]] = []

        try:
            for i in range(0, len(truncated), batch_size):
                batch = truncated[i : i + batch_size]
                batch_preds = model.batch_predict_entities(
                    batch,
                    labels,
                    threshold=threshold,
                )
                for preds in batch_preds:
                    all_results.append(
                        [
                            ExtractedEntity(
                                text=ent["text"],
                                type=ent["label"],
                                score=round(ent["score"], 4),
                                start=ent["start"],
                                end=ent["end"],
                            )
                            for ent in preds
                        ]
                    )

            logger.debug(
                "extractor.batch_extracted",
                texts=len(texts),
                total_entities=sum(len(r) for r in all_results),
                batch_size=batch_size,
            )
            return all_results

        except Exception as exc:
            logger.error("extractor.batch_failed", error=str(exc))
            # Fallback to sequential extraction on batch failure
            logger.warning("extractor.batch_fallback_to_sequential")
            return [self.extract(text, entity_types=entity_types, threshold=threshold) for text in texts]
