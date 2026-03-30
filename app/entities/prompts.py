"""Prompt templates for entity resolution.

Centralised per CLAUDE.md rule 49: all prompt templates in ``prompts.py``.
"""

ENTITY_RESOLUTION_PROMPT = """\
You are an entity resolution expert for legal documents.

Given a list of entity names (type: {entity_type}) extracted via OCR from legal \
documents, group names that refer to the same real-world entity.

OCR introduces errors: missing/extra characters, broken words, wrong \
capitalisation, leading garbage characters, embedded page numbers. Account for:
- OCR corruption ("CLinton" = "Clinton", "vGhislaine" = "Ghislaine")
- Partial vs full names ("Trump" and "Donald Trump" if contextually the same person)
- Titles and honorifics ("Dr. Jeffrey Epstein" = "Jeffrey Epstein" = "Mr. Epstein")
- Abbreviations ("DOJ" = "Department of Justice")
- Reordered names ("Epstein, Jeffrey" = "Jeffrey Epstein")

Rules:
- Only group entities you are CONFIDENT are the same real-world entity.
- Choose the best canonical form: prefer full proper names over fragments.
- Do NOT group entities that are merely related (e.g. "Bill Clinton" ≠ "Hillary Clinton").
- If a name is ambiguous or could refer to multiple people, leave it ungrouped.
- Return ONLY groups with 2+ members. Skip singletons.

Names (with mention counts):
{name_list}"""
