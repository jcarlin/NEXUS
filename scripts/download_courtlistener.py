#!/usr/bin/env python3
"""Download court documents from the CourtListener RECAP archive.

Fetches PDF filings for a given docket via the CourtListener REST API v3
and saves them to a local directory. Supports resume (skips existing files),
pagination, rate limiting, and optional API token authentication.

Default target: Giuffre v. Maxwell (docket ID 4355835).

Usage::

    # Download all available PDFs for Giuffre v. Maxwell
    python scripts/download_courtlistener.py \\
        --docket-id 4355835 \\
        --output-dir /tmp/courtlistener_docs

    # Download first 10 documents only
    python scripts/download_courtlistener.py \\
        --docket-id 4355835 \\
        --output-dir /tmp/courtlistener_docs \\
        --limit 10

    # With API token (higher rate limits)
    python scripts/download_courtlistener.py \\
        --docket-id 4355835 \\
        --output-dir /tmp/courtlistener_docs \\
        --api-token YOUR_TOKEN

Fallback sources (manual download):
    If the CourtListener API is unavailable or rate-limited, PDFs for the
    Giuffre v. Maxwell case can also be sourced from:
    - Public Intelligence: batches 1-8 of unsealed documents
      https://publicintelligence.net/giuffre-v-maxwell/
    - The Guardian / Newsweek consolidated PDF downloads
    - RECAP Archive direct browser at https://www.courtlistener.com/docket/4355835/
    These would need to be downloaded manually and placed in the output directory.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import httpx

_BASE_API = "https://www.courtlistener.com/api/rest/v3"
_STORAGE_BASE = "https://storage.courtlistener.com"


def _slugify(text: str, max_len: int = 60) -> str:
    """Sanitize a description into a safe filename slug.

    Lowercase, replace spaces/special chars with hyphens, strip leading/trailing
    hyphens, and truncate to ``max_len`` characters.
    """
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:max_len].rstrip("-")


def _build_filename(
    docket_entry_number: int | str,
    document_number: int | str,
    description: str,
) -> str:
    """Build a PDF filename from docket entry number, document number, and description."""
    slug = _slugify(description) if description else "untitled"
    return f"{docket_entry_number}_{document_number}_{slug}.pdf"


def _fetch_document_list(
    client: httpx.Client,
    docket_id: int,
    limit: int | None,
) -> list[dict]:
    """Fetch all RECAP documents for a docket, handling pagination.

    Returns a list of document metadata dicts from the CourtListener API.
    """
    documents: list[dict] = []
    url: str | None = f"{_BASE_API}/recap-documents/?docket_entry__docket={docket_id}&is_available=true&page_size=100"

    page = 1
    while url:
        print(f"Fetching document list page {page}...")
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        documents.extend(results)

        if limit and len(documents) >= limit:
            documents = documents[:limit]
            break

        url = data.get("next")
        page += 1

        if url:
            time.sleep(1)  # rate-limit: 1 req/s

    return documents


def _download_pdf(
    client: httpx.Client,
    filepath_local: str,
    dest: Path,
) -> int | None:
    """Download a single PDF from CourtListener storage.

    Returns the file size in bytes if successful, or None if the download
    was skipped (non-PDF content type, HTTP error, etc.).
    """
    if filepath_local.startswith("http"):
        download_url = filepath_local
    else:
        download_url = f"{_STORAGE_BASE}/{filepath_local.lstrip('/')}"

    resp = client.get(download_url, follow_redirects=True)

    if resp.status_code in (403, 404):
        print(f"  WARNING: HTTP {resp.status_code} for {download_url} — skipping (may be behind PACER paywall)")
        return None

    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")
    if "application/pdf" not in content_type:
        print(f"  WARNING: Non-PDF content-type '{content_type}' — skipping")
        return None

    dest.write_bytes(resp.content)
    return len(resp.content)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download court documents from the CourtListener RECAP archive",
    )
    parser.add_argument(
        "--docket-id",
        type=int,
        default=4355835,
        help="CourtListener docket ID (default: 4355835 = Giuffre v. Maxwell)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory to save downloaded PDFs",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of documents to download (default: all)",
    )
    parser.add_argument(
        "--api-token",
        default=None,
        help="CourtListener API token for higher rate limits (free to register)",
    )
    args = parser.parse_args()

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    headers: dict[str, str] = {
        "User-Agent": "NEXUS-Legal-Research/1.0 (https://github.com/nexus-legal)",
    }
    if args.api_token:
        headers["Authorization"] = f"Token {args.api_token}"

    print(f"Docket ID:   {args.docket_id}")
    print(f"Output dir:  {output_dir}")
    if args.limit:
        print(f"Limit:       {args.limit}")
    print()

    with httpx.Client(headers=headers, timeout=60.0) as client:
        # Phase 1: Fetch document list
        try:
            documents = _fetch_document_list(client, args.docket_id, args.limit)
        except httpx.HTTPStatusError as exc:
            print(f"ERROR: Failed to fetch document list: {exc}", file=sys.stderr)
            return 1

        total = len(documents)
        print(f"\nFound {total} available documents\n")

        if total == 0:
            print("No documents to download.")
            return 0

        # Phase 2: Download PDFs
        downloaded = 0
        skipped_existing = 0
        skipped_error = 0
        total_bytes = 0
        total_pages = 0

        for i, doc in enumerate(documents, 1):
            filepath_local = doc.get("filepath_local", "")
            if not filepath_local:
                print(f"  [{i}/{total}] No filepath_local — skipping")
                skipped_error += 1
                continue

            docket_entry_number = doc.get("docket_entry", {})
            # The API nests docket_entry as a URL; use document_number as primary identifier
            document_number = doc.get("document_number", i)
            description = doc.get("description", "")
            page_count = doc.get("page_count") or 0

            # Extract docket entry number from the docket_entry URL if available
            # URL format: https://www.courtlistener.com/api/rest/v3/docket-entries/XXXXX/
            entry_number = document_number
            if isinstance(docket_entry_number, str) and "/docket-entries/" in docket_entry_number:
                match = re.search(r"/docket-entries/(\d+)/", docket_entry_number)
                if match:
                    entry_number = match.group(1)

            filename = _build_filename(entry_number, document_number, description)
            dest = output_dir / filename

            if dest.exists():
                skipped_existing += 1
                total_pages += page_count
                total_bytes += dest.stat().st_size
                print(f"  [{i}/{total}] Already exists: {filename}")
                continue

            try:
                size = _download_pdf(client, filepath_local, dest)
            except httpx.HTTPError as exc:
                print(f"  [{i}/{total}] WARNING: Download failed: {exc}")
                skipped_error += 1
                continue

            if size is None:
                skipped_error += 1
                continue

            downloaded += 1
            total_bytes += size
            total_pages += page_count
            size_kb = size / 1024

            print(f"  Downloaded {downloaded}/{total}: {filename} ({page_count} pages, {size_kb:.0f} KB)")

            # Rate limit between downloads
            if i < total:
                time.sleep(1)

    # Summary
    print("\n--- Download Summary ---")
    print(f"Total available:   {total}")
    print(f"Downloaded:        {downloaded}")
    print(f"Already existed:   {skipped_existing}")
    print(f"Skipped (errors):  {skipped_error}")
    print(f"Total pages:       {total_pages:,}")
    print(f"Total size:        {total_bytes / 1024 / 1024:.1f} MB")
    print(f"Output directory:  {output_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
