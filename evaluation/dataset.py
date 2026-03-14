"""Load and validate evaluation datasets from JSON files."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from evaluation.schemas import (
    AdversarialItem,
    EvaluationDataset,
    GroundTruthItem,
    LegalBenchItem,
)

DATA_DIR = Path(__file__).parent / "data"


def load_dataset(data_dir: Path | None = None) -> EvaluationDataset:
    """Load all dataset files from *data_dir* and return a validated dataset.

    Raises ``ValidationError`` if any item fails schema validation.
    Raises ``FileNotFoundError`` if the data directory is missing.
    """
    root = data_dir or DATA_DIR
    if not root.is_dir():
        raise FileNotFoundError(f"Evaluation data directory not found: {root}")

    ground_truth: list[GroundTruthItem] = []
    adversarial: list[AdversarialItem] = []
    legalbench: list[LegalBenchItem] = []

    gt_path = root / "ground_truth.json"
    if gt_path.exists():
        raw = json.loads(gt_path.read_text())
        # Support both list format and dict-with-version format
        if isinstance(raw, dict):
            gt_items = raw.get("ground_truth", [])
        else:
            gt_items = raw
        ground_truth = [GroundTruthItem.model_validate(item) for item in gt_items]

    adv_path = root / "adversarial.json"
    if adv_path.exists():
        raw = json.loads(adv_path.read_text())
        adversarial = [AdversarialItem.model_validate(item) for item in raw]

    lb_path = root / "legalbench.json"
    if lb_path.exists():
        raw = json.loads(lb_path.read_text())
        legalbench = [LegalBenchItem.model_validate(item) for item in raw]

    return EvaluationDataset(
        ground_truth=ground_truth,
        adversarial=adversarial,
        legalbench=legalbench,
    )


def validate_dataset_file(path: Path, item_type: type) -> list[str]:
    """Validate a single JSON dataset file. Returns a list of error messages."""
    errors: list[str] = []
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return [f"Invalid JSON: {exc}"]

    # Support both list format and dict-with-version format
    if isinstance(raw, dict):
        raw = raw.get("ground_truth", raw.get("adversarial", raw.get("legalbench", [])))
    if not isinstance(raw, list):
        return ["Expected a JSON array at top level (or dict with 'ground_truth' key)"]

    for i, item in enumerate(raw):
        try:
            item_type.model_validate(item)
        except ValidationError as exc:
            errors.append(f"Item {i}: {exc}")

    return errors
