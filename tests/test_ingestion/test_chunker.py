"""Tests for the semantic text chunker."""

from __future__ import annotations

from app.ingestion.chunker import TextChunker


def test_empty_text_returns_no_chunks():
    chunker = TextChunker(max_tokens=512, overlap_tokens=64)
    assert chunker.chunk("") == []
    assert chunker.chunk("   \n\n  ") == []


def test_short_text_returns_single_chunk():
    chunker = TextChunker(max_tokens=512, overlap_tokens=64)
    chunks = chunker.chunk("Hello world. This is a short document.")
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert "Hello world" in chunks[0].text
    assert chunks[0].token_count > 0


def test_long_text_produces_multiple_chunks():
    chunker = TextChunker(max_tokens=50, overlap_tokens=10)
    # Create text with distinct paragraphs
    paragraphs = [f"Paragraph {i}. " + "word " * 30 for i in range(10)]
    text = "\n\n".join(paragraphs)
    chunks = chunker.chunk(text)
    assert len(chunks) > 1
    # All chunks should respect the token limit (with some tolerance for overlap)
    for chunk in chunks:
        assert chunk.token_count <= 60  # Allow slight overflow for overlap


def test_metadata_passed_to_chunks():
    chunker = TextChunker(max_tokens=512, overlap_tokens=64)
    meta = {"source_file": "test.pdf", "page_number": 3}
    chunks = chunker.chunk("Some legal text about evidence.", metadata=meta)
    assert len(chunks) == 1
    assert chunks[0].metadata["source_file"] == "test.pdf"
    assert chunks[0].metadata["page_number"] == 3
    assert chunks[0].metadata["chunk_index"] == 0


def test_table_kept_as_single_block():
    chunker = TextChunker(max_tokens=512, overlap_tokens=64)
    table = (
        "| Name | Amount |\n"
        "|------|--------|\n"
        "| Alice | $100 |\n"
        "| Bob | $200 |\n"
    )
    text = f"Before table.\n\n{table}\n\nAfter table."
    chunks = chunker.chunk(text)
    # The table should not be split across chunks
    found_table = False
    for chunk in chunks:
        if "| Name | Amount |" in chunk.text:
            assert "| Alice | $100 |" in chunk.text
            assert "| Bob | $200 |" in chunk.text
            found_table = True
    assert found_table


def test_token_counting():
    chunker = TextChunker()
    count = chunker.count_tokens("Hello world")
    assert isinstance(count, int)
    assert count > 0
    assert count < 10  # "Hello world" is 2-3 tokens


def test_chunk_indices_are_sequential():
    chunker = TextChunker(max_tokens=30, overlap_tokens=5)
    text = "\n\n".join([f"Sentence number {i}. " + "word " * 15 for i in range(5)])
    chunks = chunker.chunk(text)
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i
