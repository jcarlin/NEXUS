"""Cross-document entity resolution using fuzzy string matching and embedding similarity.

Resolves duplicates like "J. Epstein" / "Jeffrey Epstein" / "Epstein, Jeffrey"
into a single canonical entity node in the knowledge graph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import networkx as nx
import numpy as np
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


@dataclass
class MergeGroup:
    """A group of entity names that should be merged into one canonical node.

    All ``aliases`` will be merged into ``canonical``.
    """

    canonical: str
    aliases: list[str] = field(default_factory=list)
    entity_type: str = ""


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

            # Token-based blocking: bucket names by each lowercase token.
            # "Jeffrey Epstein" → tokens {"jeffrey", "epstein"}
            # "Epstein, Jeffrey" → tokens {"epstein", "jeffrey"}
            # Both land in the "epstein" bucket → compared.
            # This replaces first-char blocking which missed cross-initial
            # duplicates (e.g. "Jeffrey Epstein" vs "Epstein, Jeffrey").
            token_to_indices: dict[str, list[int]] = {}
            for idx, name in enumerate(unique_names):
                tokens = set(re.sub(r"[^a-z0-9\s]", "", name.lower()).split())
                for tok in tokens:
                    if len(tok) >= 3:  # skip very short tokens
                        token_to_indices.setdefault(tok, []).append(idx)

            comparison_pairs: set[tuple[int, int]] = set()
            for indices in token_to_indices.values():
                if len(indices) > 200:  # skip extremely common tokens
                    continue
                for ii in range(len(indices)):
                    for jj in range(ii + 1, len(indices)):
                        comparison_pairs.add((indices[ii], indices[jj]))

            for i, j in comparison_pairs:
                name_a = unique_names[i]
                name_b = unique_names[j]
                score = fuzz.ratio(
                    " ".join(name_a.lower().split()),
                    " ".join(name_b.lower().split()),
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

            # Batch cosine similarity via numpy matrix operations
            matrix = np.array(embeddings)
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)

            # Avoid division by zero for zero-vectors
            safe_norms = np.where(norms == 0, 1.0, norms)
            normalized = matrix / safe_norms

            # Similarity matrix (only upper triangle needed)
            sim_matrix = normalized @ normalized.T

            # Zero out rows/cols for zero-norm vectors
            zero_mask = norms.squeeze() == 0
            sim_matrix[zero_mask, :] = 0.0
            sim_matrix[:, zero_mask] = 0.0

            # Extract upper-triangle pairs above threshold
            rows, cols = np.where(np.triu(sim_matrix >= self.cosine_threshold, k=1))
            for r, c in zip(rows, cols):
                matches.append(
                    EntityMatch(
                        name_a=unique_names[r],
                        name_b=unique_names[c],
                        entity_type=entity_type,
                        score=float(sim_matrix[r, c]),
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

    def compute_merge_groups(
        self,
        matches: list[EntityMatch],
    ) -> list[MergeGroup]:
        """Compute transitive merge groups from pairwise matches.

        Uses ``networkx.connected_components`` to find the transitive closure:
        if A≈B and B≈C, then {A, B, C} form a single group.  Within each
        group, :meth:`select_canonical` picks the best representative name.

        Returns
        -------
        List of :class:`MergeGroup` — one per connected component that
        has at least two members.
        """
        # Group matches by entity_type (connected components are per-type)
        by_type: dict[str, list[EntityMatch]] = {}
        for m in matches:
            by_type.setdefault(m.entity_type, []).append(m)

        groups: list[MergeGroup] = []

        for entity_type, type_matches in by_type.items():
            g = nx.Graph()
            for m in type_matches:
                g.add_edge(m.name_a, m.name_b)

            for component in nx.connected_components(g):
                if len(component) < 2:
                    continue

                members = list(component)

                # Find canonical by iterating pairwise through members
                canonical = members[0]
                for other in members[1:]:
                    canonical, _ = self.select_canonical(canonical, other)

                aliases = [m for m in members if m != canonical]
                groups.append(
                    MergeGroup(
                        canonical=canonical,
                        aliases=aliases,
                        entity_type=entity_type,
                    )
                )

        logger.info(
            "resolver.merge_groups.computed",
            total_groups=len(groups),
            total_aliases=sum(len(g.aliases) for g in groups),
        )
        return groups

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        a = np.asarray(vec_a)
        b = np.asarray(vec_b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))
