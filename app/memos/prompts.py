"""Memo drafting prompt templates.

All LLM prompts for the memos module live here.
"""

MEMO_SYSTEM_PROMPT = """You are a legal research assistant generating a formal legal memorandum.
Write in a professional, objective legal writing style. Be precise and cite sources.
Every factual claim MUST reference a source document by its filename and page number.

Use the following citation format: (Source: [filename], p. [page_number])"""

MEMO_GENERATION_PROMPT = """Generate a legal memorandum based on the following investigation findings.

## Investigation Query
{query}

## Source Documents and Cited Claims
{context}

## Instructions
Generate a structured legal memorandum with the following sections:

1. **MEMORANDUM HEADER** — Include To, From, Date, Re fields. Use "NEXUS Investigation Platform" as From. Use the query as the Re field.

2. **EXECUTIVE SUMMARY** — 2-3 paragraph overview of key findings.

3. **FACTUAL FINDINGS** — Detailed findings organized by topic. Every claim must cite a source document with filename and page number.

4. **ANALYSIS** — Legal analysis and implications of the findings. Note any gaps in the documentary record.

5. **CONCLUSION** — Summary of conclusions and recommended next steps.

{source_index_instruction}

Format the output as markdown."""

SOURCE_INDEX_INSTRUCTION = """6. **SOURCE INDEX** — Table listing all cited documents with:
   - Document filename
   - Page numbers referenced
   - Brief description of relevance"""

MEMO_TITLE_PROMPT = """Based on this investigation query, generate a concise memo title (max 80 chars).
Only respond with the title, nothing else.

Query: {query}"""
