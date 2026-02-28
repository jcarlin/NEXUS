"""Near-duplicate detection and version tracking for documents.

Uses MinHash + LSH from the datasketch library for efficient
Jaccard similarity estimation. Per-matter LSH indices are maintained.

Version detection piggybacks on dedup: documents with Jaccard 0.80-0.95
and version-indicating filenames (v1, v2, draft, final) are grouped.
"""

from __future__ import annotations

import re
import uuid

import structlog
from datasketch import MinHash, MinHashLSH

logger = structlog.get_logger(__name__)

# Regex for version-indicating patterns in filenames
_VERSION_PATTERN = re.compile(
    r"(?:[-_ .])?(v\d+|version\s*\d+|draft|final|rev\s*\d+|revised)",
    re.IGNORECASE,
)


def _text_to_shingles(text: str, k: int = 5) -> set[str]:
    """Convert text to a set of character k-shingles."""
    text = text.lower().strip()
    if len(text) < k:
        return {text}
    return {text[i:i + k] for i in range(len(text) - k + 1)}


class NearDuplicateDetector:
    """Detect near-duplicate documents using MinHash + LSH.

    Maintains per-matter LSH indices for efficient similarity search.
    """

    def __init__(
        self,
        threshold: float = 0.80,
        num_perm: int = 128,
    ) -> None:
        self.threshold = threshold
        self.num_perm = num_perm
        self._indices: dict[str, MinHashLSH] = {}  # matter_id -> LSH index
        self._minhashes: dict[str, MinHash] = {}  # doc_id -> MinHash

    def _get_index(self, matter_id: str) -> MinHashLSH:
        """Get or create the LSH index for a matter."""
        if matter_id not in self._indices:
            self._indices[matter_id] = MinHashLSH(
                threshold=self.threshold,
                num_perm=self.num_perm,
            )
        return self._indices[matter_id]

    def compute_minhash(self, text: str) -> MinHash:
        """Compute a MinHash signature for document text."""
        m = MinHash(num_perm=self.num_perm)
        shingles = _text_to_shingles(text)
        for s in shingles:
            m.update(s.encode("utf-8"))
        return m

    def find_duplicates(
        self,
        doc_id: str,
        text: str,
        matter_id: str,
    ) -> list[tuple[str, float]]:
        """Check a document against the LSH index for near-duplicates.

        Returns a list of (matching_doc_id, jaccard_score) tuples.
        """
        minhash = self.compute_minhash(text)
        self._minhashes[doc_id] = minhash

        index = self._get_index(matter_id)

        # Query for candidates
        candidates: list[str] = []
        try:
            candidates = index.query(minhash)
        except ValueError:
            pass

        # Compute exact Jaccard for each candidate
        matches: list[tuple[str, float]] = []
        for candidate_id in candidates:
            if candidate_id == doc_id:
                continue
            candidate_mh = self._minhashes.get(candidate_id)
            if candidate_mh is not None:
                score = minhash.jaccard(candidate_mh)
                if score >= self.threshold:
                    matches.append((candidate_id, score))

        # Insert into index
        try:
            index.insert(doc_id, minhash)
        except ValueError:
            # Already in index
            pass

        if matches:
            logger.info(
                "dedup.duplicates_found",
                doc_id=doc_id,
                match_count=len(matches),
                matter_id=matter_id,
            )

        return matches

    @staticmethod
    def assign_cluster(
        engine,
        doc_id: str,
        matches: list[tuple[str, float]],
    ) -> str | None:
        """Assign a duplicate cluster ID to the document and its matches.

        If any match already has a cluster_id, reuse it. Otherwise create
        a new one. Updates all documents in the cluster.

        Returns the cluster_id or None if no matches.
        """
        if not matches:
            return None

        from sqlalchemy import text

        match_ids = [m[0] for m in matches]

        with engine.connect() as conn:
            # Check if any match already has a cluster_id
            placeholders = ", ".join(f":id_{i}" for i in range(len(match_ids)))
            params = {f"id_{i}": mid for i, mid in enumerate(match_ids)}

            result = conn.execute(
                text(
                    f"SELECT duplicate_cluster_id FROM documents "
                    f"WHERE id IN ({placeholders}) "
                    f"AND duplicate_cluster_id IS NOT NULL "
                    f"LIMIT 1"
                ),
                params,
            )
            row = result.first()
            cluster_id = row.duplicate_cluster_id if row else str(uuid.uuid4())[:16]

            # Find the best score for this document
            best_score = max(score for _, score in matches)

            # Update the current document
            conn.execute(
                text(
                    """
                    UPDATE documents
                    SET duplicate_cluster_id = :cluster_id,
                        duplicate_score = :score,
                        updated_at = now()
                    WHERE id = :doc_id
                    """
                ),
                {"cluster_id": cluster_id, "score": best_score, "doc_id": doc_id},
            )

            # Update matches that don't have a cluster_id yet
            for match_id, score in matches:
                conn.execute(
                    text(
                        """
                        UPDATE documents
                        SET duplicate_cluster_id = :cluster_id,
                            duplicate_score = GREATEST(COALESCE(duplicate_score, 0), :score),
                            updated_at = now()
                        WHERE id = :match_id AND duplicate_cluster_id IS NULL
                        """
                    ),
                    {"cluster_id": cluster_id, "score": score, "match_id": match_id},
                )

            conn.commit()

        logger.info(
            "dedup.cluster_assigned",
            doc_id=doc_id,
            cluster_id=cluster_id,
            match_count=len(matches),
        )
        return cluster_id


