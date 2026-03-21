#!/usr/bin/env python3
"""Download FBI FOIA Vault documents for the Jeffrey Epstein case.

Fetches all PDF documents from the FBI Vault's Jeffrey Epstein release,
organized into parts. Supports resume (skips existing files) and rate
limiting to be respectful of the government server.

Usage::

    # Download all parts
    python scripts/download_fbi_vault.py --output-dir /tmp/fbi_vault_docs

    # Download only the first 3 parts
    python scripts/download_fbi_vault.py --output-dir /tmp/fbi_vault_docs --limit 3
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

import httpx

_BASE_URL = "https://vault.fbi.gov"
_INDEX_URL = f"{_BASE_URL}/jeffrey-epstein"
_USER_AGENT = "NEXUS-Downloader/1.0"
_REQUEST_DELAY_SECONDS = 1


class _LinkParser(HTMLParser):
    """Extract <a> tag hrefs from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.links.append(value)


def _fetch_page(client: httpx.Client, url: str) -> str | None:
    """Fetch a page and return its text content, or None on error."""
    try:
        resp = client.get(url, follow_redirects=True, timeout=30.0)
        resp.raise_for_status()
        return resp.text
    except httpx.HTTPError as exc:
        print(f"  WARNING: Failed to fetch {url}: {exc}", file=sys.stderr)
        return None


def _extract_links(html: str) -> list[str]:
    """Parse HTML and return all href values from <a> tags."""
    parser = _LinkParser()
    parser.feed(html)
    return parser.links


def _find_part_links(html: str) -> list[tuple[int, str]]:
    """Find part links from the index page.

    Returns a sorted list of (part_number, url) tuples.
    """
    links = _extract_links(html)
    parts: dict[int, str] = {}

    # Match patterns like:
    #   /jeffrey-epstein/jeffrey-epstein-part-01-of-22/view
    #   /jeffrey-epstein/Jeffrey%20Epstein%20Part%2001/view
    #   Jeffrey Epstein Part 01 (after URL-decoding)
    part_pattern = re.compile(r"(?:jeffrey[- ]epstein[- ])?part[- ]?(\d+)", re.IGNORECASE)

    for href in links:
        # URL-decode before matching so %20 → space
        decoded = unquote(href)
        match = part_pattern.search(decoded)
        if match:
            part_num = int(match.group(1))
            # Normalize the URL
            if href.startswith("/"):
                url = f"{_BASE_URL}{href}"
            elif href.startswith("http"):
                url = href
            else:
                url = f"{_INDEX_URL}/{href}"

            # Keep the longest/most specific URL for each part
            if part_num not in parts or len(url) > len(parts[part_num]):
                parts[part_num] = url

    return sorted(parts.items())


def _find_pdf_links(html: str, part_url: str) -> list[str]:
    """Find PDF download links from a part page.

    Looks for hrefs ending in .pdf or containing /at_download/file.
    """
    links = _extract_links(html)
    pdf_urls: list[str] = []

    for href in links:
        is_pdf = href.lower().endswith(".pdf") or "/at_download/file" in href

        if not is_pdf:
            continue

        # Normalize URL
        if href.startswith("/"):
            url = f"{_BASE_URL}{href}"
        elif href.startswith("http"):
            url = href
        else:
            # Relative to the part page
            base = part_url.rstrip("/")
            url = f"{base}/{href}"

        if url not in pdf_urls:
            pdf_urls.append(url)

    return pdf_urls


def _download_file(client: httpx.Client, url: str, dest: Path) -> int | None:
    """Download a file to dest. Returns file size in bytes, or None on error."""
    try:
        with client.stream("GET", url, follow_redirects=True, timeout=120.0) as resp:
            resp.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)
        return dest.stat().st_size
    except httpx.HTTPError as exc:
        print(f"  WARNING: Failed to download {url}: {exc}", file=sys.stderr)
        # Clean up partial download
        if dest.exists():
            dest.unlink()
        return None


