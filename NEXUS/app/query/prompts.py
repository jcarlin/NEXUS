"""Prompt templates for the query pipeline.

Four templates matching CLAUDE.md Section 6.3:
  * CLASSIFY_PROMPT  — determine query type
  * REWRITE_PROMPT   — resolve pronouns, expand context
  * SYNTHESIS_PROMPT  — generate cited answer from evidence
  * FOLLOWUP_PROMPT   — generate 3 follow-up investigation questions
"""

CLASSIFY_PROMPT = """\
Classify the following user question into exactly one category.
Reply with a single word — one of: factual, analytical, exploratory, timeline

- factual: asks for a specific fact, name, date, or number
- analytical: asks to compare, evaluate, or explain relationships
- exploratory: open-ended, asks to discover or survey information
- timeline: asks about chronological events or sequences

Question: {query}

Category:"""

REWRITE_PROMPT = """\
You are a legal investigation query optimizer.
Given the conversation history and current question, rewrite the question to be:
1. Self-contained (no pronouns referencing chat history)
2. Specific (include full names, dates, locations mentioned in context)
3. Optimized for both keyword search AND semantic similarity

Conversation:
{history}

Current question: {query}

Rewritten query:"""

SYNTHESIS_PROMPT = """\
You are a legal investigation analyst. Answer the question using ONLY the provided evidence.

RULES:
- Cite every claim with [Source: filename, page X]
- Distinguish between facts stated in documents vs. inferences
- Flag contradictions between sources
- Note if evidence is insufficient to fully answer
- Use precise legal/investigative language
- If the query involves a timeline, present events chronologically
- Cross-reference entities across multiple documents when relevant

EVIDENCE:
{context}

KNOWLEDGE GRAPH CONNECTIONS:
{graph_context}

QUESTION: {query}

ANALYSIS:"""

FOLLOWUP_PROMPT = """\
Based on the question asked and the answer provided, generate exactly 3 follow-up \
questions that would deepen the investigation. These should:
1. Explore connections to OTHER entities/documents not yet examined
2. Probe for timeline gaps or contradictions
3. Suggest a different analytical angle (financial, geographic, relational)

Question: {query}
Answer: {response}
Entities found: {entities}

Generate 3 follow-up questions (one per line):"""
