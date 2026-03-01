"""Prompt templates for sentiment analysis and completeness detection.

All prompts for the analysis module are centralized here for auditability,
tuning, and legal review (see CLAUDE.md rule 40).
"""

SENTIMENT_SCORING_PROMPT = """\
You are a forensic document analyst specializing in legal investigations. \
Analyze the following document text and score it across multiple dimensions.

## Scoring Dimensions

### Core Sentiment (0.0 - 1.0)
- **positive**: Degree of positive, cooperative, or constructive tone
- **negative**: Degree of negative, hostile, defensive, or adversarial tone

### Fraud Triangle Indicators (0.0 - 1.0)
- **pressure**: Evidence of financial pressure, deadlines, threats, desperation, \
or compulsion to act (e.g., "we have to close this before the audit", \
"if we don't hit the number...")
- **opportunity**: References to exploitable gaps in controls, oversight lapses, \
access to systems/funds, or weaknesses that could be leveraged \
(e.g., "nobody checks the reconciliation", "I have admin access to...")
- **rationalization**: Justifications for questionable behavior, minimization \
of wrongdoing, appeals to normalcy or precedent \
(e.g., "everyone does it", "it's just temporary", "we'll fix it next quarter")
- **intent**: Evidence of deliberate planning, coordination of improper actions, \
or awareness that conduct is wrong \
(e.g., "make sure this doesn't get forwarded", "keep this between us")
- **concealment**: Attempts to hide, destroy, or obscure information; \
instructions to delete records, use alternative communication channels, \
or avoid creating a paper trail \
(e.g., "call me instead", "delete this after reading", "let's discuss offline")

### Hot Document Signals (0.0 - 1.0)
- **admission_guilt**: Direct or indirect admissions of wrongdoing, liability, \
or awareness of impropriety
- **inappropriate_enthusiasm**: Celebratory tone about activities that should \
raise concern (e.g., excitement about circumventing controls or exploiting \
information asymmetry)
- **deliberate_vagueness**: Conspicuous avoidance of specifics in contexts \
where precision would be normal; use of euphemisms, code words, or \
oblique references

### Hot Document Score (0.0 - 1.0)
Compute as: 0.3 * max(pressure, opportunity, rationalization) + \
0.4 * max(intent, concealment) + 0.3 * max(admission_guilt, \
inappropriate_enthusiasm, deliberate_vagueness)

## Scoring Guidelines
- Be CONSERVATIVE. Most documents in a legal corpus are routine and should \
score near 0.0 on fraud/concealment dimensions.
- Only assign scores above 0.3 when there is clear textual evidence.
- Only assign scores above 0.5 when the evidence is strong and unambiguous.
- Scores above 0.7 should be reserved for documents with explicit, \
unmistakable indicators.
- The summary should cite specific phrases or patterns that drove the scoring.
- Do NOT over-interpret neutral business language as suspicious.

## Document Text
{text}
"""

COMPLETENESS_ANALYSIS_PROMPT = """\
You are a forensic document analyst assessing the completeness of a document \
within the context of a legal investigation. Identify gaps that suggest \
missing information, removed context, or deliberate omissions.

## Gap Types to Detect

1. **missing_attachment**: References to attachments, enclosures, or \
supplementary materials that are not present \
(e.g., "see attached", "per the spreadsheet", "as shown in Exhibit A")

2. **prior_conversation**: References to prior discussions, meetings, or \
communications whose content is not available in the corpus \
(e.g., "as we discussed", "following up on yesterday's call", \
"per our conversation")

3. **forward_reference**: References to future events, decisions, or documents \
that should exist but may not have been produced \
(e.g., "I'll send the revised version tomorrow", "the board will decide next week")

4. **coded_language**: Use of euphemisms, code words, nicknames, or oblique \
references that obscure the actual subject matter \
(e.g., "the project", "our friend", "the thing we discussed", \
unexplained acronyms or shorthand)

5. **unusual_terseness**: Abnormally brief responses in contexts where more \
detail would be expected; potential indicator of sensitive content \
being communicated through other channels \
(e.g., one-word replies to complex questions, "OK" to detailed proposals)

## Scoring Guidelines
- **context_gap_score**: Overall score (0.0-1.0) reflecting how incomplete \
or suspicious the document appears in context.
- For each gap found, provide the gap_type, a direct quote or specific \
indicator as evidence, and a severity score (0.0-1.0).
- Be conservative: routine references to prior meetings or standard \
attachments in a business context should have low severity (< 0.3).
- High severity (> 0.5) should be reserved for gaps that materially \
affect understanding of the document or suggest deliberate omission.

## Document Text
{text}

## Thread Context (surrounding messages, if available)
{thread_context}
"""
