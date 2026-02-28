"""Prompt templates for the Case Setup Agent.

Four extraction prompts used by the agent nodes to extract structured
intelligence from a legal complaint.
"""

EXTRACT_CLAIMS_PROMPT = """\
You are a legal document analyst. Extract all Claims and Causes of Action \
from the following legal complaint.

For each claim, identify:
1. The claim number (sequential, starting from 1)
2. A short label (e.g., "Fraud", "Breach of Fiduciary Duty", "Negligence")
3. The full text or summary of the claim
4. The legal elements that must be proven
5. The page numbers where the claim appears

If the document does not contain identifiable claims, return an empty list.

DOCUMENT TEXT:
{document_text}"""

EXTRACT_PARTIES_PROMPT = """\
You are a legal document analyst. Identify all parties mentioned in the \
following legal complaint.

For each party, provide:
1. Their full legal name
2. Their role: plaintiff, defendant, third_party, witness, or counsel
3. A brief description of who they are and their relevance to the case
4. Any aliases, abbreviations, or alternative references used in the document \
(e.g., "the Company", "Defendant A", initials)
5. The page numbers where they are first or prominently mentioned

Include all named individuals, companies, and organizations that are parties \
to the action or mentioned as significant participants.

DOCUMENT TEXT:
{document_text}"""

EXTRACT_DEFINED_TERMS_PROMPT = """\
You are a legal document analyst. Build a glossary of defined terms from the \
following legal complaint.

Look for:
1. Capitalized terms that are explicitly defined (e.g., '"the Agreement" means...')
2. Terms defined in a definitions section
3. Shorthand references established in the document (e.g., \
'"XYZ Corporation" (hereinafter "XYZ" or "the Company")')
4. Legal terms of art that are given specific meaning in this case

For each term, provide:
1. The term as it appears in the document
2. Its definition or the entity/concept it refers to
3. The page numbers where it is defined

DOCUMENT TEXT:
{document_text}"""

EXTRACT_TIMELINE_PROMPT = """\
You are a legal document analyst. Extract a chronological timeline of events \
from the following legal complaint.

For each event, provide:
1. The date or date range (be as specific as the document allows — exact dates, \
months, years, or ranges like "2019-2021")
2. A concise description of what happened
3. The page number where the event is mentioned

Order events chronologically. Include:
- Key transactions, meetings, communications
- Filing dates, deadlines, statutory events
- Actions or omissions central to the claims
- Background facts establishing context

If no datable events are found, return an empty list.

DOCUMENT TEXT:
{document_text}"""
