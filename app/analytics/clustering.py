"""Topic clustering via BERTopic (M10c).

Feature-flagged via ``ENABLE_TOPIC_CLUSTERING``.  When disabled, ``cluster()``
returns an empty list.  BERTopic model is lazy-loaded on first use.
"""

from __future__ import annotations

import structlog

from app.analytics.schemas import TopicCluster

logger = structlog.get_logger(__name__)


class TopicClusterer:
    """Lazy-loaded BERTopic wrapper for unsupervised topic clustering."""

    def __init__(
        self,
        enabled: bool = False,
        embedding_model: str = "all-MiniLM-L6-v2",
        min_cluster_size: int = 5,
    ) -> None:
        self._enabled = enabled
        self._embedding_model = embedding_model
        self._min_cluster_size = min_cluster_size
        self._model = None

    def _get_model(self):
        """Lazy-load BERTopic model on first use."""
        if self._model is None:
            from bertopic import BERTopic

            self._model = BERTopic(
                embedding_model=self._embedding_model,
                min_topic_size=self._min_cluster_size,
                verbose=False,
            )
        return self._model

    def cluster(
        self,
        texts: list[str],
        min_cluster_size: int | None = None,
    ) -> list[TopicCluster]:
        """Run BERTopic unsupervised clustering on input texts.

        Returns an empty list when the feature flag is off or there are
        insufficient texts for clustering.
        """
        if not self._enabled:
            return []

        if len(texts) < (min_cluster_size or self._min_cluster_size):
            logger.info(
                "analytics.clustering.insufficient_texts",
                count=len(texts),
                min_required=min_cluster_size or self._min_cluster_size,
            )
            return []

        model = self._get_model()

        topics, _probs = model.fit_transform(texts)

        # Extract topic info
        topic_info = model.get_topic_info()

        clusters = []
        for _, row in topic_info.iterrows():
            topic_id = row["Topic"]
            if topic_id == -1:
                continue  # Skip outlier cluster

            # Get representative terms for this topic
            topic_terms = model.get_topic(topic_id)
            terms = [term for term, _score in (topic_terms or [])][:10]

            label = row.get("Name", f"Topic {topic_id}")
            doc_count = row.get("Count", 0)

            clusters.append(
                TopicCluster(
                    topic_id=topic_id,
                    label=str(label),
                    representative_terms=terms,
                    document_count=int(doc_count),
                )
            )

        logger.info(
            "analytics.clustering.complete",
            total_texts=len(texts),
            clusters_found=len(clusters),
        )
        return clusters
