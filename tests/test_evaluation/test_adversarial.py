"""Tests for adversarial dataset loading and validation."""

from __future__ import annotations

from evaluation.dataset import load_dataset
from evaluation.schemas import AdversarialCategory


class TestAdversarialDataset:
    def test_adversarial_dataset_loads(self) -> None:
        """All 27 items load, validate, and match schema."""
        dataset = load_dataset()

        assert len(dataset.adversarial) == 27

        # Each item has required fields
        for item in dataset.adversarial:
            assert item.id
            assert item.question
            assert item.expected_behavior
            assert isinstance(item.should_answer, bool)

    def test_all_categories_represented(self) -> None:
        """All 9 AdversarialCategory values are present in the dataset."""
        dataset = load_dataset()
        categories = {item.category for item in dataset.adversarial}
        expected = set(AdversarialCategory)
        assert (
            categories == expected
        ), f"Missing categories: {expected - categories}, extra categories: {categories - expected}"

    def test_adversarial_items_valid(self) -> None:
        """Every adversarial item has a non-empty expected_behavior."""
        dataset = load_dataset()
        for item in dataset.adversarial:
            assert item.expected_behavior.strip(), f"Item {item.id} has empty expected_behavior"
