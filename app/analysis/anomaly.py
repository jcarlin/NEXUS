"""Communication baseline and anomaly detection.

Pure statistical computation -- no LLM calls. Compares a document's
sentiment dimensions against a person's historical baseline to flag
anomalous communications.
"""

from __future__ import annotations

import structlog
from sqlalchemy import text

from app.analysis.schemas import AnomalyResult, PersonBaseline, SentimentDimensions

logger = structlog.get_logger(__name__)

_SENTIMENT_COLUMNS = [
    "positive",
    "negative",
    "pressure",
    "opportunity",
    "rationalization",
    "intent",
    "concealment",
]


class CommunicationBaseline:
    """Compute and compare communication baselines per person."""

    @staticmethod
    def compute_baseline(
        engine,
        matter_id: str,
        person_name: str,
    ) -> PersonBaseline:
        """Build a statistical baseline for a person's communications.

        Queries the documents table for all documents sent by the person
        within the matter, computing average message length and tone profile.

        Parameters
        ----------
        engine:
            Sync SQLAlchemy engine.
        matter_id:
            Matter to scope the query.
        person_name:
            Sender name to match (case-insensitive ILIKE).

        Returns
        -------
        PersonBaseline with computed statistics.
        """
        sender_pattern = f"%{person_name}%"

        col_avgs = ", ".join(f"avg(sentiment_{col})" for col in _SENTIMENT_COLUMNS)
        query = text(
            f"""
            SELECT
                avg(file_size_bytes) AS avg_len,
                count(*) AS msg_count,
                {col_avgs}
            FROM documents
            WHERE matter_id = :mid
              AND metadata_->>'from' ILIKE :sender_pattern
            """  # noqa: S608
        )

        with engine.connect() as conn:
            result = conn.execute(
                query,
                {"mid": matter_id, "sender_pattern": sender_pattern},
            )
            row = result.first()

        if row is None or row.msg_count == 0:
            logger.info(
                "baseline.no_data",
                matter_id=matter_id,
                person_name=person_name,
            )
            return PersonBaseline()

        tone_profile: dict[str, float] = {}
        for i, col in enumerate(_SENTIMENT_COLUMNS):
            val = row[2 + i]  # offset past avg_len and msg_count
            tone_profile[col] = float(val) if val is not None else 0.0

        baseline = PersonBaseline(
            avg_message_length=float(row.avg_len) if row.avg_len else 0.0,
            message_count=int(row.msg_count),
            tone_profile=tone_profile,
        )

        logger.info(
            "baseline.computed",
            matter_id=matter_id,
            person_name=person_name,
            message_count=baseline.message_count,
        )
        return baseline

    @staticmethod
    def compute_anomaly_score(
        doc_scores: SentimentDimensions,
        baseline: PersonBaseline,
    ) -> AnomalyResult:
        """Compare document sentiment against the person's baseline.

        For each dimension, computes the relative deviation from the
        baseline average. The overall anomaly score is the maximum
        deviation, capped at 1.0.

        Parameters
        ----------
        doc_scores:
            Sentiment dimensions for the current document.
        baseline:
            Person's historical communication baseline.

        Returns
        -------
        AnomalyResult with per-dimension deviations and overall score.
        """
        if baseline.message_count == 0:
            return AnomalyResult(anomaly_score=0.0)

        deviations: dict[str, float] = {}
        scores_dict = doc_scores.model_dump()

        for dim in _SENTIMENT_COLUMNS:
            doc_val = scores_dict.get(dim, 0.0)
            baseline_avg = baseline.tone_profile.get(dim, 0.0)
            deviation = abs(doc_val - baseline_avg) / max(baseline_avg, 0.1)
            deviations[dim] = round(deviation, 4)

        anomaly_score = min(max(deviations.values()), 1.0) if deviations else 0.0

        logger.info(
            "anomaly.computed",
            anomaly_score=anomaly_score,
            max_deviation_dim=max(deviations, key=deviations.get) if deviations else None,
        )
        return AnomalyResult(
            anomaly_score=round(anomaly_score, 4),
            deviations=deviations,
        )
