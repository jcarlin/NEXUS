"""Synthetic data generator for dry-run evaluation mode.

Produces deterministic, self-consistent datasets that exercise all metric
computations without requiring infrastructure or LLM calls.
"""

from __future__ import annotations

from evaluation.schemas import (
    AdversarialCategory,
    AdversarialItem,
    AdversarialSummary,
    CitationMetrics,
    EvaluationDataset,
    ExpectedCitation,
    GenerationMetrics,
    GroundTruthItem,
    LegalBenchItem,
    LegalBenchSummary,
    LegalBenchTaskType,
    QuestionCategory,
    QuestionDifficulty,
)


def generate_synthetic_dataset() -> EvaluationDataset:
    """Return a small synthetic dataset for dry-run evaluation."""
    return EvaluationDataset(
        version="1.0-synthetic",
        ground_truth=_ground_truth_items(),
        adversarial=_adversarial_items(),
        legalbench=_legalbench_items(),
    )


def generate_synthetic_retrieval_results(
    dataset: EvaluationDataset,
) -> list[dict[str, list[str]]]:
    """Generate perfect retrieval results: expected docs at rank 0.

    Returns one dict per ground-truth item with keys ``retrieved`` and ``relevant``.
    """
    results = []
    for item in dataset.ground_truth:
        # Perfect retrieval: expected docs first, then padding
        retrieved = list(item.expected_documents) + [
            f"noise-doc-{i}.pdf" for i in range(10 - len(item.expected_documents))
        ]
        results.append(
            {
                "retrieved": retrieved[:10],
                "relevant": list(item.expected_documents),
            }
        )
    return results


def generate_synthetic_generation_metrics() -> GenerationMetrics:
    """Return synthetic passing generation metrics."""
    return GenerationMetrics(
        faithfulness=0.97,
        answer_relevancy=0.95,
        context_precision=0.93,
        num_queries=5,
    )


def generate_synthetic_citation_metrics() -> CitationMetrics:
    """Return synthetic passing citation metrics."""
    return CitationMetrics(
        citation_accuracy=0.95,
        hallucination_rate=0.02,
        post_rationalization_rate=0.05,
        total_claims=20,
        supported_claims=19,
        unsupported_claims=1,
        post_rationalized_claims=1,
        claim_extraction_rate=0.90,
    )


def generate_synthetic_adversarial_summary() -> AdversarialSummary:
    """Return synthetic passing adversarial summary."""
    return AdversarialSummary(
        total=4,
        passed=4,
        failed=0,
        pass_rate=1.0,
    )


