#!/usr/bin/env python3
"""Generate a synthetic resume PDF for E2E pipeline testing.

Outputs: tests/test_e2e/fixtures/sample_resume.pdf

The PDF contains known ground-truth entities for semantic assertions:
- Person: Elena Vasquez
- Organizations: Meridian Legal Group, Stanford University
- Location: San Francisco, California
- Email: elena.vasquez@meridian.law
- Dates: 2018, 2022

Usage:
    python scripts/generate_test_pdf.py
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "tests" / "test_e2e" / "fixtures" / "sample_resume.pdf"


def generate() -> None:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)

    # ── Page 1: Header + Summary + Experience ──────────────────────
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 12, "Elena Vasquez", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, "Senior Legal Analyst", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, "San Francisco, California", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, "elena.vasquez@meridian.law | (415) 555-0192", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(8)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Professional Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(
        0,
        6,
        (
            "Elena Vasquez is a seasoned legal analyst with over eight years of experience "
            "in corporate litigation, regulatory compliance, and legal technology. She specializes "
            "in large-scale document review, e-discovery workflows, and knowledge management "
            "for complex multi-party disputes. Elena has managed document populations exceeding "
            "500,000 pages and has been recognized for her ability to identify critical evidence "
            "patterns across heterogeneous legal corpora."
        ),
    )

    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Professional Experience", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Meridian Legal Group", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "I", 11)
    pdf.cell(0, 7, "Senior Legal Analyst  |  January 2022 - Present", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(
        0,
        6,
        (
            "At Meridian Legal Group, Elena Vasquez leads the litigation support team responsible "
            "for complex commercial disputes. She directs document review operations for cases "
            "involving regulatory investigations, securities fraud, and intellectual property "
            "litigation. Elena developed the firm's internal knowledge graph system for tracking "
            "entity relationships across case documents, reducing review time by 35 percent. "
            "She manages a team of twelve analysts and coordinates with outside counsel on "
            "privilege review and production workflows."
        ),
    )

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Pacific Coast Legal Services", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "I", 11)
    pdf.cell(0, 7, "Legal Analyst  |  June 2018 - December 2021", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(
        0,
        6,
        (
            "At Pacific Coast Legal Services in San Francisco, Elena performed document review "
            "and analysis for class action litigation and government investigations. She developed "
            "coding protocols for privilege and relevance review, trained junior analysts on "
            "e-discovery platforms including Relativity and Nuix, and assisted attorneys with "
            "deposition preparation by identifying key documents and witness statements."
        ),
    )

    # ── Page 2: Education + Skills + Certifications ────────────────
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Education", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Stanford University", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, "Master of Science in Computational Law, 2018", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(
        0,
        6,
        (
            'Thesis: "Automated Entity Resolution in Large-Scale Legal Document Collections." '
            "Coursework included natural language processing, information retrieval, statistical "
            "learning, and legal informatics. Research assistant in the Stanford Law and Technology "
            "Lab under Professor James Whitfield."
        ),
    )

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "University of California, Berkeley", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, "Bachelor of Arts in Political Science, 2016", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(
        0,
        6,
        (
            "Graduated magna cum laude. Minor in Computer Science. Member of the Berkeley "
            "Legal Studies Society and the Data Science Club."
        ),
    )

    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Technical Skills", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(
        0,
        6,
        (
            "Document Review: Relativity, Nuix, Brainspace, DISCO\n"
            "Programming: Python, SQL, R, JavaScript\n"
            "Data Analysis: Pandas, scikit-learn, spaCy, NetworkX\n"
            "Legal Technology: Knowledge graphs, entity extraction, predictive coding\n"
            "Project Management: Agile methodology, JIRA, Confluence"
        ),
    )

    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Certifications and Awards", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(
        0,
        6,
        (
            "Certified E-Discovery Specialist (CEDS), ACEDS, 2020\n"
            "Relativity Certified Administrator (RCA), 2019\n"
            "Meridian Legal Group Outstanding Achievement Award, 2023\n"
            'Published: "Graph-Based Approaches to Legal Document Analysis" in the '
            "Journal of Legal Technology, Volume 14, Issue 3, 2022"
        ),
    )

    # ── Page 3: References + additional context ────────────────────
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Professional References", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(
        0,
        6,
        (
            "1. Sarah Chen, Managing Partner, Meridian Legal Group\n"
            "   sarah.chen@meridian.law | (415) 555-0201\n\n"
            "2. Professor James Whitfield, Stanford University\n"
            "   jwhitfield@stanford.edu | (650) 555-0134\n\n"
            "3. David Park, Senior Counsel, Pacific Coast Legal Services\n"
            "   dpark@pacificcoastlegal.com | (415) 555-0178"
        ),
    )

    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Professional Affiliations", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(
        0,
        6,
        (
            "Association of Certified E-Discovery Specialists (ACEDS)\n"
            "Women in Legal Technology (WILT)\n"
            "San Francisco Bar Association, Legal Technology Committee\n"
            "International Legal Technology Association (ILTA)"
        ),
    )

    # Write PDF
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUTPUT_PATH))
    print(f"Generated: {OUTPUT_PATH}  ({OUTPUT_PATH.stat().st_size:,} bytes, {pdf.pages_count} pages)")


if __name__ == "__main__":
    generate()
