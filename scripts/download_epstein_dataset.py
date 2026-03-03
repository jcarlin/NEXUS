#!/usr/bin/env python3
"""Download the Epstein Files dataset from HuggingFace.

Saves as Parquet for efficient import via ``HuggingFaceCSVAdapter``.

Usage::

    # Default: teyler/epstein-files-20k (open access, no auth)
    python scripts/download_epstein_dataset.py --output-dir ./data/epstein

    # Alternative: tensonaut/EPSTEIN_FILES_20K (may need HF_TOKEN)
    python scripts/download_epstein_dataset.py --source tensonaut --output-dir ./data/epstein
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SOURCES = {
    "teyler": "teyler/epstein-files-20k",
    "tensonaut": "tensonaut/EPSTEIN_FILES_20K",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Epstein Files dataset from HuggingFace")
    parser.add_argument(
        "--source",
        choices=list(_SOURCES.keys()),
        default="teyler",
        help="HuggingFace dataset source (default: teyler)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./data/epstein"),
        help="Output directory for downloaded dataset",
    )
    args = parser.parse_args()

    repo_id = _SOURCES[args.source]
    output_dir: Path = args.output_dir

    try:
        from datasets import load_dataset
    except ImportError:
        print("Error: 'datasets' library required. Install with: pip install datasets", file=sys.stderr)
        return 1

    print(f"Downloading dataset: {repo_id}")
    print(f"Output directory:    {output_dir}")

    ds = load_dataset(repo_id, split="train")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "epstein_files_20k.parquet"

    print("Converting to Parquet...")
    ds.to_parquet(str(output_path))

    # Print summary
    print("\n--- Download Summary ---")
    print(f"Rows:           {len(ds):,}")
    print(f"Columns:        {ds.column_names}")
    print(f"Output file:    {output_path}")
    print(f"File size:      {output_path.stat().st_size / 1024 / 1024:.1f} MB")

    # Distribution stats
    text_rows = sum(1 for row in ds if str(row.get("filename", "")).startswith("TEXT/"))
    image_rows = sum(1 for row in ds if str(row.get("filename", "")).startswith("IMAGES/"))
    other_rows = len(ds) - text_rows - image_rows

    print("\nDistribution:")
    print(f"  TEXT/:    {text_rows:,}")
    print(f"  IMAGES/: {image_rows:,}")
    if other_rows:
        print(f"  Other:   {other_rows:,}")

    # Text length stats for TEXT/ rows only
    text_lengths = [len(str(row.get("text", ""))) for row in ds if str(row.get("filename", "")).startswith("TEXT/")]
    if text_lengths:
        text_lengths.sort()
        total_chars = sum(text_lengths)
        print("\nText length stats (TEXT/ rows):")
        print(f"  Total chars:  {total_chars:,}")
        print(f"  Mean:         {total_chars // len(text_lengths):,}")
        print(f"  Median:       {text_lengths[len(text_lengths) // 2]:,}")
        print(f"  Min:          {text_lengths[0]:,}")
        print(f"  Max:          {text_lengths[-1]:,}")

    print("\nDone! Import with:")
    print("  python scripts/import_dataset.py huggingface_csv \\")
    print(f"      --file {output_path} \\")
    print("      --matter-id <MATTER_UUID> --dry-run")

    return 0


if __name__ == "__main__":
    sys.exit(main())
