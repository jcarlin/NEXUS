"""Tests for adversarial dataset loading and validation."""

from __future__ import annotations

from evaluation.dataset import load_dataset
from evaluation.schemas import AdversarialCategory


class TestAdversarialDataset:
    def test_adversarial_dataset_loads(self) -> None:
        """All 4 categories load, validate, and match schema."""
        dataset = load_dataset()  # Uses default evaluation/data/ directory

        assert len(dataset.adversarial) == 4

        # All 4 categories are represented
        categories = {item.category for item in dataset.adversarial}
        assert categories == {
            AdversarialCategory.FALSE_PREMISE,
            AdversarialCategory.PRIVILEGE_TRICK,
            AdversarialCategory.AMBIGUOUS_ENTITY,
            AdversarialCategory.OVERTURNED_PRECEDENT,
        }

        # Each item has required fields
        for item in dataset.adversarial:
            assert item.id
            assert item.question
            assert item.expected_behavior
            assert isinstance(item.should_answer, bool)
