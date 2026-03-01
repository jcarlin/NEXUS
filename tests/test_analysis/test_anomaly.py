"""Tests for CommunicationBaseline anomaly detection."""

from __future__ import annotations

from app.analysis.anomaly import CommunicationBaseline
from app.analysis.schemas import AnomalyResult, PersonBaseline, SentimentDimensions


def test_normal_doc_scores_low_anomaly():
    """Document close to baseline scores low anomaly."""
    baseline = PersonBaseline(
        avg_message_length=500.0,
        message_count=50,
        tone_profile={
            "positive": 0.3,
            "negative": 0.1,
            "pressure": 0.1,
            "opportunity": 0.05,
            "rationalization": 0.05,
            "intent": 0.05,
            "concealment": 0.05,
        },
    )
    doc_scores = SentimentDimensions(
        positive=0.32,
        negative=0.12,
        pressure=0.08,
        opportunity=0.06,
        rationalization=0.04,
        intent=0.06,
        concealment=0.04,
    )

    result = CommunicationBaseline.compute_anomaly_score(doc_scores, baseline)

    assert isinstance(result, AnomalyResult)
    assert result.anomaly_score < 0.3


def test_deviation_scores_high_anomaly():
    """Document far from baseline scores high anomaly."""
    baseline = PersonBaseline(
        avg_message_length=500.0,
        message_count=50,
        tone_profile={
            "positive": 0.3,
            "negative": 0.1,
            "pressure": 0.1,
            "opportunity": 0.05,
            "rationalization": 0.05,
            "intent": 0.05,
            "concealment": 0.05,
        },
    )
    doc_scores = SentimentDimensions(
        positive=0.1,
        negative=0.8,
        pressure=0.9,
        opportunity=0.7,
        rationalization=0.8,
        intent=0.9,
        concealment=0.85,
    )

    result = CommunicationBaseline.compute_anomaly_score(doc_scores, baseline)

    assert isinstance(result, AnomalyResult)
    assert result.anomaly_score > 0.7
