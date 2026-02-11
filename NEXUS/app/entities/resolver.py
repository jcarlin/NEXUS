"""Cross-document entity resolution using fuzzy string matching and embedding similarity.

Resolves duplicates like "J. Epstein" / "Jeffrey Epstein" / "Epstein, Jeffrey"
into a single canonical entity node in the knowledge graph.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from rapidfuzz import fuzz

logger = structlog.get_logger(__name__)


@dataclass
class EntityMatch:
    """A pair of entities that should be merged."""

    name_a: str
    name_b: str
    entity_type: str
    score: float  # 0-100 for fuzzy, 0-1 for cosine
    method: str  # "fuzzy" or "embedding"


class EntityResolver:
    """Resolve duplicate entities across documents.

    Uses a two-pass approach:
    1. Fuzzy string matching (rapidfuzz) for obvious duplicates.
    2. Embedding cosine similarity for semantically similar but lexically
       different names (e.g. nicknames, abbreviations).

    Parameters
    ----------
    fuzzy_threshold:
        Minimum rapidfuzz ratio (0-100) to consider a fuzzy match.
    cosine_threshold:
        Minimum cosine similarity (0-1) for embedding-based matching.
    """

    def __init__(
        self,
        fuzzy_threshold: float = 85,
        cosine_threshold: float = 0.92,
    ) -> None:
        self.fuzzy_threshold = fuzzy_threshold
        self.cosine_threshold = cosine_threshold

    def find_fuzzy_matches(
        self,
        entities: list[dict],
    ) -> list[EntityMatch]:
        """Compare all entity pairs within the same type using rapidfuzz.

        Parameters
        ----------
        entities:
            List of dicts with at least ``name`` and ``type`` keys.

        Returns
        -------
        List of EntityMatch pairs exceeding the fuzzy threshold.
        """
        # Group by type for efficiency
        by_type: dict[str, list[str]] = {}
        for ent in entities:
            etype = ent["type"]
            by_type.setdefault(etype, []).append(ent["name"])

        matches: list[EntityMatch] = []

        for entity_type, names in by_type.items():
            # Deduplicate names list
            unique_names = list(dict.fromkeys(names))
            if len(unique_names) < 2:
                continue

            for i in range(len(unique_names)):
                for j in range(i + 1, len(unique_names)):
                    name_a = unique_names[i]
                    name_b = unique_names[j]
                    score = fuzz.ratio(
                        name_a.lower().strip(),
                        name_b.lower().strip(),
                    )
                    if score >= self.fuzzy_threshold:
                        matches.append(
                            EntityMatch(
                                name_a=name_a,
                                name_b=name_b,
                                entity_type=entity_type,
                                score=score,
                                method="fuzzy",
                            )
                        )

        logger.info(
            "resolver.fuzzy.complete",
            entities_checked=len(entities),
            matches_found=len(matches),
        )
        return matches

    async def find_embedding_matches(
        self,
        entities: list[dict],
        embedder,
    ) -> list[EntityMatch]:
        """Find matching entities using embedding cosine similarity.

        Only checks entities NOT already matched by fuzzy matching.
        This is a more expensive pass reserved for cases where fuzzy
        matching misses semantically similar names.

        Parameters
        ----------
        entities:
            List of dicts with ``name`` and ``type`` keys.
        embedder:
            An embedder instance with an ``embed_texts`` async method.

        Returns
        -------
        List of EntityMatch pairs exceeding the cosine threshold.
        """
        # Group by type
        by_type: dict[str, list[str]] = {}
        for ent in entities:
            etype = ent["type"]
            by_type.setdefault(etype, []).append(ent["name"])

        matches: list[EntityMatch] = []

        for entity_type, names in by_type.items():
            unique_names = list(dict.fromkeys(names))
            if len(unique_names) < 2:
                continue

            # Embed all names in batch
            embeddings = await embedder.embed_texts(unique_names)

            # Compute pairwise cosine similarity
            for i in range(len(unique_names)):
                for j in range(i + 1, len(unique_names)):
                    sim = self._cosine_similarity(embeddings[i], embeddings[j])
                    if sim >= self.cosine_threshold:
                        matches.append(
                            EntityMatch(
                                name_a=unique_names[i],
                                name_b=unique_names[j],
                                entity_type=entity_type,
                                score=sim,
                                method="embedding",
                            )
                        )

        logger.info(
            "resolver.embedding.complete",
            entities_checked=len(entities),
            matches_found=len(matches),
        )
        return matches

    @staticmethod
    def select_canonical(name_a: str, name_b: str) -> tuple[str, str]:
        """Select the canonical name from a pair.

        Preference order:
        1. Longer name (more complete)
        2. Proper capitalization (not all-caps or all-lower)
        3. Alphabetical order (deterministic tiebreaker)

        Returns
        -------
        (canonical_name, alias_name)
        """
        # Prefer longer name
        if len(name_a.strip()) != len(name_b.strip()):
            if len(name_a.strip()) > len(name_b.strip()):
                return name_a, name_b
            return name_b, name_a

        # Prefer proper case (not all upper or all lower)
        a_proper = not (name_a.isupper() or name_a.islower())
        b_proper = not (name_b.isupper() or name_b.islower())
        if a_proper and not b_proper:
            return name_a, name_b
        if b_proper and not a_proper:
            return name_b, name_a

        # Alphabetical tiebreaker
        if name_a <= name_b:
            return name_a, name_b
        return name_b, name_a

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = sum(a * a for a in vec_a) ** 0.5
        norm_b = sum(b * b for b in vec_b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
