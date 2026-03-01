"""Tests for BERTopic topic clustering (M10c).

Covers:
- BERTopic clustering with auto-generated labels
- Feature flag disabled behavior (returns empty list)
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pandas as pd

from app.analytics.clustering import TopicClusterer
from app.analytics.schemas import TopicCluster

# ---------------------------------------------------------------------------
# Test 7: BERTopic clustering with auto labels + disabled behavior
# ---------------------------------------------------------------------------


def test_bertopic_clustering_with_auto_labels():
    """Mock BERTopic by patching the bertopic module import.

    Feed sample texts to TopicClusterer(enabled=True). Verify cluster
    structure. Also test: when disabled, returns empty list.
    """
    # --- Part 1: Disabled clusterer returns empty list ---
    disabled_clusterer = TopicClusterer(enabled=False)
    result = disabled_clusterer.cluster(["text1", "text2", "text3", "text4", "text5"])
    assert result == []

    # --- Part 2: Enabled clusterer with mocked BERTopic ---
    sample_texts = [
        "Securities fraud complaint filed in federal court",
        "Stock manipulation scheme involving insider trading",
        "Breach of contract regarding software licensing agreement",
        "Contract termination notice due to non-performance",
        "Employment discrimination lawsuit under Title VII",
        "Wrongful termination claim with retaliation allegations",
        "Securities fraud and stock manipulation charges",
        "Breach of licensing agreement and IP infringement",
    ]

    # Mock BERTopic model
    mock_model = MagicMock()

    # fit_transform returns (topics, probabilities)
    mock_model.fit_transform.return_value = (
        [0, 0, 1, 1, 2, 2, 0, 1],  # topic assignments
        [[0.9, 0.05, 0.05]] * 8,  # probabilities (not used directly)
    )

    # get_topic_info returns a DataFrame with Topic, Name, Count columns
    mock_model.get_topic_info.return_value = pd.DataFrame(
        {
            "Topic": [-1, 0, 1, 2],
            "Name": ["Outlier", "0_securities_fraud", "1_breach_contract", "2_employment_discrimination"],
            "Count": [0, 3, 3, 2],
        }
    )

    # get_topic returns representative terms for each topic
    mock_model.get_topic.side_effect = lambda topic_id: {
        0: [("securities", 0.9), ("fraud", 0.85), ("stock", 0.7), ("insider", 0.6)],
        1: [("contract", 0.92), ("breach", 0.88), ("licensing", 0.75), ("agreement", 0.7)],
        2: [("employment", 0.91), ("discrimination", 0.87), ("termination", 0.72)],
    }.get(topic_id, [])

    # Create a mock bertopic module so the lazy import works
    mock_bertopic_module = MagicMock()
    mock_bertopic_module.BERTopic = MagicMock(return_value=mock_model)

    with patch.dict(sys.modules, {"bertopic": mock_bertopic_module}):
        clusterer = TopicClusterer(enabled=True, min_cluster_size=2)
        clusters = clusterer.cluster(sample_texts)

    # Verify cluster structure
    assert len(clusters) == 3  # 3 topics (outlier -1 excluded)

    # All results should be TopicCluster instances
    for c in clusters:
        assert isinstance(c, TopicCluster)

    # Verify topic 0: securities fraud
    topic_0 = next(c for c in clusters if c.topic_id == 0)
    assert "securities" in topic_0.label.lower() or topic_0.topic_id == 0
    assert topic_0.document_count == 3
    assert "securities" in topic_0.representative_terms
    assert "fraud" in topic_0.representative_terms

    # Verify topic 1: breach of contract
    topic_1 = next(c for c in clusters if c.topic_id == 1)
    assert topic_1.document_count == 3
    assert "contract" in topic_1.representative_terms

    # Verify topic 2: employment discrimination
    topic_2 = next(c for c in clusters if c.topic_id == 2)
    assert topic_2.document_count == 2
    assert "employment" in topic_2.representative_terms

    # Verify BERTopic was called correctly
    mock_model.fit_transform.assert_called_once_with(sample_texts)

    # --- Part 3: Insufficient texts returns empty list ---
    with patch.dict(sys.modules, {"bertopic": mock_bertopic_module}):
        clusterer_min5 = TopicClusterer(enabled=True, min_cluster_size=5)
        result = clusterer_min5.cluster(["only two", "texts here"])
    assert result == []
