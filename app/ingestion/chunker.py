"""Semantic text chunking for legal documents.

Uses tiktoken for token counting.  Respects paragraph boundaries.
Max 512 tokens per chunk with 64-token overlap (configurable).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog
import tiktoken

logger = structlog.get_logger(__name__)

# Regex that identifies a markdown table line (starts with |)
_TABLE_LINE_RE = re.compile(r"^\s*\|")
# Regex for markdown table separator lines (e.g. |---|---|)
_TABLE_SEP_RE = re.compile(r"^\s*\|[\s\-:|]+\|\s*$")


@dataclass
class Chunk:
    """A single chunk of text produced by the chunker."""

    chunk_index: int
    text: str
    token_count: int
    metadata: dict = field(default_factory=dict)


class TextChunker:
    """Split text into token-bounded chunks that respect paragraph boundaries.

    The algorithm:

    1.  Split the incoming text into *blocks* — contiguous paragraphs
        separated by blank lines.  Markdown tables (lines starting with
        ``|``) are grouped into a single block so they are never split
        mid-row.
    2.  Accumulate blocks into a chunk until adding the next block would
        exceed ``max_tokens``.
    3.  When a single block itself exceeds ``max_tokens``, hard-split it
        on sentence or whitespace boundaries.
    4.  After finalising a chunk, create the overlap by taking up to
        ``overlap_tokens`` worth of text from the *end* of the previous
        chunk and prepending it to the next chunk.

    Parameters
    ----------
    max_tokens:
        Maximum number of tokens per chunk (default 512).
    overlap_tokens:
        Number of overlapping tokens between consecutive chunks (default 64).
    """

    def __init__(
        self,
        max_tokens: int = 512,
        overlap_tokens: int = 64,
    ) -> None:
        self._max_tokens = max_tokens
        self._overlap = overlap_tokens
        self._encoding = tiktoken.get_encoding("cl100k_base")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def count_tokens(self, text: str) -> int:
        """Return the number of tokens in *text* using cl100k_base."""
        return len(self._encoding.encode(text))

    def chunk(
        self,
        text: str,
        metadata: dict | None = None,
        document_type: str | None = None,
    ) -> list[Chunk]:
        """Split *text* into a list of :class:`Chunk` objects.

        Parameters
        ----------
        text:
            The full document text (typically markdown produced by the parser).
        metadata:
            Optional base metadata to attach to every chunk.  Keys like
            ``source_file`` and ``page_number`` are preserved on each chunk.
        document_type:
            Optional hint (e.g. ``"email"``) that enables format-specific
            chunking strategies.

        Returns
        -------
        List of ``Chunk`` objects ordered by ``chunk_index``.
        """
        if metadata is None:
            metadata = {}

        if not text or not text.strip():
            logger.debug("chunker.empty_input")
            return []

        # Email-aware chunking: split body from quoted replies first
        if document_type == "email":
            return self._chunk_email(text, metadata)

        blocks = self._split_into_blocks(text)
        raw_chunks = self._assemble_chunks(blocks)

        chunks: list[Chunk] = []
        for idx, chunk_text in enumerate(raw_chunks):
            token_count = self.count_tokens(chunk_text)
            chunk_meta = {**metadata, "chunk_index": idx}
            chunks.append(
                Chunk(
                    chunk_index=idx,
                    text=chunk_text,
                    token_count=token_count,
                    metadata=chunk_meta,
                )
            )

        logger.info(
            "chunker.complete",
            total_chunks=len(chunks),
            total_tokens=sum(c.token_count for c in chunks),
            max_tokens=self._max_tokens,
        )
        return chunks

    # ------------------------------------------------------------------
    # Internal: block splitting
    # ------------------------------------------------------------------

    def _split_into_blocks(self, text: str) -> list[str]:
        """Split *text* into semantic blocks (paragraphs & tables).

        Blank-line separated paragraphs become individual blocks.
        Consecutive markdown table lines are merged into a single block
        so tables are never broken across chunks.
        """
        lines = text.split("\n")
        blocks: list[str] = []
        current_lines: list[str] = []
        in_table = False

        for line in lines:
            is_table_line = bool(_TABLE_LINE_RE.match(line))

            if is_table_line:
                if not in_table:
                    # Flush any accumulated paragraph before entering table.
                    self._flush_lines(current_lines, blocks)
                    current_lines = []
                    in_table = True
                current_lines.append(line)
            else:
                if in_table:
                    # Leaving a table block — flush it.
                    self._flush_lines(current_lines, blocks)
                    current_lines = []
                    in_table = False

                # Blank line signals a paragraph boundary.
                if line.strip() == "":
                    self._flush_lines(current_lines, blocks)
                    current_lines = []
                else:
                    current_lines.append(line)

        # Flush remainder.
        self._flush_lines(current_lines, blocks)
        return blocks

    @staticmethod
    def _flush_lines(lines: list[str], blocks: list[str]) -> None:
        """Join *lines* into a single block string and append to *blocks*."""
        if not lines:
            return
        block = "\n".join(lines).strip()
        if block:
            blocks.append(block)

    # ------------------------------------------------------------------
    # Internal: chunk assembly
    # ------------------------------------------------------------------

    def _assemble_chunks(self, blocks: list[str]) -> list[str]:
        """Accumulate blocks into chunks respecting token limits and overlap."""
        if not blocks:
            return []

        chunks: list[str] = []
        current_parts: list[str] = []
        current_tokens: int = 0

        for block in blocks:
            block_tokens = self.count_tokens(block)

            # If a single block exceeds the max, hard-split it.
            if block_tokens > self._max_tokens:
                # First, flush whatever we have accumulated so far.
                if current_parts:
                    chunks.append("\n\n".join(current_parts))
                    current_parts = []
                    current_tokens = 0

                sub_chunks = self._hard_split(block)
                chunks.extend(sub_chunks)
                continue

            # Would adding this block exceed the budget?
            # Account for the double-newline joiner between parts.
            joiner_tokens = self.count_tokens("\n\n") if current_parts else 0
            projected = current_tokens + joiner_tokens + block_tokens

            if projected > self._max_tokens and current_parts:
                # Finalise current chunk.
                chunks.append("\n\n".join(current_parts))
                # Build overlap from the tail of the just-finished chunk.
                overlap_text = self._build_overlap(current_parts)
                current_parts = []
                current_tokens = 0
                if overlap_text:
                    current_parts.append(overlap_text)
                    current_tokens = self.count_tokens(overlap_text)

            current_parts.append(block)
            joiner_tokens = self.count_tokens("\n\n") if len(current_parts) > 1 else 0
            current_tokens = self.count_tokens("\n\n".join(current_parts))

        # Flush last chunk.
        if current_parts:
            chunks.append("\n\n".join(current_parts))

        return chunks

    def _build_overlap(self, parts: list[str]) -> str:
        """Return up to ``overlap_tokens`` worth of text from *parts* (tail)."""
        if self._overlap <= 0:
            return ""

        # Work backwards through the parts collecting tokens.
        full_text = "\n\n".join(parts)
        tokens = self._encoding.encode(full_text)

        if len(tokens) <= self._overlap:
            return full_text

        overlap_tokens = tokens[-self._overlap :]
        return self._encoding.decode(overlap_tokens)

    def _hard_split(self, block: str) -> list[str]:
        """Split a single oversized block into chunks at sentence or word boundaries.

        Tries to break on sentence endings first (``.``, ``?``, ``!`` followed
        by whitespace).  Falls back to whitespace boundaries.
        """
        tokens = self._encoding.encode(block)
        chunks: list[str] = []

        start = 0
        while start < len(tokens):
            end = min(start + self._max_tokens, len(tokens))
            chunk_text = self._encoding.decode(tokens[start:end])

            # If there is more text to come, try to break at a sentence end.
            if end < len(tokens):
                sentence_break = self._find_sentence_break(chunk_text)
                if sentence_break > 0:
                    chunk_text = chunk_text[:sentence_break]
                    # Recount tokens for the trimmed text to set the correct start.
                    end = start + len(self._encoding.encode(chunk_text))

            chunks.append(chunk_text.strip())

            # Advance, accounting for overlap.
            advance = end - start
            if advance <= 0:
                # Safety valve to avoid infinite loops.
                advance = self._max_tokens
            start += advance

        return [c for c in chunks if c]

    @staticmethod
    def _find_sentence_break(text: str) -> int:
        """Return the index *after* the last sentence-ending punctuation.

        Returns 0 if no suitable break point is found.
        """
        # Search from the end for ". ", "? ", "! " (sentence endings).
        best = 0
        for pattern in (". ", "? ", "! ", ".\n", "?\n", "!\n"):
            idx = text.rfind(pattern)
            if idx > 0:
                candidate = idx + len(pattern)
                if candidate > best:
                    best = candidate
        return best

    # ------------------------------------------------------------------
    # Email-aware chunking
    # ------------------------------------------------------------------

    # Pattern for quoted reply boundaries: lines starting with > or
    # common reply markers like "On ... wrote:" or "-----Original Message-----"
    _REPLY_MARKER_RE = re.compile(
        r"^(?:"
        r"(?:>{1,}\s)|"                          # > quoted lines
        r"(?:On .+ wrote:$)|"                     # "On ... wrote:"
        r"(?:-{3,}\s*Original Message\s*-{3,})|"  # ---Original Message---
        r"(?:-{3,}\s*Forwarded .+\s*-{3,})"       # ---Forwarded message---
        r")",
        re.MULTILINE | re.IGNORECASE,
    )

    def _chunk_email(self, text: str, base_metadata: dict) -> list[Chunk]:
        """Split an email into body and quoted-reply sections, then chunk each.

        This prevents quoted replies from being merged into the primary body
        content, making retrieval more precise for email threads.
        """
        # Find the first quoted reply boundary
        match = self._REPLY_MARKER_RE.search(text)

        if match:
            body_text = text[:match.start()].strip()
            quoted_text = text[match.start():].strip()
            sections = []
            if body_text:
                sections.append(("body", body_text))
            if quoted_text:
                sections.append(("quoted_reply", quoted_text))
        else:
            sections = [("body", text)]

        all_chunks: list[Chunk] = []
        chunk_idx = 0

        for section_label, section_text in sections:
            blocks = self._split_into_blocks(section_text)
            raw_chunks = self._assemble_chunks(blocks)

            for chunk_text in raw_chunks:
                token_count = self.count_tokens(chunk_text)
                chunk_meta = {
                    **base_metadata,
                    "chunk_index": chunk_idx,
                    "email_section": section_label,
                }
                all_chunks.append(
                    Chunk(
                        chunk_index=chunk_idx,
                        text=chunk_text,
                        token_count=token_count,
                        metadata=chunk_meta,
                    )
                )
                chunk_idx += 1

        logger.info(
            "chunker.email.complete",
            total_chunks=len(all_chunks),
            total_tokens=sum(c.token_count for c in all_chunks),
        )
        return all_chunks
