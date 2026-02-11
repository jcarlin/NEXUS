"""Document parsing via Docling.

Routes files to the correct parser based on extension.
Extracts text, structure, and page images.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

# Extension -> parser backend mapping
PARSER_ROUTES: dict[str, str] = {
    # Docling handles these natively
    ".pdf": "docling",
    ".docx": "docling",
    ".xlsx": "docling",
    ".pptx": "docling",
    ".html": "docling",
    ".htm": "docling",
    ".png": "docling",
    ".jpg": "docling",
    ".jpeg": "docling",
    ".tiff": "docling",
    ".tif": "docling",
    # These are deferred to M3 (unstructured):
    ".eml": "unsupported",
    ".msg": "unsupported",
    ".rtf": "unsupported",
    ".txt": "plaintext",
    ".csv": "unsupported",
    ".doc": "unsupported",
    ".zip": "zip_extract",
}


@dataclass
class PageContent:
    """Content extracted from a single page of a document."""

    page_number: int
    text: str
    tables: list[str] = field(default_factory=list)  # Tables as markdown
    images: list[bytes] = field(default_factory=list)  # Raw image bytes


@dataclass
class ParseResult:
    """The output of parsing a single document."""

    text: str  # Full extracted text (markdown)
    pages: list[PageContent]  # Per-page content
    metadata: dict  # Doc metadata (title, author, dates, etc.)
    page_count: int


class DocumentParser:
    """Route documents to the correct parser backend and extract content.

    Currently supports:
    - Docling: PDF, DOCX, XLSX, PPTX, HTML, and image files.
    - Plaintext: .txt files (read directly).

    Other formats (EML, MSG, RTF, CSV, legacy DOC) are deferred to M3.
    """

    def __init__(self) -> None:
        self._converter = None  # Lazy-loaded Docling DocumentConverter

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, file_path: Path, filename: str) -> ParseResult:
        """Parse a document file and return structured content.

        Parameters
        ----------
        file_path:
            Absolute path to the file on disk (e.g. a temp download from MinIO).
        filename:
            Original filename — used to determine the file extension.

        Returns
        -------
        ParseResult with extracted text, per-page content, and metadata.

        Raises
        ------
        ValueError
            If the file extension is unsupported or not recognised.
        FileNotFoundError
            If *file_path* does not exist.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = Path(filename).suffix.lower()
        backend = PARSER_ROUTES.get(ext)

        if backend is None:
            raise ValueError(
                f"Unrecognised file extension '{ext}' for file '{filename}'. "
                f"Supported extensions: {sorted(PARSER_ROUTES.keys())}"
            )

        logger.info(
            "parser.routing",
            filename=filename,
            extension=ext,
            backend=backend,
        )

        if backend == "docling":
            return self._parse_with_docling(file_path, filename)
        if backend == "plaintext":
            return self._parse_plaintext(file_path, filename)
        if backend == "unsupported":
            raise ValueError(
                f"File format '{ext}' is not yet supported (scheduled for M3). "
                f"File: '{filename}'"
            )
        if backend == "zip_extract":
            raise ValueError(
                "ZIP extraction is not yet supported in the parser. "
                "Extract the archive first, then ingest individual files."
            )

        # Defensive fallback — should never reach here.
        raise ValueError(f"Unknown parser backend '{backend}' for extension '{ext}'")

    # ------------------------------------------------------------------
    # Docling backend
    # ------------------------------------------------------------------

    def _get_converter(self):
        """Lazily initialise the Docling DocumentConverter.

        The converter is heavyweight (loads models on first call),
        so we defer creation until the first document is actually parsed.
        """
        if self._converter is None:
            try:
                from docling.document_converter import DocumentConverter

                self._converter = DocumentConverter()
                logger.info("parser.docling.loaded")
            except Exception:
                logger.exception("parser.docling.load_failed")
                raise
        return self._converter

    def _parse_with_docling(self, file_path: Path, filename: str) -> ParseResult:
        """Parse a file using the Docling library.

        Docling's ``DocumentConverter.convert()`` returns a conversion result
        whose ``.document`` exposes the parsed content.  We extract the full
        markdown representation and attempt per-page iteration when available.
        """
        converter = self._get_converter()

        try:
            result = converter.convert(str(file_path))
        except Exception:
            logger.exception("parser.docling.convert_failed", filename=filename)
            raise

        doc = result.document

        # ----------------------------------------------------------
        # Full text as markdown
        # ----------------------------------------------------------
        try:
            text = doc.export_to_markdown()
        except Exception:
            logger.warning(
                "parser.docling.markdown_export_failed",
                filename=filename,
            )
            text = ""

        # ----------------------------------------------------------
        # Per-page content
        # ----------------------------------------------------------
        pages: list[PageContent] = []

        try:
            # Docling exposes pages via ``doc.pages`` (a dict keyed by page
            # number or a sequence — handle both).
            raw_pages = doc.pages
            if isinstance(raw_pages, dict):
                page_items = sorted(raw_pages.items(), key=lambda kv: kv[0])
                for idx, (_key, page) in enumerate(page_items, start=1):
                    page_text = self._extract_page_text(page)
                    tables = self._extract_page_tables(page)
                    pages.append(
                        PageContent(
                            page_number=idx,
                            text=page_text,
                            tables=tables,
                            images=[],
                        )
                    )
            else:
                # Iterable (list / tuple)
                for idx, page in enumerate(raw_pages, start=1):
                    page_text = self._extract_page_text(page)
                    tables = self._extract_page_tables(page)
                    pages.append(
                        PageContent(
                            page_number=idx,
                            text=page_text,
                            tables=tables,
                            images=[],
                        )
                    )
        except Exception:
            # Page-level iteration is best-effort; fall back to a single
            # page containing the full text.
            logger.debug(
                "parser.docling.page_iteration_unavailable",
                filename=filename,
            )

        # Fallback: if we got no pages, wrap the entire text in one page.
        if not pages:
            pages = [
                PageContent(page_number=1, text=text, tables=[], images=[])
            ]

        # ----------------------------------------------------------
        # Metadata
        # ----------------------------------------------------------
        metadata: dict = {"format": file_path.suffix.lower()}
        try:
            # Docling may expose name/title or other metadata on the document.
            if hasattr(doc, "name") and doc.name:
                metadata["title"] = doc.name
        except Exception:
            pass

        page_count = len(pages)

        logger.info(
            "parser.docling.success",
            filename=filename,
            page_count=page_count,
            text_length=len(text),
        )

        return ParseResult(
            text=text,
            pages=pages,
            metadata=metadata,
            page_count=page_count,
        )

    # ----------------------------------------------------------
    # Helpers for extracting page-level content from Docling
    # ----------------------------------------------------------

    @staticmethod
    def _extract_page_text(page) -> str:
        """Best-effort extraction of text from a Docling page object."""
        # Try common attribute / method names that Docling versions expose.
        for attr in ("text", "content"):
            val = getattr(page, attr, None)
            if isinstance(val, str) and val:
                return val
        # Some versions expose an export method.
        if callable(getattr(page, "export_to_markdown", None)):
            try:
                return page.export_to_markdown()
            except Exception:
                pass
        return ""

    @staticmethod
    def _extract_page_tables(page) -> list[str]:
        """Best-effort extraction of tables (as markdown) from a Docling page."""
        tables: list[str] = []
        raw = getattr(page, "tables", None)
        if raw is None:
            return tables
        try:
            for table in raw:
                if callable(getattr(table, "export_to_markdown", None)):
                    tables.append(table.export_to_markdown())
                elif hasattr(table, "text") and isinstance(table.text, str):
                    tables.append(table.text)
        except Exception:
            pass
        return tables

    # ------------------------------------------------------------------
    # Plaintext backend
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_plaintext(file_path: Path, filename: str) -> ParseResult:
        """Read a plain-text file and wrap it in a ParseResult."""
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Fall back to latin-1 which never raises on byte values.
            text = file_path.read_text(encoding="latin-1")

        logger.info(
            "parser.plaintext.success",
            filename=filename,
            text_length=len(text),
        )

        return ParseResult(
            text=text,
            pages=[PageContent(page_number=1, text=text, tables=[], images=[])],
            metadata={"format": ".txt"},
            page_count=1,
        )
