"""Tests for evaluation dataset loading and validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.dataset import load_dataset, validate_dataset_file
from evaluation.schemas import GroundTruthItem


class TestLoadDataset:
    """Test that the dataset loader validates schemas correctly."""

    def test_load_ground_truth_validates_schema(self, tmp_path: Path) -> None:
        """Loader parses valid JSON, rejects malformed, validates Pydantic."""
        # Valid items load successfully
        valid_items = [
            {
                "id": "gt-001",
                "question": "What is the main claim?",
                "expected_answer": "Breach of contract.",
                "category": "factual",
                "difficulty": "easy",
                "expected_documents": ["complaint.pdf"],
            }
        ]
        gt_path = tmp_path / "ground_truth.json"
        gt_path.write_text(json.dumps(valid_items))

        # Also create empty adversarial and legalbench files
        (tmp_path / "adversarial.json").write_text("[]")
        (tmp_path / "legalbench.json").write_text("[]")

        dataset = load_dataset(data_dir=tmp_path)
        assert len(dataset.ground_truth) == 1
        assert dataset.ground_truth[0].id == "gt-001"
        assert dataset.ground_truth[0].category == "factual"

        # Invalid items raise ValidationError
        invalid_items = [{"id": "bad", "question": "no other fields"}]
        gt_path.write_text(json.dumps(invalid_items))
        with pytest.raises(Exception):  # ValidationError
            load_dataset(data_dir=tmp_path)

        # Missing data dir raises FileNotFoundError
        with pytest.raises(FileNotFoundError):
            load_dataset(data_dir=tmp_path / "nonexistent")

        # Validate function reports errors on bad items
        bad_path = tmp_path / "bad.json"
        bad_path.write_text(json.dumps(invalid_items))
        errors = validate_dataset_file(bad_path, GroundTruthItem)
        assert len(errors) > 0

        # Validate function returns empty on good items
        good_path = tmp_path / "good.json"
        good_path.write_text(json.dumps(valid_items))
        errors = validate_dataset_file(good_path, GroundTruthItem)
        assert len(errors) == 0
