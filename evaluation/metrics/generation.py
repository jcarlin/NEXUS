"""Generation quality metrics via RAGAS.

Wraps RAGAS faithfulness, answer_relevancy, and context_precision metrics.
Only used in full evaluation mode — dry-run returns synthetic scores.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


async def compute_ragas_metrics(
    question: str,
    answer: str,
    contexts: list[str],
    ground_truth_answer: str,
) -> dict[str, float]:
    """Compute RAGAS metrics for a single Q&A pair.

    Returns dict with keys: faithfulness, answer_relevancy, context_precision.

    Requires ``ragas``, ``datasets``, ``langchain-anthropic``, and
    ``langchain-openai`` packages. If unavailable, raises ``ImportError``.
    """
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, context_precision, faithfulness
    except ImportError as exc:
        raise ImportError(
            "RAGAS dependencies not installed. "
            "Install with: uv pip install -e '.[dev]' ragas datasets langchain-anthropic langchain-openai"
        ) from exc

    # RAGAS expects a HuggingFace Dataset
    data = {
        "question": [question],
        "answer": [answer],
        "contexts": [contexts],
        "ground_truth": [ground_truth_answer],
    }
    dataset = Dataset.from_dict(data)

    try:
        result = evaluate(
            dataset,
            metrics=[faithfulness, answer_relevancy, context_precision],
        )
        return {
            "faithfulness": float(result["faithfulness"]),
            "answer_relevancy": float(result["answer_relevancy"]),
            "context_precision": float(result["context_precision"]),
        }
    except Exception:
        logger.exception("ragas.evaluation_failed")
        raise
