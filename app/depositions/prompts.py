"""Prompt templates for the depositions domain.

All LLM prompts are centralised here for auditability, tuning, and legal review.
"""

from __future__ import annotations

DEPOSITION_QUESTIONS_PROMPT = """\
You are a senior litigation attorney preparing for a deposition. Based on the \
witness profile and supporting documents below, generate targeted deposition \
questions.

## Witness Profile
- **Name:** {witness_name}
- **Roles:** {witness_roles}
- **Connected Entities:** {connected_entities}
- **Documents Mentioning Witness:** {document_count}

## Document Summaries
{document_summaries}

## Entity Connections
{entity_connections}

## Instructions
Generate up to {max_questions} deposition questions. Each question must:
1. Be specific, not generic — reference concrete facts from the documents.
2. Fall into one of these categories: relationship, timeline, document_specific, inconsistency.
3. Include a brief rationale explaining why this question matters.
4. Reference the basis document IDs where applicable.

{focus_instruction}

Return a JSON array of objects with these fields:
- "question": the deposition question text
- "category": one of "relationship", "timeline", "document_specific", "inconsistency"
- "basis_document_ids": list of document ID strings that support this question
- "rationale": why this question is important for the deposition
"""

WITNESS_SUMMARY_PROMPT = """\
You are a litigation support analyst. Summarise the role and significance of the \
following witness across the document corpus.

## Witness: {witness_name}

## Document Mentions
{document_mentions}

## Entity Connections
{entity_connections}

Provide a concise summary (2-3 sentences) of:
1. The witness's apparent role(s) in the matter.
2. Key relationships with other entities.
3. Any patterns or notable aspects of their document appearances.

Return only the summary text, no JSON.
"""
