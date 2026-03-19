#!/usr/bin/env python3
"""Download any HuggingFace dataset and save as Parquet with schema inspection.

Generic downloader that works with any HF dataset. Prints column types,
sample values, null counts, and embedding dimensions if present.

Usage::

    # Download FBI files dataset (3.31 GB)
    python scripts/download_hf_dataset.py --dataset svetfm/epstein-fbi-files

    # Download House Oversight pre-embedded (357 MB)
    python scripts/download_hf_dataset.py --dataset svetfm/epstein-files-nov11-25-house-post-ocr-embeddings

    # Sample first 100 rows for local testing
    python scripts/download_hf_dataset.py --dataset svetfm/epstein-fbi-files --sample 100

    # Custom output directory
    python scripts/download_hf_dataset.py --dataset svetfm/epstein-fbi-files --output-dir ./data/fbi
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _slugify(repo_id: str) -> str:
    """Convert 'owner/dataset-name' to 'dataset_name' for filenames."""
    name = repo_id.split("/")[-1]
    return name.replace("-", "_").lower()


def _inspect_schema(ds) -> None:
    """Print detailed schema information for the dataset."""
    print("\n--- Schema Inspection ---")
    print(f"Rows:    {len(ds):,}")
    print(f"Columns: {ds.column_names}")
    print("Features:")
    for col_name, feat in ds.features.items():
        print(f"  {col_name}: {feat}")

    # Null counts
    print("\nNull/empty counts:")
    for col in ds.column_names:
        sample = ds[:100][col]
        nulls = sum(1 for v in sample if v is None or (isinstance(v, str) and not v.strip()))
        print(f"  {col}: {nulls}/100 in sample")

    # Sample values (first row)
    print("\nFirst row sample:")
    row = ds[0]
    for col in ds.column_names:
        val = row[col]
        if isinstance(val, list) and len(val) > 5:
            print(f"  {col}: [{val[0]:.4f}, {val[1]:.4f}, ...] (len={len(val)})")
        elif isinstance(val, str) and len(val) > 120:
            print(f"  {col}: {val[:120]}...")
        else:
            print(f"  {col}: {val}")

    # Detect embedding columns
    row = ds[0]
    for col in ds.column_names:
        val = row[col]
        if isinstance(val, list) and len(val) > 50 and isinstance(val[0], float):
            print(f"\nEmbedding column detected: '{col}' (dimensions={len(val)})")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download a HuggingFace dataset and save as Parquet",
    )
    parser.add_argument(
        "--dataset",
        required=True,
        help="HuggingFace dataset repo ID (e.g., svetfm/epstein-fbi-files)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: ./data/{dataset_slug})",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Download only first N rows (for local testing)",
    )
    parser.add_argument(
        "--split",
        default="train",
        help="Dataset split to download (default: train)",
    )
    parser.add_argument(
        "--inspect-only",
        action="store_true",
        help="Print schema info without saving to disk",
    )
    args = parser.parse_args()

    try:
        from datasets import load_dataset
    except ImportError:
        print("Error: 'datasets' library required. Install with: pip install datasets", file=sys.stderr)
        return 1

    slug = _slugify(args.dataset)
    output_dir = args.output_dir or Path(f"./data/{slug}")

    print(f"Dataset:    {args.dataset}")
    print(f"Split:      {args.split}")
    if args.sample:
        print(f"Sample:     first {args.sample} rows")

    # Download
    print("Downloading...")
    if args.sample:
        ds = load_dataset(args.dataset, split=f"{args.split}[:{args.sample}]")
    else:
        ds = load_dataset(args.dataset, split=args.split)

    # Schema inspection
    _inspect_schema(ds)

    if args.inspect_only:
        print("\n(inspect-only mode, not saving)")
        return 0

    # Save to Parquet
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{slug}.parquet"

    print(f"\nSaving to: {output_path}")
    ds.to_parquet(str(output_path))

    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"File size:  {size_mb:.1f} MB")
    print(f"\nDone! {len(ds):,} rows saved to {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