def _filename_from_url(url: str, part_num: int, index: int) -> str:
    """Derive a filename from a URL, falling back to a generated name."""
    # Try to extract a meaningful filename from the URL path
    path = url.rstrip("/").split("/")[-1]
    path = path.split("?")[0]  # Strip query params

    if path.lower().endswith(".pdf"):
        return path

    # For /at_download/file style URLs, generate a name
    return f"jeffrey-epstein-part-{part_num:02d}-{index:02d}.pdf"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download FBI FOIA Vault documents for the Jeffrey Epstein case",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for downloaded PDFs",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit to first N parts (default: all)",
    )
    args = parser.parse_args()

    output_dir: Path = args.output_dir

    headers = {"User-Agent": _USER_AGENT}
    client = httpx.Client(headers=headers)

    # Step 1: Fetch index page
    print(f"Fetching index page: {_INDEX_URL}")
    index_html = _fetch_page(client, _INDEX_URL)
    if index_html is None:
        print("ERROR: Could not fetch index page.", file=sys.stderr)
        return 1

    # Step 2: Parse part links
    parts = _find_part_links(index_html)
    if not parts:
        print("WARNING: No part links found on index page.", file=sys.stderr)
        print("Index page links found:", file=sys.stderr)
        for link in _extract_links(index_html):
            if "epstein" in link.lower():
                print(f"  {link}", file=sys.stderr)
        return 1

    total_parts = len(parts)
    if args.limit:
        parts = parts[: args.limit]

    print(f"Found {total_parts} parts, downloading {len(parts)}")
    print()

    # Step 3: Download each part
    total_files = 0
    total_bytes = 0
    skipped_files = 0

    for part_num, part_url in parts:
        part_dir = output_dir / f"part_{part_num}"

        # Ensure we fetch the /view page for PDF links
        view_url = part_url.rstrip("/")
        if not view_url.endswith("/view"):
            view_url = f"{view_url}/view"

        print(f"[Part {part_num}/{total_parts}] Fetching: {view_url}")
        time.sleep(_REQUEST_DELAY_SECONDS)

        part_html = _fetch_page(client, view_url)
        if part_html is None:
            # Try the URL without /view as fallback
            print(f"  Retrying without /view: {part_url}")
            time.sleep(_REQUEST_DELAY_SECONDS)
            part_html = _fetch_page(client, part_url)
            if part_html is None:
                print(f"  WARNING: Skipping part {part_num} — could not fetch page.", file=sys.stderr)
                continue

        # Find PDF links
        pdf_urls = _find_pdf_links(part_html, part_url)

        if not pdf_urls:
            # Try the /at_download/file pattern directly
            direct_url = f"{part_url.rstrip('/')}/at_download/file"
            print(f"  No PDF links found on page. Trying direct download: {direct_url}")
            pdf_urls = [direct_url]

        print(f"  Found {len(pdf_urls)} PDF link(s)")
        for url in pdf_urls:
            print(f"    {url}")

        # Download each PDF
        for idx, pdf_url in enumerate(pdf_urls, start=1):
            filename = _filename_from_url(pdf_url, part_num, idx)
            dest = part_dir / filename

            if dest.exists():
                size = dest.stat().st_size
                print(f"  SKIP (exists): {filename} ({size / 1024:.0f} KB)")
                skipped_files += 1
                total_bytes += size
                total_files += 1
                continue

            time.sleep(_REQUEST_DELAY_SECONDS)
            size = _download_file(client, pdf_url, dest)

            if size is not None:
                total_files += 1
                total_bytes += size
                print(f"  Downloaded: {filename} ({size / 1024:.0f} KB)")
            else:
                print(f"  FAILED: {filename}")

        print()

    client.close()

    # Summary
    print("--- Download Summary ---")
    print(f"Parts processed: {len(parts)}")
    print(f"Total files:     {total_files}")
    print(f"Skipped (exist): {skipped_files}")
    print(f"Total size:      {total_bytes / 1024 / 1024:.1f} MB")
    print(f"Output dir:      {output_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
