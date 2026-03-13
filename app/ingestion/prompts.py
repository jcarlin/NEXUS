"""Prompt templates for the ingestion pipeline.

Used by the contextual chunk enrichment stage and OCR correction (feature-flagged).
"""

CONTEXT_SYSTEM_PROMPT = """\
You are a document analyst. For each numbered chunk from a legal document, \
write ONE concise sentence (max 25 words) explaining what this chunk discusses \
and its role in the document. Focus on entities, claims, dates, and legal \
concepts mentioned.

Return exactly one line per chunk, prefixed with its number (e.g. "1. ..." or "[1] ...")."""

CONTEXT_USER_PROMPT = """\
Document: {title} ({doc_type})
Author: {author} | Date: {date}

{numbered_chunks}

Context sentences:"""

# ---------------------------------------------------------------------------
# Document summarization (T2-12)
# ---------------------------------------------------------------------------

DOC_SUMMARY_PROMPT = """\
Summarize this legal document in 2-3 sentences. Include the document type, \
key parties, and main subject matter.

Document: {filename}

Content:
{content}"""

# ---------------------------------------------------------------------------
# Chunk summarization for multi-representation indexing (T2-11)
# ---------------------------------------------------------------------------

CHUNK_SUMMARY_PROMPT = """\
Summarize the following passage from a legal document in one sentence:

{chunk_text}"""

# ---------------------------------------------------------------------------
# OCR error correction (T3-14)
# ---------------------------------------------------------------------------

OCR_CORRECTION_PROMPT = """\
Fix OCR errors in the following legal document text. \
Only fix clear OCR misrecognitions (wrong characters, broken words). \
Do NOT change meaning, add content, or rephrase. \
Return ONLY the corrected text with no explanation.

Text:
{chunk}"""
