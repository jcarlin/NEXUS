"""Dataset adapters for bulk import.

Each adapter implements the ``DatasetAdapter`` protocol and yields
``ImportDocument`` instances from a specific data source format.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.ingestion.adapters.concordance_dat import ConcordanceDATAdapter
from app.ingestion.adapters.directory import DirectoryAdapter
from app.ingestion.adapters.edrm_xml import EDRMXMLAdapter
from app.ingestion.adapters.gdrive import GoogleDriveAdapter
from app.ingestion.adapters.huggingface_csv import HuggingFaceCSVAdapter

if TYPE_CHECKING:
    from app.ingestion.bulk_import import DatasetAdapter

# Registry mapping adapter name → class.  Used by the CLI orchestrator
# to look up adapters by the subcommand string.
ADAPTER_REGISTRY: dict[str, type[DatasetAdapter]] = {
    "directory": DirectoryAdapter,  # type: ignore[dict-item]
    "edrm_xml": EDRMXMLAdapter,  # type: ignore[dict-item]
    "concordance_dat": ConcordanceDATAdapter,  # type: ignore[dict-item]
    "huggingface_csv": HuggingFaceCSVAdapter,  # type: ignore[dict-item]
    "google_drive": GoogleDriveAdapter,  # type: ignore[dict-item]
}

__all__ = [
    "ADAPTER_REGISTRY",
    "ConcordanceDATAdapter",
    "DirectoryAdapter",
    "EDRMXMLAdapter",
    "GoogleDriveAdapter",
    "HuggingFaceCSVAdapter",
]
