"""Document parsing via Docling and lightweight format-specific parsers.

Routes files to the correct parser based on extension.
Extracts text, structure, and page images.
"""

from __future__ import annotations

import csv
import email
import email.policy
import io
import re
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
    # M3: Email formats
    ".eml": "eml",
    ".msg": "msg",
    # M3: Data / text formats
    ".csv": "csv",
    ".tsv": "csv",
    ".rtf": "rtf",
    # Plaintext
    ".txt": "plaintext",
    # Legacy Word — needs libreoffice, not supported
    ".doc": "unsupported",
    # ZIP: handled by task layer, not parser
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
    - EML: RFC 822 email files (stdlib email.parser).
    - MSG: Outlook .msg files (extract-msg library).
    - CSV/TSV: Tabular data rendered as markdown tables.
    - RTF: Rich Text Format (striprtf library).

    Other formats (legacy DOC) are not yet supported.
    """

    def __init__(self) -> None:
        self._converters: dict[str, object] = {}  # "ocr" and "no_ocr" cached separately

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
        if backend == "eml":
            return self._parse_eml(file_path, filename)
        if backend == "msg":
            return self._parse_msg(file_path, filename)
        if backend == "csv":
            return self._parse_csv(file_path, filename)
        if backend == "rtf":
            return self._parse_rtf(file_path, filename)
        if backend == "unsupported":
            raise ValueError(f"File format '{ext}' is not supported. File: '{filename}'")
        if backend == "zip_extract":
            raise ValueError(
                "ZIP files are handled by the task layer, not the parser. "
                "Use process_document or process_zip tasks instead."
            )

        # Defensive fallback — should never reach here.
        raise ValueError(f"Unknown parser backend '{backend}' for extension '{ext}'")

    # ------------------------------------------------------------------
    # Docling backend
    # ------------------------------------------------------------------

    def _get_converter(self, with_ocr: bool = False):
        """Lazily initialise a Docling DocumentConverter for the given OCR mode.

        Two converters are cached separately (``"ocr"`` and ``"no_ocr"``) so
        that the heavyweight OCR ONNX models are only loaded when a document
        actually needs them.
        """
        key = "ocr" if with_ocr else "no_ocr"
        if key not in self._converters:
            try:
                from docling.datamodel.base_models import InputFormat
                from docling.datamodel.pipeline_options import PdfPipelineOptions
                from docling.document_converter import DocumentConverter, PdfFormatOption

                pdf_opts = PdfPipelineOptions(do_ocr=with_ocr)
                self._converters[key] = DocumentConverter(
                    format_options={
                        InputFormat.PDF: PdfFormatOption(
                            pipeline_options=pdf_opts,
                        ),
                    }
                )
                logger.info("parser.docling.loaded", do_ocr=with_ocr)
            except Exception:
                logger.exception("parser.docling.load_failed")
                raise
        return self._converters[key]

    @staticmethod
    def _has_text_layer(file_path: Path) -> bool:
        """Fast check for embedded text using pypdfium2 (Docling dependency).

        Samples the first 3 pages. If average character count > 50, the PDF
        has a usable text layer and OCR model loading can be skipped entirely.
        """
        import pypdfium2 as pdfium

        try:
            doc = pdfium.PdfDocument(str(file_path))
            pages_to_check = min(len(doc), 3)
            total_chars = 0
            for i in range(pages_to_check):
                page = doc[i]
                textpage = page.get_textpage()
                total_chars += len(textpage.get_text_range().strip())
                textpage.close()
                page.close()
            doc.close()
            return total_chars / max(pages_to_check, 1) > 50
        except Exception:
            return False  # Can't read → fall back to OCR

    def _resolve_ocr(self, file_path: Path, ext: str) -> bool:
        """Decide whether to use OCR for this document based on config."""
        from app.config import Settings

        settings = Settings()
        ocr_setting = settings.enable_docling_ocr

        # Handle both str ("auto"/"true"/"false") and bool (from DB overrides)
        if isinstance(ocr_setting, bool):
            return ocr_setting
        if ocr_setting == "auto":
            if ext != ".pdf":
                return False
            has_text = self._has_text_layer(file_path)
            logger.info("parser.ocr.auto_detect", filename=file_path.name, has_text_layer=has_text)
            return not has_text
        return ocr_setting.lower() not in ("false", "0", "")

    def _parse_with_docling(self, file_path: Path, filename: str) -> ParseResult:
        """Parse a file using the Docling library.

        Docling's ``DocumentConverter.convert()`` returns a conversion result
        whose ``.document`` exposes the parsed content.  We extract the full
        markdown representation and attempt per-page iteration when available.
        """
        ext = Path(filename).suffix.lower()
        use_ocr = self._resolve_ocr(file_path, ext)
        converter = self._get_converter(with_ocr=use_ocr)

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
            logger.error(
                "parser.docling.markdown_export_failed",
                filename=filename,
                exc_info=True,
            )
            raise

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
            # Page-level iteration is best-effort degradation: the full text
            # is still available from export_to_markdown().  Docling page
            # structures vary across versions, so graceful fallback to a
            # single-page wrapper is acceptable.
            logger.warning(
                "parser.docling.page_iteration_unavailable",
                filename=filename,
                exc_info=True,
            )

        # Fallback: if we got no pages, wrap the entire text in one page.
        if not pages:
            pages = [PageContent(page_number=1, text=text, tables=[], images=[])]

        # ----------------------------------------------------------
        # Metadata
        # ----------------------------------------------------------
        metadata: dict = {"format": file_path.suffix.lower()}
        try:
            # Docling may expose name/title or other metadata on the document.
            if hasattr(doc, "name") and doc.name:
                metadata["title"] = doc.name
        except AttributeError:
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
        # Some versions expose an export method.  Best-effort: page text
        # extraction is optional enrichment; full document text is available
        # from the top-level export.
        if callable(getattr(page, "export_to_markdown", None)):
            try:
                return str(page.export_to_markdown())
            except (AttributeError, TypeError, RuntimeError):
                pass
        return ""

    @staticmethod
    def _extract_page_tables(page) -> list[str]:
        """Best-effort extraction of tables (as markdown) from a Docling page."""
        tables: list[str] = []
        raw = getattr(page, "tables", None)
        if raw is None:
            return tables
        # Best-effort: table extraction is optional enrichment.
        # Returns whatever tables were successfully extracted.
        try:
            for table in raw:
                if callable(getattr(table, "export_to_markdown", None)):
                    tables.append(table.export_to_markdown())
                elif hasattr(table, "text") and isinstance(table.text, str):
                    tables.append(table.text)
        except (AttributeError, TypeError, RuntimeError):
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

    # ------------------------------------------------------------------
    # EML backend (RFC 822 email, stdlib)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_eml(file_path: Path, filename: str) -> ParseResult:
        """Parse an EML file using stdlib email.parser."""
        raw_bytes = file_path.read_bytes()
        msg = email.message_from_bytes(raw_bytes, policy=email.policy.default)

        # Extract headers (including RFC 5322 threading headers)
        headers = {
            "from": str(msg.get("From", "")),
            "to": str(msg.get("To", "")),
            "cc": str(msg.get("Cc", "")),
            "subject": str(msg.get("Subject", "")),
            "date": str(msg.get("Date", "")),
            "message_id": str(msg.get("Message-ID", "") or ""),
            "in_reply_to": str(msg.get("In-Reply-To", "") or ""),
            "references": str(msg.get("References", "") or ""),
        }

        # Extract body text
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    payload = part.get_content()
                    if isinstance(payload, str):
                        body = payload
                        break
            # Fallback: strip HTML if no plaintext part found
            if not body:
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type == "text/html":
                        payload = part.get_content()
                        if isinstance(payload, str):
                            body = re.sub(r"<[^>]+>", "", payload)
                            body = re.sub(r"\s+", " ", body).strip()
                            break
        else:
            content_type = msg.get_content_type()
            payload = msg.get_content()
            if isinstance(payload, str):
                if content_type == "text/html":
                    body = re.sub(r"<[^>]+>", "", payload)
                    body = re.sub(r"\s+", " ", body).strip()
                else:
                    body = payload

        # Collect attachments metadata (binary data stored separately)
        attachments: list[dict] = []
        if msg.is_multipart():
            for part in msg.walk():
                disposition = part.get_content_disposition()
                if disposition == "attachment" or (disposition == "inline" and part.get_filename()):
                    att_filename = part.get_filename() or "unnamed_attachment"
                    att_data = part.get_payload(decode=True)
                    if att_data:
                        attachments.append(
                            {
                                "filename": att_filename,
                                "content_type": part.get_content_type(),
                                "data": att_data,
                            }
                        )

        # Format header block
        header_block = f"From: {headers['from']}\nTo: {headers['to']}\n"
        if headers["cc"]:
            header_block += f"Cc: {headers['cc']}\n"
        header_block += f"Date: {headers['date']}\nSubject: {headers['subject']}\n"

        full_text = f"{header_block}\n{body}"

        metadata: dict = {
            "format": ".eml",
            "document_type": "email",
            **headers,
        }
        if attachments:
            metadata["attachment_count"] = len(attachments)
            metadata["attachment_data"] = attachments

        logger.info(
            "parser.eml.success",
            filename=filename,
            text_length=len(full_text),
            attachments=len(attachments),
        )

        return ParseResult(
            text=full_text,
            pages=[PageContent(page_number=1, text=full_text, tables=[], images=[])],
            metadata=metadata,
            page_count=1,
        )

    # ------------------------------------------------------------------
    # MSG backend (Outlook .msg, extract-msg library)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_msg(file_path: Path, filename: str) -> ParseResult:
        """Parse an Outlook .msg file using extract-msg."""
        import extract_msg

        msg = extract_msg.Message(str(file_path))
        try:
            # Extract RFC 5322 threading headers from MSG transport headers
            message_id = ""
            in_reply_to = ""
            references = ""
            transport_headers = getattr(msg, "header", None) or ""
            if not transport_headers:
                transport_headers = getattr(msg, "transportMessageHeaders", None) or ""
            if transport_headers:
                import email as _email_mod
                import email.policy as _email_policy

                parsed_headers = _email_mod.message_from_string(transport_headers, policy=_email_policy.default)
                message_id = str(parsed_headers.get("Message-ID", "") or "")
                in_reply_to = str(parsed_headers.get("In-Reply-To", "") or "")
                references = str(parsed_headers.get("References", "") or "")

            headers = {
                "from": msg.sender or "",
                "to": msg.to or "",
                "cc": msg.cc or "",
                "subject": msg.subject or "",
                "date": str(msg.date) if msg.date else "",
                "message_id": message_id,
                "in_reply_to": in_reply_to,
                "references": references,
            }

            body = msg.body or ""

            # Collect attachments
            attachments: list[dict] = []
            for att in msg.attachments:
                att_filename = getattr(att, "longFilename", None) or getattr(att, "shortFilename", None) or "unnamed"
                att_data = getattr(att, "data", None)
                if att_data:
                    attachments.append(
                        {
                            "filename": att_filename,
                            "content_type": "application/octet-stream",
                            "data": att_data,
                        }
                    )

            # Format header block
            header_block = f"From: {headers['from']}\nTo: {headers['to']}\n"
            if headers["cc"]:
                header_block += f"Cc: {headers['cc']}\n"
            header_block += f"Date: {headers['date']}\nSubject: {headers['subject']}\n"

            full_text = f"{header_block}\n{body}"

            metadata: dict = {
                "format": ".msg",
                "document_type": "email",
                **headers,
            }
            if attachments:
                metadata["attachment_count"] = len(attachments)
                metadata["attachment_data"] = attachments

            logger.info(
                "parser.msg.success",
                filename=filename,
                text_length=len(full_text),
                attachments=len(attachments),
            )

            return ParseResult(
                text=full_text,
                pages=[PageContent(page_number=1, text=full_text, tables=[], images=[])],
                metadata=metadata,
                page_count=1,
            )
        finally:
            msg.close()

    # ------------------------------------------------------------------
    # CSV/TSV backend (stdlib csv → markdown table)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_csv(file_path: Path, filename: str) -> ParseResult:
        """Parse a CSV/TSV file into a markdown table."""
        max_rows = 1000

        try:
            raw_text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw_text = file_path.read_text(encoding="latin-1")

        # Detect dialect (comma vs tab vs other)
        try:
            sample = raw_text[:8192]
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            # Default to comma-separated
            dialect = csv.excel

        reader = csv.reader(io.StringIO(raw_text), dialect)
        rows: list[list[str]] = []
        for row in reader:
            rows.append(row)
            if len(rows) > max_rows + 1:  # +1 for header
                break

        if not rows:
            return ParseResult(
                text="(empty CSV file)",
                pages=[PageContent(page_number=1, text="(empty CSV file)", tables=[], images=[])],
                metadata={"format": Path(filename).suffix.lower(), "row_count": 0, "column_count": 0},
                page_count=1,
            )

        truncated = len(rows) > max_rows + 1
        total_row_count = len(rows) - 1  # Subtract header
        if truncated:
            rows = rows[: max_rows + 1]
            total_row_count = max_rows

        # Build markdown table
        header = rows[0]
        column_count = len(header)
        md_lines: list[str] = []
        md_lines.append("| " + " | ".join(header) + " |")
        md_lines.append("| " + " | ".join(["---"] * column_count) + " |")
        for row in rows[1:]:
            # Pad or truncate row to match header length
            padded = row[:column_count] + [""] * max(0, column_count - len(row))
            md_lines.append("| " + " | ".join(padded) + " |")

        text = "\n".join(md_lines)

        metadata: dict = {
            "format": Path(filename).suffix.lower(),
            "row_count": total_row_count,
            "column_count": column_count,
            "truncated": truncated,
        }

        logger.info(
            "parser.csv.success",
            filename=filename,
            rows=total_row_count,
            columns=column_count,
            truncated=truncated,
        )

        return ParseResult(
            text=text,
            pages=[PageContent(page_number=1, text=text, tables=[text], images=[])],
            metadata=metadata,
            page_count=1,
        )

    # ------------------------------------------------------------------
    # RTF backend (striprtf library)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_rtf(file_path: Path, filename: str) -> ParseResult:
        """Parse an RTF file using striprtf."""
        from striprtf.striprtf import rtf_to_text

        try:
            raw = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw = file_path.read_text(encoding="latin-1")

        text = rtf_to_text(raw)

        logger.info(
            "parser.rtf.success",
            filename=filename,
            text_length=len(text),
        )

        return ParseResult(
            text=text,
            pages=[PageContent(page_number=1, text=text, tables=[], images=[])],
            metadata={"format": ".rtf"},
            page_count=1,
        )
