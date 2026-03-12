"""Prompt templates for the ingestion pipeline.

Used by the contextual chunk enrichment stage (feature-flagged).
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
