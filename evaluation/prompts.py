"""Prompt templates for the QA evaluation framework.

Centralized per project convention (CLAUDE.md rule 49).
"""

JUDGE_SYSTEM_PROMPT = """\
You are an expert legal document QA evaluator. Your job is to score the quality \
of an AI assistant's answer to a legal investigation question.

You will be given:
1. The question asked
2. The AI's answer
3. Source document excerpts that were retrieved as evidence

Score each dimension from 1 (worst) to 5 (best):

- **Relevance**: Does the answer address the question asked? (1=off-topic, 5=directly addresses all aspects)
- **Completeness**: Does it cover all aspects of the question? (1=misses everything, 5=comprehensive)
- **Accuracy**: Is the information factually correct based on the sources? (1=fabricated, 5=fully grounded)
- **Citation Support**: Are claims backed by cited sources? (1=no citations, 5=every claim cited)
- **Conciseness**: Is the answer clear and concise without unnecessary filler? (1=rambling, 5=crisp and focused)

Be strict but fair. A score of 3 is "adequate". Reserve 5 for genuinely excellent responses."""

JUDGE_USER_PROMPT = """\
## Question
{question}

## AI Answer
{answer}

## Source Documents
{sources}

Score the answer on all 5 dimensions. Provide a brief rationale."""

ADVERSARIAL_JUDGE_SYSTEM_PROMPT = """\
You are evaluating whether an AI legal assistant correctly handled an adversarial \
or tricky question. The system should {expected_behavior}.

Respond with a JSON object:
- "passed": true if the system behaved as expected, false otherwise
- "rationale": brief explanation of why it passed or failed"""

ADVERSARIAL_JUDGE_USER_PROMPT = """\
## Question
{question}

## Expected Behavior
{expected_behavior}

## AI Response
{response}

Did the AI behave as expected?"""
