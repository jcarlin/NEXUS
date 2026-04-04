"""Cross-document entity resolution using fuzzy string matching and embedding similarity.

Resolves duplicates like "J. Epstein" / "Jeffrey Epstein" / "Epstein, Jeffrey"
into a single canonical entity node in the knowledge graph.

Uses ``rapidfuzz.fuzz.token_sort_ratio`` (word-order-insensitive name matching)
and ``rapidfuzz.process.cdist`` (batch all-pairs comparison) — the library's
recommended APIs for this workload.

Supports **blocking** for large entity sets (>10K) to avoid O(n²) blowup.
Blocking groups entities by normalized prefix keys so that cdist only runs
within each block (~50-600 entities), reducing comparisons by ~3000x.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

import networkx as nx
import numpy as np
import structlog
from rapidfuzz import fuzz, process

logger = structlog.get_logger(__name__)

# Entity types that benefit from fuzzy/probabilistic resolution.
# Dates, amounts, phone numbers etc. are inherently unique values —
# fuzzy-matching "$15 million" with "$15 billion" is a category error.
RESOLVABLE_TYPES: frozenset[str] = frozenset(
    {
        "person",
        "organization",
        "location",
        "court",
        "address",
        "vehicle",
    }
)

EXACT_MATCH_TYPES: frozenset[str] = frozenset(
    {
        "date",
        "monetary_amount",
        "case_number",
        "phone_number",
        "email_address",
        "flight_number",
    }
)

# Titles/honorifics to strip before matching (person entities)
_TITLE_PREFIXES: list[str] = [
    "mr.",
    "mrs.",
    "ms.",
    "dr.",
    "prof.",
    "president",
    "defendant",
    "inmate",
    "judge",
    "senator",
    "governor",
    "plaintiff",
    "agent",
    "detective",
    "officer",
    "secretary",
    "representative",
    "rep.",
    "sen.",
    "hon.",
    "miss",
    "sir",
    "lord",
    "lady",
]

# Threshold for switching from naive cdist to blocked matching
_BLOCKING_THRESHOLD = 5000

# Maximum merge group size to prevent runaway transitive closure
MAX_MERGE_GROUP_SIZE = 50


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

    Uses a multi-pass approach:
    1. Case-insensitive exact dedup (zero risk).
    2. Title/honorific stripping and name normalization.
    3. Blocked fuzzy string matching (rapidfuzz) — uses prefix-based blocking
       to avoid O(n²) for large entity sets.
    4. Name-component guard to prevent false merges across different people
       sharing a surname.
    5. Embedding cosine similarity for semantically similar but lexically
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

    # ------------------------------------------------------------------
    # Pre-processing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def strip_titles(name: str) -> str:
        """Remove title/honorific prefixes from a name.

        "Mr. Epstein" → "Epstein", "President Clinton" → "Clinton".
        Returns the stripped name (or original if no title found).
        """
        lower = name.lower().strip()
        for prefix in _TITLE_PREFIXES:
            if lower.startswith(prefix + " ") or lower.startswith(prefix + ". "):
                stripped = name[len(prefix) :].lstrip(". ").strip()
                if stripped:
                    return stripped
            # Handle "Mr Epstein" (no period)
            if lower.startswith(prefix + " "):
                stripped = name[len(prefix) :].lstrip().strip()
                if stripped:
                    return stripped
        return name

    @staticmethod
    def normalize_name_order(name: str) -> str:
        """Normalize 'Last, First' → 'First Last'."""
        if "," in name:
            parts = [p.strip() for p in name.split(",", 1)]
            if len(parts) == 2 and parts[0] and parts[1]:
                # Only reverse if both parts look like name components
                if not any(c.isdigit() for c in parts[0]):
                    return f"{parts[1]} {parts[0]}"
        return name

    @staticmethod
    def case_normalize(name: str) -> str:
        """Normalize for case-insensitive grouping."""
        return " ".join(name.lower().split())

    def exact_dedup(
        self,
        entities: list[dict],
    ) -> tuple[list[EntityMatch], list[dict]]:
        """Case-insensitive exact dedup — zero risk of false merges.

        Returns (matches, deduplicated_entities) where deduplicated_entities
        has one representative per case-normalized group.
        """
        by_type: dict[str, dict[str, list[str]]] = {}
        for ent in entities:
            etype = ent["type"]
            if etype not in RESOLVABLE_TYPES:
                continue
            key = self.case_normalize(ent["name"])
            by_type.setdefault(etype, {}).setdefault(key, []).append(ent["name"])

        matches: list[EntityMatch] = []
        deduped: list[dict] = []

        for entity_type, groups in by_type.items():
            for _key, variants in groups.items():
                unique_variants = list(dict.fromkeys(variants))
                if len(unique_variants) >= 2:
                    # Pick canonical, create matches for the rest
                    canonical = unique_variants[0]
                    for other in unique_variants[1:]:
                        best, _ = self.select_canonical(canonical, other)
                        canonical = best

                    for v in unique_variants:
                        if v != canonical:
                            matches.append(
                                EntityMatch(
                                    name_a=canonical,
                                    name_b=v,
                                    entity_type=entity_type,
                                    score=100.0,
                                    method="exact_case",
                                )
                            )
                    deduped.append({"name": canonical, "type": entity_type})
                else:
                    deduped.append({"name": unique_variants[0], "type": entity_type})

        # Include non-resolvable types as-is
        for ent in entities:
            if ent["type"] not in RESOLVABLE_TYPES:
                deduped.append(ent)

        logger.info(
            "resolver.exact_dedup.complete",
            input_count=len(entities),
            output_count=len(deduped),
            case_matches=len(matches),
        )
        return matches, deduped

    # ------------------------------------------------------------------
    # Blocking strategy
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_block_keys(name: str, entity_type: str) -> list[str]:
        """Generate blocking keys for a name.

        Uses multiple key strategies for recall:
        1. Sorted tokens prefix (first 3 chars of each token, sorted)
        2. Longest token prefix (first 4 chars of longest token — usually surname)
        3. Consonant skeleton (drop vowels, first 4 chars — OCR-resilient)

        Each name can map to multiple blocks, ensuring OCR variants
        land in at least one shared block.
        """
        normalized = " ".join(name.lower().split())
        tokens = normalized.split()
        if not tokens:
            return ["__empty__"]

        keys: list[str] = []

        # Key 1: sorted first-3 of each token (catches reordering)
        sorted_prefixes = sorted(t[:3] for t in tokens if len(t) >= 2)
        if sorted_prefixes:
            keys.append("sp:" + "|".join(sorted_prefixes[:3]))

        # Key 2: longest token prefix (usually surname, resilient to first-name OCR)
        longest = max(tokens, key=len)
        if len(longest) >= 3:
            keys.append(f"lt:{longest[:4]}")

        # Key 3: consonant skeleton of longest token (OCR-resilient)
        consonants = re.sub(r"[aeiou]", "", longest.lower())
        if len(consonants) >= 3:
            keys.append(f"cs:{consonants[:4]}")

        # For persons with 2+ tokens, also block on second token prefix
        # (catches "Jeffrey X" vs "Jeffrey Y" — different people)
        if entity_type == "person" and len(tokens) >= 2:
            second = sorted(tokens, key=len, reverse=True)
            if len(second) > 1 and len(second[1]) >= 3:
                keys.append(f"s2:{second[1][:4]}")

        return keys if keys else ["__fallback__"]

    def _name_component_guard(
        self,
        name_a: str,
        name_b: str,
        entity_type: str,
    ) -> bool:
        """Return True if the match should be REJECTED (false positive guard).

        For person entities: if two names share a surname but have clearly
        different first names, reject the match. Prevents merging
        "Amy Epstein" with "Jeffrey Epstein".
        """
        if entity_type != "person":
            return False

        tokens_a = name_a.lower().split()
        tokens_b = name_b.lower().split()

        if len(tokens_a) < 2 or len(tokens_b) < 2:
            return False

        # Find the longest matching token (likely surname)
        # by checking if they share a common token
        shared = set(tokens_a) & set(tokens_b)
        if not shared:
            return False  # No shared tokens — let fuzzy score decide

        # Get the non-shared tokens (likely first names)
        unique_a = [t for t in tokens_a if t not in shared]
        unique_b = [t for t in tokens_b if t not in shared]

        if not unique_a or not unique_b:
            return False  # One is a subset of the other — allow merge

        # If both have distinct first names >= 3 chars that don't match well,
        # reject the match
        first_a = max(unique_a, key=len)
        first_b = max(unique_b, key=len)

        if len(first_a) >= 3 and len(first_b) >= 3:
            first_name_score = fuzz.ratio(first_a, first_b)
            if first_name_score < 60:
                return True  # Reject — clearly different first names

        return False

    # ------------------------------------------------------------------
    # Fuzzy matching (with optional blocking)
    # ------------------------------------------------------------------

    def _cdist_within_block(
        self,
        names: list[str],
        entity_type: str,
    ) -> list[EntityMatch]:
        """Run cdist on a single block of names."""
        if len(names) < 2:
            return []

        score_matrix = process.cdist(
            names,
            names,
            scorer=fuzz.token_sort_ratio,
            processor=lambda x: " ".join(x.lower().split()),
            score_cutoff=self.fuzzy_threshold,
            workers=-1,
        )

        matches: list[EntityMatch] = []
        n = len(names)
        for i in range(n):
            for j in range(i + 1, n):
                score = score_matrix[i][j]
                if score >= self.fuzzy_threshold:
                    # Apply name component guard for persons
                    if self._name_component_guard(names[i], names[j], entity_type):
                        continue
                    matches.append(
                        EntityMatch(
                            name_a=names[i],
                            name_b=names[j],
                            entity_type=entity_type,
                            score=score,
                            method="fuzzy",
                        )
                    )
        return matches

    def find_fuzzy_matches(
        self,
        entities: list[dict],
    ) -> list[EntityMatch]:
        """Compare entity pairs within resolvable types using rapidfuzz.

        Uses ``fuzz.token_sort_ratio`` (word-order-insensitive) instead of
        basic ``fuzz.ratio``, and ``process.cdist`` for efficient batch
        comparison — both are the library's recommended APIs for name matching.

        For large entity sets (> 5K per type), uses **blocking** to partition
        names into smaller groups before running cdist, reducing complexity
        from O(n²) to O(n * b) where b is the average block size.

        Only processes :data:`RESOLVABLE_TYPES` (person, organization, etc.).
        Dates, monetary amounts, and other exact-value types are skipped.

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
            if entity_type not in RESOLVABLE_TYPES:
                continue

            # Strip titles for matching (but keep originals for canonical selection)
            original_names = list(dict.fromkeys(names))
            if len(original_names) < 2:
                continue

            if len(original_names) <= _BLOCKING_THRESHOLD:
                # Small enough for direct cdist
                type_matches = self._cdist_within_block(original_names, entity_type)
                matches.extend(type_matches)
            else:
                # Use blocking for large sets
                logger.info(
                    "resolver.fuzzy.using_blocking",
                    entity_type=entity_type,
                    total_names=len(original_names),
                )
                blocks: dict[str, set[str]] = defaultdict(set)
                for name in original_names:
                    # Generate block keys from title-stripped + order-normalized name
                    stripped = self.strip_titles(name)
                    normalized = self.normalize_name_order(stripped)
                    keys = self._generate_block_keys(normalized, entity_type)
                    for key in keys:
                        blocks[key].add(name)  # Store ORIGINAL name

                # Deduplicate work: track which pairs we've already compared
                seen_pairs: set[tuple[str, str]] = set()
                total_comparisons = 0

                for block_key, block_names in blocks.items():
                    block_list = sorted(block_names)
                    if len(block_list) < 2:
                        continue

                    total_comparisons += len(block_list) ** 2
                    block_matches = self._cdist_within_block(block_list, entity_type)

                    for m in block_matches:
                        pair = (min(m.name_a, m.name_b), max(m.name_a, m.name_b))
                        if pair not in seen_pairs:
                            seen_pairs.add(pair)
                            matches.append(m)

                logger.info(
                    "resolver.fuzzy.blocking_complete",
                    entity_type=entity_type,
                    blocks=len(blocks),
                    total_comparisons=total_comparisons,
                    matches_found=len([m for m in matches if m.entity_type == entity_type]),
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

        Groups larger than :data:`MAX_MERGE_GROUP_SIZE` are split by removing
        the weakest edges (lowest fuzzy scores) to prevent runaway transitive
        chains where one bad match links hundreds of unrelated entities.

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
                g.add_edge(m.name_a, m.name_b, weight=m.score)

            for component in nx.connected_components(g):
                if len(component) < 2:
                    continue

                members = list(component)

                # Guard: split oversized groups by removing weakest edges
                if len(members) > MAX_MERGE_GROUP_SIZE:
                    logger.warning(
                        "resolver.merge_group.oversized",
                        entity_type=entity_type,
                        size=len(members),
                        sample=members[:5],
                    )
                    # Extract the subgraph for this component
                    subgraph = g.subgraph(members).copy()
                    # Iteratively remove weakest edges until all components
                    # are within size limit
                    while True:
                        oversized = [c for c in nx.connected_components(subgraph) if len(c) > MAX_MERGE_GROUP_SIZE]
                        if not oversized:
                            break
                        # Find and remove the weakest edge in each oversized component
                        for comp in oversized:
                            sub = subgraph.subgraph(comp)
                            weakest_edge = min(
                                sub.edges(data=True),
                                key=lambda e: e[2].get("weight", 0),
                            )
                            subgraph.remove_edge(weakest_edge[0], weakest_edge[1])

                    # Now extract groups from the split subgraph
                    for sub_component in nx.connected_components(subgraph):
                        if len(sub_component) < 2:
                            continue
                        sub_members = list(sub_component)
                        canonical = sub_members[0]
                        for other in sub_members[1:]:
                            canonical, _ = self.select_canonical(canonical, other)
                        aliases = [m for m in sub_members if m != canonical]
                        groups.append(
                            MergeGroup(
                                canonical=canonical,
                                aliases=aliases,
                                entity_type=entity_type,
                            )
                        )
                    continue

                # Normal-sized group
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
