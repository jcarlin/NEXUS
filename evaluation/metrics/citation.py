"""Citation provenance metrics.

Extracts citations from LLM responses and measures accuracy,
hallucination, and post-rationalization rates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ExtractedCitation:
    """A citation extracted from an LLM response."""

    filename: str
    page: int


# Matches patterns like: [Source: complaint.pdf, page 3]
# Also handles: [Source: complaint.pdf, Page 3]
_CITATION_PATTERN = re.compile(r"\[Source:\s*([^,\]]+),\s*[Pp]age\s*(\d+)\]")


def extract_citations(response_text: str) -> list[ExtractedCitation]:
    """Extract all citations from an LLM response text.

    Looks for the pattern ``[Source: <filename>, page <N>]``.
    """
    citations = []
    for match in _CITATION_PATTERN.finditer(response_text):
        filename = match.group(1).strip()
        page = int(match.group(2))
        citations.append(ExtractedCitation(filename=filename, page=page))
    return citations


def citation_accuracy(
    extracted: list[ExtractedCitation],
    expected: list[dict[str, str | int]],
) -> float:
    """Fraction of extracted citations that match an expected citation range.

    Each expected item has keys: ``document_id``, ``page_start``, ``page_end``.
    A citation matches if its filename is a substring of the expected document_id
    (or vice versa) AND its page falls within [page_start, page_end].

    Returns 1.0 if there are no extracted citations (vacuous truth).
    """
    if not extracted:
        return 1.0

    matched = 0
    for citation in extracted:
        for exp in expected:
            doc_id = str(exp["document_id"])
            page_start = int(exp["page_start"])
            page_end = int(exp["page_end"])
            # Substring match in either direction for filename flexibility
            if (citation.filename in doc_id or doc_id in citation.filename) and (
                page_start <= citation.page <= page_end
            ):
                matched += 1
                break

    return matched / len(extracted)


def hallucination_rate(
    extracted: list[ExtractedCitation],
    retrieved_filenames: set[str],
) -> float:
    """Fraction of citations referencing files NOT in the retrieved context.

    A citation is considered hallucinated if its filename does not match
    (substring) any file in the retrieved context.

    Returns 0.0 if there are no extracted citations.
    """
    if not extracted:
        return 0.0

    hallucinated = 0
    for citation in extracted:
        found = any(citation.filename in rf or rf in citation.filename for rf in retrieved_filenames)
        if not found:
            hallucinated += 1

    return hallucinated / len(extracted)


def post_rationalization_rate(
    extracted: list[ExtractedCitation],
    fused_context_filenames: set[str],
) -> float:
    """Fraction of citations referencing docs NOT in the fused context.

    Post-rationalization occurs when the model cites a document that was
    not actually presented to the synthesis node — the model generated the
    answer from memory and found a plausible source afterward.

    See: Wallat et al., "Faithfulness of RAG Citations" (2024).

    Returns 0.0 if there are no extracted citations.
    """
    if not extracted:
        return 0.0

    post_rationalized = 0
    for citation in extracted:
        found = any(citation.filename in ff or ff in citation.filename for ff in fused_context_filenames)
        if not found:
            post_rationalized += 1

    return post_rationalized / len(extracted)