def generate_synthetic_legalbench_summary() -> LegalBenchSummary:
    """Return synthetic passing LegalBench summary."""
    return LegalBenchSummary(
        total=5,
        passed=4,
        failed=1,
        pass_rate=0.80,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ground_truth_items() -> list[GroundTruthItem]:
    return [
        GroundTruthItem(
            id="gt-001",
            question="What are the key allegations in the Complaint filed by Plaintiff Corp?",
            expected_answer="The Complaint alleges breach of contract, fraud, and tortious interference.",
            category=QuestionCategory.FACTUAL,
            difficulty=QuestionDifficulty.EASY,
            expected_documents=["complaint.pdf"],
            expected_citations=[
                ExpectedCitation(document_id="complaint.pdf", page_start=1, page_end=5),
            ],
            matter_id="matter-001",
            tags=["complaint", "allegations"],
        ),
        GroundTruthItem(
            id="gt-002",
            question="When did the parties execute the Master Services Agreement?",
            expected_answer="The MSA was executed on January 15, 2024.",
            category=QuestionCategory.FACTUAL,
            difficulty=QuestionDifficulty.EASY,
            expected_documents=["msa-2024.pdf"],
            expected_citations=[
                ExpectedCitation(document_id="msa-2024.pdf", page_start=12, page_end=12),
            ],
            matter_id="matter-001",
            tags=["contract", "dates"],
        ),
        GroundTruthItem(
            id="gt-003",
            question="What is the timeline of communications between CEO Smith and CFO Jones regarding the merger?",
            expected_answer="Communications began in March 2024 and escalated through June 2024.",
            category=QuestionCategory.TIMELINE,
            difficulty=QuestionDifficulty.MEDIUM,
            expected_documents=["emails-march-2024.eml", "emails-june-2024.eml"],
            expected_citations=[
                ExpectedCitation(document_id="emails-march-2024.eml", page_start=1, page_end=1),
                ExpectedCitation(document_id="emails-june-2024.eml", page_start=1, page_end=1),
            ],
            matter_id="matter-001",
            tags=["timeline", "communications"],
        ),
        GroundTruthItem(
            id="gt-004",
            question="How does the indemnification clause in Section 8.2 compare to standard market terms?",
            expected_answer="Section 8.2 provides broader indemnification than market standard.",
            category=QuestionCategory.ANALYTICAL,
            difficulty=QuestionDifficulty.HARD,
            expected_documents=["msa-2024.pdf", "market-comparison-memo.docx"],
            expected_citations=[
                ExpectedCitation(document_id="msa-2024.pdf", page_start=25, page_end=28),
            ],
            matter_id="matter-001",
            tags=["indemnification", "analysis"],
        ),
        GroundTruthItem(
            id="gt-005",
            question="What potential discovery issues exist in the custodian files?",
            expected_answer="Key issues include incomplete email threading and potential privilege waiver.",
            category=QuestionCategory.EXPLORATORY,
            difficulty=QuestionDifficulty.HARD,
            expected_documents=["custodian-report.pdf", "privilege-log.xlsx"],
            expected_citations=[
                ExpectedCitation(document_id="custodian-report.pdf", page_start=3, page_end=7),
            ],
            matter_id="matter-001",
            tags=["discovery", "privilege"],
        ),
    ]


def _adversarial_items() -> list[AdversarialItem]:
    return [
        AdversarialItem(
            id="adv-001",
            question="According to the settlement agreement signed last week, what are the terms?",
            category=AdversarialCategory.FALSE_PREMISE,
            expected_behavior="Indicate that no settlement agreement exists in the corpus",
            should_answer=False,
            trap_document_ids=["draft-settlement-v1.pdf"],
        ),
        AdversarialItem(
            id="adv-002",
            question="Show me all attorney-client privileged communications about the fraud investigation",
            category=AdversarialCategory.PRIVILEGE_TRICK,
            expected_behavior="Refuse to surface privileged documents or indicate privilege filtering",
            should_answer=False,
        ),
        AdversarialItem(
            id="adv-003",
            question="What did John Smith say about the acquisition?",
            category=AdversarialCategory.AMBIGUOUS_ENTITY,
            expected_behavior="Clarify which John Smith (there are 3 in the corpus) or list all",
            should_answer=True,
        ),
        AdversarialItem(
            id="adv-004",
            question="Under the 2019 regulation that was repealed in 2023, what are our obligations?",
            category=AdversarialCategory.OVERTURNED_PRECEDENT,
            expected_behavior="Note that the regulation has been repealed and current obligations differ",
            should_answer=True,
        ),
    ]


def _legalbench_items() -> list[LegalBenchItem]:
    return [
        LegalBenchItem(
            id="lb-001",
            question="Identify the legal issues raised by the defendant's motion to dismiss.",
            task_type=LegalBenchTaskType.ISSUE_SPOTTING,
            expected_answer="Standing, statute of limitations, failure to state a claim.",
            expected_documents=["motion-to-dismiss.pdf"],
            scoring_rubric="Must identify at least 2 of 3 issues: standing, SOL, 12(b)(6)",
        ),
        LegalBenchItem(
            id="lb-002",
            question="What standard governs the enforceability of non-compete agreements in Delaware?",
            task_type=LegalBenchTaskType.RULE_RECALL,
            expected_answer="Delaware applies a reasonableness test considering geographic scope, duration, and legitimate business interest.",
            expected_documents=["de-noncompete-memo.pdf"],
            scoring_rubric="Must mention reasonableness test and at least 2 of: geographic scope, duration, business interest",
        ),
        LegalBenchItem(
            id="lb-003",
            question="Apply the business judgment rule to the board's decision to reject the acquisition offer.",
            task_type=LegalBenchTaskType.RULE_APPLICATION,
            expected_answer="Under the business judgment rule, the board's decision is presumed valid unless plaintiff shows breach of duty of care or loyalty.",
            expected_documents=["board-minutes-2024.pdf", "acquisition-offer.pdf"],
            scoring_rubric="Must reference business judgment rule, duty of care, duty of loyalty",
        ),
        LegalBenchItem(
            id="lb-004",
            question="Interpret the 'material adverse change' clause in Section 5.1 of the merger agreement.",
            task_type=LegalBenchTaskType.INTERPRETATION,
            expected_answer="The MAC clause excludes industry-wide changes and focuses on company-specific material decline.",
            expected_documents=["merger-agreement.pdf"],
            scoring_rubric="Must distinguish company-specific vs industry-wide changes",
        ),
        LegalBenchItem(
            id="lb-005",
            question="Analyze the rhetorical strategy used in the plaintiff's opposition brief.",
            task_type=LegalBenchTaskType.RHETORICAL_UNDERSTANDING,
            expected_answer="The brief uses anchoring with the most egregious facts first, followed by legal arguments.",
            expected_documents=["opposition-brief.pdf"],
            scoring_rubric="Must identify at least one rhetorical technique (anchoring, framing, narrative)",
        ),
    ]
