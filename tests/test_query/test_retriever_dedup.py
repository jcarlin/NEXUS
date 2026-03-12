"""Tests for T1-7: Near-duplicate retrieval deduplication."""

from __future__ import annotations

from app.query.retriever import HybridRetriever


class TestDeduplicateByCluster:
    """Tests for HybridRetriever._deduplicate_by_cluster()."""

    def test_deduplicates_same_cluster(self):
        """Chunks from the same cluster should be reduced to one."""
        results = [
            {"id": "a", "score": 0.9, "duplicate_cluster_id": "cluster-1"},
            {"id": "b", "score": 0.8, "duplicate_cluster_id": "cluster-1"},
            {"id": "c", "score": 0.7, "duplicate_cluster_id": "cluster-1"},
        ]
        deduped = HybridRetriever._deduplicate_by_cluster(results)
        assert len(deduped) == 1
        assert deduped[0]["id"] == "a"  # Highest score

    def test_keeps_final_version(self):
        """Final version should be preferred within a cluster."""
        results = [
            {"id": "a", "score": 0.9, "duplicate_cluster_id": "cluster-1"},
            {"id": "b", "score": 0.7, "duplicate_cluster_id": "cluster-1", "is_final_version": True},
        ]
        deduped = HybridRetriever._deduplicate_by_cluster(results)
        assert len(deduped) == 1
        assert deduped[0]["id"] == "b"  # Final version preferred

    def test_no_cluster_passthrough(self):
        """Chunks without cluster_id should pass through unchanged."""
        results = [
            {"id": "a", "score": 0.9},
            {"id": "b", "score": 0.8},
            {"id": "c", "score": 0.7},
        ]
        deduped = HybridRetriever._deduplicate_by_cluster(results)
        assert len(deduped) == 3

    def test_mixed_clustered_and_unclustered(self):
        """Mix of clustered and unclustered chunks."""
        results = [
            {"id": "a", "score": 0.95},
            {"id": "b", "score": 0.9, "duplicate_cluster_id": "cluster-1"},
            {"id": "c", "score": 0.85, "duplicate_cluster_id": "cluster-1"},
            {"id": "d", "score": 0.8},
            {"id": "e", "score": 0.75, "duplicate_cluster_id": "cluster-2"},
            {"id": "f", "score": 0.7, "duplicate_cluster_id": "cluster-2"},
        ]
        deduped = HybridRetriever._deduplicate_by_cluster(results)
        assert len(deduped) == 4  # 2 unclustered + 1 per cluster
        ids = [r["id"] for r in deduped]
        assert "a" in ids
        assert "d" in ids
        assert "b" in ids  # Highest in cluster-1
        assert "e" in ids  # Highest in cluster-2

    def test_empty_results(self):
        """Empty results should return empty."""
        deduped = HybridRetriever._deduplicate_by_cluster([])
        assert deduped == []

    def test_results_sorted_by_score(self):
        """Deduped results should be sorted by score descending."""
        results = [
            {"id": "a", "score": 0.5},
            {"id": "b", "score": 0.9, "duplicate_cluster_id": "c1"},
            {"id": "c", "score": 0.7, "duplicate_cluster_id": "c1"},
        ]
        deduped = HybridRetriever._deduplicate_by_cluster(results)
        scores = [r["score"] for r in deduped]
        assert scores == sorted(scores, reverse=True)
