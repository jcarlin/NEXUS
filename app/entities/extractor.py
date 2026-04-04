"""Zero-shot NER using GLiNER.

The model is lazy-loaded on first use (~600MB, runs on CPU).
Extracts: person, organization, location, date, monetary_amount,
case_number, court, vehicle, phone_number, email_address, flight_number, address.
"""

from __future__ import annotations

import re
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

# Entities to discard — pronouns, stopwords, and common garbage extracted
# from conversational text (emails, chat logs). Case-insensitive.
_STOPWORD_ENTITIES: set[str] = {
    "i",
    "me",
    "my",
    "mine",
    "myself",
    "you",
    "your",
    "yours",
    "yourself",
    "he",
    "him",
    "his",
    "himself",
    "she",
    "her",
    "hers",
    "herself",
    "it",
    "its",
    "itself",
    "we",
    "us",
    "our",
    "ours",
    "ourselves",
    "they",
    "them",
    "their",
    "theirs",
    "themselves",
    "this",
    "that",
    "these",
    "those",
    "who",
    "whom",
    "whose",
    "which",
    "what",
    "the",
    "a",
    "an",
    "here",
    "there",
    "where",
    "when",
    "how",
    "all",
    "each",
    "every",
    "both",
    "few",
    "many",
    "some",
    "any",
    "no",
    "not",
    "none",
    "yes",
    "ok",
    "okay",
    "re",
    "fw",
    "fwd",  # email prefixes
    "n/a",
    "na",
    "tbd",
    "tba",
    "unknown",
    # Relative dates — meaningless without temporal grounding
    "today",
    "tomorrow",
    "yesterday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "saturdays",
    "this weekend",
    "next week",
    "last week",
    # Generic monetary noise
    "money",
    "cash",
    "funds",
    "dollars",
}

# Minimum entity text length (after whitespace normalization)
_MIN_ENTITY_LENGTH = 2

# Maximum entity name length — rejects URL slugs, sentence fragments, descriptive phrases
_MAX_ENTITY_LENGTH = 60

# URL slug pattern: 3+ consecutive hyphen-separated lowercase words (article slugs)
_URL_SLUG_RE = re.compile(r"^[a-z]+-[a-z]+-[a-z]+-")

# OCR garbled text: alternating case runs like "PaWeRhiR" (3+ transitions)
_OCR_GARBLE_RE = re.compile(r"[A-Z]{2}[a-z][A-Z]{2}")


def normalize_entity_name(raw: str) -> str:
    """Normalize an entity name: fix encoding, rejoin hyphenation, collapse whitespace.

    This is the single normalization point — used by the extractor, ingestion
    tasks, and the NER pass script to ensure consistent entity names.

    Uses ``ftfy`` (already installed) for encoding/mojibake/HTML-entity fixes,
    which is purpose-built for cleaning OCR and web-scraped text.
    """
    import ftfy

    # ftfy: fix mojibake, broken Unicode, HTML entities (&amp; → &), etc.
    name = ftfy.fix_text(raw)
    # Replace newlines/carriage returns with spaces
    name = name.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    # Rejoin OCR hyphenation at line breaks: "Ep- stein" → "Epstein"
    name = re.sub(r"(\w)- (\w)", r"\1\2", name)
    name = re.sub(r"(\w) -(\w)", r"\1\2", name)
    # Collapse all whitespace to single spaces
    name = " ".join(name.split()).strip()
    return name


def _is_garbage_entity(text: str) -> bool:
    """Return True if the entity text is a pronoun, stopword, or too short."""
    normalized = normalize_entity_name(text)
    if len(normalized) < _MIN_ENTITY_LENGTH:
        return True
    if normalized.lower() in _STOPWORD_ENTITIES:
        return True
    # All-numeric single tokens that aren't dates or case numbers (e.g. "1", "23")
    if normalized.isdigit() and len(normalized) < 4:
        return True
    # Too long — URL slugs, sentence fragments, descriptive phrases
    if len(normalized) > _MAX_ENTITY_LENGTH:
        return True
    # URL slug pattern (consecutive hyphen-separated lowercase words)
    if _URL_SLUG_RE.match(normalized.lower()):
        return True
    # Contains URL/email indicators
    if any(x in normalized.lower() for x in ("http", "www.", "mailto:")):
        return True
    # Starts with hashtag or mention
    if normalized.startswith(("#", "@")):
        return True
    # OCR garbled text (alternating case runs)
    if _OCR_GARBLE_RE.search(normalized):
        return True
    return False


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
        threshold: float = 0.5,
    ) -> list[ExtractedEntity]:
        """Extract entities from *text* using GLiNER.

        Args:
            text: Input text (typically a single chunk, ~512 tokens).
            entity_types: Override the default ``GLINER_ENTITY_TYPES`` if you
                only need a subset.
            threshold: Minimum confidence score for returned entities.
                Raised from 0.3 to 0.5 — GLiNER's confidence scoring
                naturally filters OCR garbage at higher thresholds.

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

            results: list[ExtractedEntity] = []
            filtered = 0
            for ent in raw_entities:
                clean_text = normalize_entity_name(ent["text"])
                if _is_garbage_entity(clean_text):
                    filtered += 1
                    continue
                results.append(
                    ExtractedEntity(
                        text=clean_text,
                        type=ent["label"],
                        score=round(ent["score"], 4),
                        start=ent["start"],
                        end=ent["end"],
                    )
                )

            logger.debug(
                "extractor.extracted",
                count=len(results),
                filtered=filtered,
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
        threshold: float = 0.5,
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
                    chunk_results: list[ExtractedEntity] = []
                    for ent in preds:
                        clean_text = normalize_entity_name(ent["text"])
                        if _is_garbage_entity(clean_text):
                            continue
                        chunk_results.append(
                            ExtractedEntity(
                                text=clean_text,
                                type=ent["label"],
                                score=round(ent["score"], 4),
                                start=ent["start"],
                                end=ent["end"],
                            )
                        )
                    all_results.append(chunk_results)

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


# ---------------------------------------------------------------------------
# Process-level singleton cache
# ---------------------------------------------------------------------------
# Celery prefork workers reuse the same process for up to max_tasks_per_child
# tasks.  Caching the extractor (and its loaded GLiNER model) here avoids
# the ~11-second model reload on every single NER task.
_EXTRACTOR_CACHE: dict[str, EntityExtractor] = {}


def get_cached_extractor(model_name: str = "urchade/gliner_multi_pii-v1") -> EntityExtractor:
    """Return a process-level cached EntityExtractor instance.

    The GLiNER model (~600 MB) is loaded once on first use and persists
    across Celery tasks within the same worker process.
    """
    if model_name not in _EXTRACTOR_CACHE:
        _EXTRACTOR_CACHE[model_name] = EntityExtractor(model_name=model_name)
    return _EXTRACTOR_CACHE[model_name]