class VersionDetector:
    """Detect version groups among near-duplicate documents.

    Piggybacks on dedup results: documents with Jaccard 0.80-0.95
    and version-indicating filenames are grouped as versions.
    """

    @staticmethod
    def extract_version_info(filename: str) -> tuple[str | None, bool]:
        """Extract version indicator from a filename.

        Returns (version_label, is_final).
        """
        match = _VERSION_PATTERN.search(filename)
        if not match:
            return None, False

        label = match.group(1).strip().lower()
        is_final = label in ("final",)
        return label, is_final

    @staticmethod
    def detect_versions(
        engine,
        doc_id: str,
        filename: str,
        matches: list[tuple[str, float]],
    ) -> str | None:
        """Check if this document and its near-duplicates form a version group.

        Criteria:
        - Jaccard between 0.80 and 0.95 (similar but not identical)
        - At least one document has a version-indicating filename

        Returns version_group_id or None.
        """
        if not matches:
            return None

        from sqlalchemy import text

        # Filter to version-range matches (0.80-0.95)
        version_matches = [(mid, score) for mid, score in matches if 0.80 <= score <= 0.95]
        if not version_matches:
            return None

        # Check for version indicators in filenames
        current_version, current_is_final = VersionDetector.extract_version_info(filename)

        match_ids = [m[0] for m in version_matches]
        placeholders = ", ".join(f":id_{i}" for i in range(len(match_ids)))
        params = {f"id_{i}": mid for i, mid in enumerate(match_ids)}

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    f"SELECT id, filename, version_group_id FROM documents "
                    f"WHERE id IN ({placeholders})"
                ),
                params,
            )
            match_docs = result.all()

            has_version_indicator = current_version is not None
            for doc in match_docs:
                v, _ = VersionDetector.extract_version_info(doc.filename)
                if v is not None:
                    has_version_indicator = True
                    break

            if not has_version_indicator:
                return None

            # Reuse existing version_group_id or create new
            group_id = None
            for doc in match_docs:
                if doc.version_group_id:
                    group_id = doc.version_group_id
                    break
            if not group_id:
                group_id = str(uuid.uuid4())[:16]

            # Determine version number (simple: count existing in group + 1)
            count_result = conn.execute(
                text(
                    "SELECT count(*) FROM documents WHERE version_group_id = :gid"
                ),
                {"gid": group_id},
            )
            existing_count = count_result.scalar_one()
            version_number = existing_count + 1

            # Update current document
            conn.execute(
                text(
                    """
                    UPDATE documents
                    SET version_group_id = :group_id,
                        version_number = :version_number,
                        is_final_version = :is_final,
                        updated_at = now()
                    WHERE id = :doc_id
                    """
                ),
                {
                    "group_id": group_id,
                    "version_number": version_number,
                    "is_final": current_is_final,
                    "doc_id": doc_id,
                },
            )

            # Update matches that don't have a version_group_id
            for doc in match_docs:
                if not doc.version_group_id:
                    v_label, v_final = VersionDetector.extract_version_info(doc.filename)
                    conn.execute(
                        text(
                            """
                            UPDATE documents
                            SET version_group_id = :group_id,
                                version_number = 1,
                                is_final_version = :is_final,
                                updated_at = now()
                            WHERE id = :doc_id AND version_group_id IS NULL
                            """
                        ),
                        {
                            "group_id": group_id,
                            "is_final": v_final,
                            "doc_id": doc.id,
                        },
                    )

            conn.commit()

        logger.info(
            "version.group_assigned",
            doc_id=doc_id,
            group_id=group_id,
            version_number=version_number,
        )
        return group_id
