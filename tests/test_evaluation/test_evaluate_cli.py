"""Tests for the evaluation CLI script."""

from __future__ import annotations

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
