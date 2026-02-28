#!/usr/bin/env python3
"""NEXUS Evaluation CLI.

Usage:
    python scripts/evaluate.py --dry-run           # Synthetic data, no infra needed
    python scripts/evaluate.py --output results.json  # Full run, save results
    python scripts/evaluate.py --skip-ragas        # Full run, skip RAGAS metrics
    python scripts/evaluate.py --verbose           # Extra logging
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the project root is on sys.path so evaluation/ is importable
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from evaluation.runner import run_dry  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="NEXUS Evaluation Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run with synthetic data (no infrastructure required)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to write JSON results",
    )
    parser.add_argument(
        "--skip-ragas",
        action="store_true",
        help="Skip RAGAS metrics (full mode only)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.dry_run:
        result = run_dry(verbose=args.verbose)
    else:
        # Full mode requires asyncio
        import asyncio

        from evaluation.runner import run_full

        try:
            result = asyncio.run(run_full(skip_ragas=args.skip_ragas, verbose=args.verbose))
        except NotImplementedError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    # Output results
    result_json = result.model_dump_json(indent=2)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(result_json)
        print(f"Results written to {output_path}")
    else:
        print(result_json)

    # Exit code based on quality gates
    if not result.passed:
        print(f"\nQuality gate FAILED: {result.gate_failures}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
