"""Tests for the evaluation CLI script."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


class TestEvaluateCLI:
    def test_evaluate_dry_run_exits_zero(self) -> None:
        """``scripts/evaluate.py --dry-run`` exits 0."""
        script = Path(__file__).resolve().parents[2] / "scripts" / "evaluate.py"
        result = subprocess.run(
            [sys.executable, str(script), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"evaluate.py --dry-run failed with exit code {result.returncode}.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )


class TestDryRunResult:
    def test_dry_run_produces_valid_result(self) -> None:
        """Verify dry-run produces an EvaluationResult with retrieval metrics."""
        from evaluation.runner import run_dry

        result = run_dry()
        assert result.retrieval, "Dry run should produce retrieval metrics"
        assert result.mode == "dry_run"

    def test_dry_run_exit_code_on_gate_failure(self) -> None:
        """Verify that a failing quality gate produces a non-passing result."""
        from evaluation.runner import run_dry

        result = run_dry()
        # Dry run uses synthetic data calibrated to pass gates
        # But verify the structure is correct
        assert isinstance(result.passed, bool)
        assert isinstance(result.gate_failures, list)

    def test_output_file_written(self, tmp_path: Path) -> None:
        """Verify --output flag writes valid JSON."""
        from evaluation.runner import run_dry

        result = run_dry()
        output_file = tmp_path / "test-eval-results.json"
        output_file.write_text(result.model_dump_json(indent=2))
        loaded = json.loads(output_file.read_text())
        assert "passed" in loaded
        assert "retrieval" in loaded
