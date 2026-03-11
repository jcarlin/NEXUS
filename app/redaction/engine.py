"""PDF redaction engine — permanent text removal from content streams.

Uses pikepdf (MPL-2.0) to parse and rewrite PDF content streams,
physically removing redacted text from the document data.  This is NOT
visual masking — the underlying text data is deleted.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pikepdf

from app.redaction.schemas import RedactionSpec


def redact_pdf(
    input_path: Path,
    output_path: Path,
    redaction_specs: list[RedactionSpec],
    replacement_char: str = "\u2588",
) -> int:
    """Apply redactions to a PDF, removing text from content streams.

    Opens the PDF at *input_path*, processes each page that has redactions,
    replaces matching text with *replacement_char*, strips metadata, and
    saves to *output_path*.

    Returns the number of redaction operations applied.
    """
    pdf = pikepdf.open(input_path)
    applied = 0

    # Group redactions by page number
    by_page: dict[int | None, list[RedactionSpec]] = {}
    for spec in redaction_specs:
        by_page.setdefault(spec.page_number, []).append(spec)

    for page_num, specs in by_page.items():
        # Determine which pages to process
        if page_num is not None:
            if page_num < 1 or page_num > len(pdf.pages):
                continue
            pages_to_process = [(page_num - 1, pdf.pages[page_num - 1])]
        else:
            # None means apply to all pages
            pages_to_process = list(enumerate(pdf.pages))

        for page_idx, page in pages_to_process:
            try:
                content_stream = pikepdf.parse_content_stream(page)
            except Exception:
                raise ValueError(
                    f"Failed to parse content stream for page {page_idx + 1}. "
                    "Redaction cannot be guaranteed — aborting to prevent privileged content leakage."
                )

            new_operations = []
            for operands, operator in content_stream:
                if operator in (pikepdf.Operator("Tj"), pikepdf.Operator("'")):
                    # Single string text operator
                    text = _decode_operand(operands[0])
                    redacted_text, count = _apply_redactions_to_text(text, specs, replacement_char)
                    applied += count
                    if count > 0:
                        operands = [pikepdf.String(redacted_text)]
                    new_operations.append((operands, operator))

                elif operator == pikepdf.Operator("TJ"):
                    # Array of strings and positioning values
                    new_array = []
                    for item in operands[0]:
                        if isinstance(item, pikepdf.String | str):
                            text = _decode_operand(item)
                            redacted_text, count = _apply_redactions_to_text(text, specs, replacement_char)
                            applied += count
                            new_array.append(pikepdf.String(redacted_text) if count > 0 else item)
                        else:
                            new_array.append(item)
                    new_operations.append(([pikepdf.Array(new_array)], operator))

                elif operator == pikepdf.Operator('"'):
                    # " operator: aw ac string
                    text = _decode_operand(operands[2])
                    redacted_text, count = _apply_redactions_to_text(text, specs, replacement_char)
                    applied += count
                    if count > 0:
                        operands = list(operands)
                        operands[2] = pikepdf.String(redacted_text)
                    new_operations.append((operands, operator))

                else:
                    new_operations.append((operands, operator))

            # Rebuild content stream
            page.Contents = pdf.make_stream(pikepdf.unparse_content_stream(new_operations))

    # Scrub document metadata
    if hasattr(pdf, "docinfo") and pdf.docinfo is not None:
        with pdf.open_metadata() as meta:
            # Clear XMP metadata entries that might contain redacted text
            for key in list(meta.keys()):
                del meta[key]
        # Clear the old-style Info dict
        del pdf.docinfo

    pdf.save(output_path)
    pdf.close()
    return applied


def verify_redaction(pdf_path: Path, redacted_texts: list[str]) -> bool:
    """Verify that none of *redacted_texts* appear in the PDF at *pdf_path*.

    Opens the PDF, extracts all text from content streams, and checks
    that none of the specified strings are present.  Returns ``True`` if
    the redaction is verified (none found), ``False`` if any remain.
    """
    pdf = pikepdf.open(pdf_path)
    all_text = []

    for page_idx, page in enumerate(pdf.pages):
        try:
            content_stream = pikepdf.parse_content_stream(page)
        except Exception:
            raise ValueError(
                f"Failed to parse content stream for page {page_idx + 1} during verification. "
                "Redaction cannot be verified — aborting to prevent privileged content leakage."
            )

        for operands, operator in content_stream:
            if operator in (pikepdf.Operator("Tj"), pikepdf.Operator("'")):
                all_text.append(_decode_operand(operands[0]))
            elif operator == pikepdf.Operator("TJ"):
                for item in operands[0]:
                    if isinstance(item, pikepdf.String | str):
                        all_text.append(_decode_operand(item))
            elif operator == pikepdf.Operator('"'):
                all_text.append(_decode_operand(operands[2]))

    pdf.close()

    full_text = "".join(all_text)
    for target in redacted_texts:
        if target in full_text:
            return False
    return True


def hash_text(text: str) -> str:
    """Return SHA-256 hex digest of *text* (for audit log, NOT the text itself)."""
    return hashlib.sha256(text.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _decode_operand(operand: pikepdf.String | str) -> str:
    """Decode a pikepdf String operand to a Python str."""
    if isinstance(operand, str):
        return operand
    try:
        return str(bytes(operand), errors="replace")
    except Exception:
        return str(operand)


def _apply_redactions_to_text(
    text: str,
    specs: list[RedactionSpec],
    replacement_char: str,
) -> tuple[str, int]:
    """Replace redacted spans in *text* with *replacement_char*.

    This uses a simple substring search based on the redaction reason
    or offset-based replacement.  Returns ``(new_text, redaction_count)``.
    """
    count = 0
    for spec in specs:
        # Offset-based: extract the target text from the original span
        # For content-stream level redaction, we do substring matching
        # since PDF text operators don't preserve document-level offsets
        if spec.start < len(text) and spec.end <= len(text) and spec.start < spec.end:
            target = text[spec.start : spec.end]
            if target in text:
                text = text.replace(target, replacement_char * len(target), 1)
                count += 1
    return text, count
