"""Generate a synthetic legal corpus for end-to-end testing of the NEXUS platform.

Creates 6 documents with overlapping entities, dates, and legal issues that
exercise the ingestion pipeline, entity extraction, relationship resolution,
and knowledge graph construction.

Usage:
    python -m scripts.generate_test_docs
    python scripts/generate_test_docs/__main__.py
"""

from __future__ import annotations

import csv
import io
import textwrap
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


# ---------------------------------------------------------------------------
# Document content generators
# ---------------------------------------------------------------------------


def _memo_acme_merger() -> str:
    return textwrap.dedent("""\
        PRIVILEGED AND CONFIDENTIAL
        ATTORNEY WORK PRODUCT

        MEMORANDUM

        TO:      Michael Torres, Partner
        FROM:    Sarah Chen, Senior Associate
        DATE:    January 25, 2025
        RE:      Acme Corp / Pinnacle Industries Merger -- Due Diligence Summary

        -----------------------------------------------------------------------

        I. EXECUTIVE SUMMARY

        This memorandum summarizes the current status of due diligence in
        connection with the proposed merger between Acme Corp ("Acme") and
        Pinnacle Industries ("Pinnacle"). The merger was publicly announced on
        January 15, 2025, with a due diligence deadline of March 30, 2025.

        Based on our review to date, two issues require immediate attention:
        (1) potential environmental liability at Pinnacle's Denver manufacturing
        plant, and (2) a pending inquiry by the Securities and Exchange
        Commission ("SEC") into Pinnacle's revenue recognition practices.

        II. KEY PERSONNEL

        The following individuals are central to the transaction:

            - John Reeves, Chief Executive Officer, Acme Corp
            - Lisa Park, Chief Financial Officer, Pinnacle Industries
            - Robert Kim, outside counsel at Wilson & Drake LLP, representing
              Pinnacle Industries in the transaction
            - Michael Torres (this firm), lead partner overseeing due diligence
            - Sarah Chen (this firm), senior associate conducting document review

        III. ENVIRONMENTAL LIABILITY -- DENVER PLANT

        Pinnacle operates a manufacturing facility at 4500 Industrial Blvd,
        Denver, CO 80216 (the "Denver Plant"). A Phase I environmental site
        assessment conducted in September 2024 identified recognized
        environmental conditions ("RECs") related to historical solvent use.

        A Phase II investigation is underway. Preliminary soil sampling
        indicates trichloroethylene ("TCE") contamination exceeding Colorado
        Department of Public Health and Environment ("CDPHE") action levels in
        two monitoring wells on the eastern boundary of the property.

        Remediation costs are estimated at $3.2M to $7.8M depending on the
        extent of the plume. I spoke with John Reeves on January 22, 2025, and
        he expressed concern that these costs could affect the merger valuation.
        Reeves indicated that Acme's board would need to see a remediation cost
        cap or indemnification provision before proceeding.

        Lisa Park has represented that Pinnacle has set aside a $2M reserve for
        environmental matters, but acknowledged this may be insufficient.
        Robert Kim at Wilson & Drake LLP is reviewing Pinnacle's insurance
        coverage for environmental claims.

        IV. SEC INQUIRY

        On November 8, 2024, the SEC's Division of Enforcement issued a
        voluntary document request to Pinnacle Industries regarding revenue
        recognition practices in fiscal years 2022 and 2023. The inquiry
        focuses on Pinnacle's treatment of long-term service contracts and
        whether revenue was prematurely recognized in violation of ASC 606.

        Lisa Park has been coordinating Pinnacle's response with Robert Kim.
        As of the date of this memorandum, the SEC has not issued a formal
        order of investigation or Wells notice. Robert Kim has advised that he
        expects the inquiry to be resolved without enforcement action, but
        cautions that the timeline is uncertain.

        We should obtain copies of all communications between Pinnacle and the
        SEC, as well as Pinnacle's internal accounting workpapers for the
        periods under review.

        V. NEXT STEPS

        1. Obtain the Phase II environmental report (expected February 15, 2025).
        2. Review Pinnacle's environmental insurance policies.
        3. Request all SEC correspondence and internal response memoranda.
        4. Schedule a meeting with Robert Kim to discuss SEC inquiry timeline.
        5. Prepare a risk matrix for the Acme Corp board of directors.

        Due diligence must be substantially complete by March 30, 2025.

        -----------------------------------------------------------------------
        This memorandum is protected by the attorney-client privilege and the
        work product doctrine. Do not distribute outside the firm.
    """)


def _memo_privilege_review() -> str:
    return textwrap.dedent("""\
        PRIVILEGED AND CONFIDENTIAL

        MEMORANDUM

        TO:      Litigation Team
        FROM:    Michael Torres, Partner
        DATE:    February 5, 2025
        RE:      Privilege Review Protocol -- Acme Corp / Pinnacle Industries Matter

        -----------------------------------------------------------------------

        I. PURPOSE

        This memorandum establishes the protocol for privilege review and
        document categorization in connection with the Acme Corp / Pinnacle
        Industries merger due diligence (the "Acme/Pinnacle Matter").

        Given the volume of documents involved -- estimated at 12,000 to 15,000
        pages -- we will use a tiered review approach to ensure that privileged
        and work product materials are properly identified before any production
        to opposing counsel or regulatory bodies.

        II. REVIEW TIERS

        Tier 1 -- Automated Pre-Screen
            All documents will be processed through our document management
            system to flag potential privilege indicators (e.g., attorney names,
            "privileged," "work product," "attorney-client").

        Tier 2 -- First-Level Review
            Associates will review flagged documents and categorize them as:
            (A) Clearly privileged -- withhold
            (B) Potentially privileged -- escalate to Tier 3
            (C) Not privileged -- clear for production
            (D) Partially privileged -- redact and escalate

        Tier 3 -- Senior Review
            I will personally review all Tier 2 escalations along with
            Sarah Chen, who has the deepest familiarity with the transaction
            documents. Sarah's work product memoranda, including her due
            diligence summary dated January 25, 2025, are themselves
            privileged and must be withheld in their entirety.

        III. SPECIAL HANDLING -- ROBERT KIM COMMUNICATIONS

        Communications between Robert Kim of Wilson & Drake LLP and Lisa Park
        of Pinnacle Industries require careful analysis. As outside counsel to
        Pinnacle, Robert Kim's communications with Lisa Park may be protected
        by Pinnacle's attorney-client privilege. However, to the extent that
        these communications were shared with third parties or discuss business
        (rather than legal) matters, the privilege may have been waived.

        All Kim-Park communications should be flagged and escalated to Tier 3
        review. Do not produce any such documents without my express approval.

        IV. KEY CUSTODIANS

        The following individuals have been identified as key custodians whose
        files must be collected and reviewed:

            - Sarah Chen (this firm) -- all work product related to Acme/Pinnacle
            - Michael Torres (this firm) -- client communications, strategy memos
            - John Reeves, CEO of Acme Corp -- board communications, merger planning
            - Lisa Park, CFO of Pinnacle Industries -- financial records, SEC responses
            - Robert Kim, Wilson & Drake LLP -- legal advice, SEC inquiry coordination

        V. DEADLINES

        Document collection must be complete by February 20, 2025. Tier 1
        processing should be finished by February 28, 2025. Tier 2 review
        must be substantially complete by March 15, 2025, to allow sufficient
        time for Tier 3 review before the overall due diligence deadline of
        March 30, 2025.

        Please direct any questions to me or Sarah Chen.

        -----------------------------------------------------------------------
        This memorandum is protected by the attorney-client privilege.
        Distribution is limited to members of the litigation team.
    """)


def _email_chen_to_torres() -> str:
    msg = EmailMessage()
    msg["From"] = "Sarah Chen <sarah.chen@lawfirm.com>"
    msg["To"] = "Michael Torres <michael.torres@lawfirm.com>"
    msg["Date"] = format_datetime(datetime(2025, 2, 1, 14, 23, 0, tzinfo=UTC))
    msg["Subject"] = "Acme Due Diligence - Environmental Concerns"
    msg["Message-ID"] = "<20250201142300.abc123@lawfirm.com>"
    msg["MIME-Version"] = "1.0"
    msg.set_content(
        textwrap.dedent("""\
        Michael,

        Following up on our discussion this morning regarding the environmental
        issues at Pinnacle's Denver plant.

        I had a call with John Reeves yesterday afternoon. He is increasingly
        concerned about the potential remediation costs. His main points:

        1. Acme's board will not approve the merger without a remediation cost
           cap. Reeves suggested $5M as the maximum Acme would absorb, with
           any excess to be borne by Pinnacle or covered by insurance.

        2. Reeves wants to see the Phase II environmental report before the
           next board meeting, which is scheduled for February 20, 2025. The
           Phase II report is expected from EcoTech Environmental Consultants
           by approximately February 15, 2025.

        3. Reeves mentioned that he spoke with Lisa Park last week and she
           indicated Pinnacle may be willing to increase the environmental
           reserve from $2M to $3.5M, but would need board approval on the
           Pinnacle side.

        Separately, I reviewed the 2019 CDPHE inspection report for the Denver
        plant. The report noted minor violations related to hazardous waste
        storage that were subsequently corrected. However, the report also
        references historical solvent use dating back to the 1990s, which is
        consistent with the TCE contamination identified in the Phase I
        assessment.

        I recommend we request the following additional documents from Pinnacle:

        - All CDPHE inspection reports from 2015 to present
        - Environmental insurance policies (current and historical)
        - Internal environmental compliance audits
        - Records of underground storage tank removal (if any)

        I'll prepare a summary of the environmental risk for the next team
        meeting. Robert Kim at Wilson & Drake has indicated he will make
        Pinnacle's environmental consultants available for a call next week.

        Please let me know if you want to loop in any environmental specialists
        from our side.

        Best regards,
        Sarah Chen
        Senior Associate
        Confidential -- Attorney Work Product
    """)
    )
    return msg.as_string()


def _email_kim_to_park() -> str:
    msg = EmailMessage()
    msg["From"] = "Robert Kim <robert.kim@wilsondrake.com>"
    msg["To"] = "Lisa Park <lisa.park@pinnacle.com>"
    msg["Cc"] = "Sarah Chen <sarah.chen@lawfirm.com>"
    msg["Date"] = format_datetime(datetime(2025, 2, 10, 9, 45, 0, tzinfo=UTC))
    msg["Subject"] = "RE: SEC Inquiry Response Timeline"
    msg["Message-ID"] = "<20250210094500.def456@wilsondrake.com>"
    msg["In-Reply-To"] = "<20250208163000.xyz789@pinnacle.com>"
    msg["MIME-Version"] = "1.0"
    msg.set_content(
        textwrap.dedent("""\
        Lisa,

        Thank you for the updated document production schedule. I have reviewed
        the timeline and have the following comments.

        1. RESPONSE DEADLINE

        The SEC's voluntary document request does not impose a formal deadline,
        but we committed in our initial response letter to substantially
        complete production by March 1, 2025. Given the volume of responsive
        documents (approximately 8,000 pages), I believe we are on track,
        but we should not allow any slippage.

        2. MEETING ON FEBRUARY 15

        I have confirmed the meeting at your Denver office for February 15,
        2025, at 10:00 AM MST. The following individuals should attend:

            - Lisa Park (Pinnacle, CFO)
            - Robert Kim (Wilson & Drake LLP)
            - Sarah Chen (outside counsel to Acme Corp)
            - David Huang (Pinnacle, VP of Accounting)

        The purpose of the meeting is to review Pinnacle's revenue recognition
        methodology for long-term service contracts and prepare for potential
        follow-up questions from the SEC staff. Please ensure that the relevant
        accounting workpapers for fiscal years 2022 and 2023 are available.

        3. PRIVILEGE CONSIDERATIONS

        Please be aware that communications between Pinnacle and its counsel
        (including this email) are protected by the attorney-client privilege.
        Do not forward this message to any individual outside of the
        attorney-client relationship without consulting me first.

        Any documents shared with Acme Corp's counsel (Sarah Chen) in the
        context of merger due diligence should be subject to a common interest
        agreement. I understand that Michael Torres at Sarah's firm is
        preparing a draft of that agreement.

        4. STATUS OF INQUIRY

        As of today, the SEC has not escalated this matter beyond the
        voluntary request stage. We have had two telephone conferences with
        SEC staff (December 5, 2024, and January 14, 2025). In the most
        recent call, the staff indicated they are focused on the treatment of
        the Meridian Technologies contract (FY 2023, approximately $14.2M in
        recognized revenue) and the GlobalSync Logistics contract (FY 2022,
        approximately $9.8M). No Wells notice has been issued.

        I remain cautiously optimistic that this matter will be resolved
        through the voluntary process. However, we should continue to prepare
        as if formal proceedings are possible.

        Please do not hesitate to call me if you have questions.

        Best regards,

        Robert Kim
        Partner
        Wilson & Drake LLP
        1200 Seventeenth Street, Suite 2400
        Denver, CO 80202
        (303) 555-0142
        robert.kim@wilsondrake.com

        CONFIDENTIAL AND PRIVILEGED: This email and any attachments are
        intended only for the addressee and may contain information that is
        privileged, confidential, or exempt from disclosure. If you are not
        the intended recipient, please notify the sender immediately and
        delete this message.
    """)
    )
    return msg.as_string()


def _letter_reeves_board() -> str:
    return textwrap.dedent("""\
        ACME CORP
        1000 Innovation Drive
        San Jose, CA 95134

        January 20, 2025

        Board of Directors
        Acme Corp
        1000 Innovation Drive
        San Jose, CA 95134

        RE: Proposed Merger with Pinnacle Industries

        Dear Members of the Board,

        I am writing to provide you with an overview of the proposed merger
        between Acme Corp ("Acme" or the "Company") and Pinnacle Industries
        ("Pinnacle"), which I recommend the Board approve for further
        consideration and due diligence.

        STRATEGIC RATIONALE

        The combination of Acme and Pinnacle would create a market leader in
        enterprise data management solutions with combined annual revenues
        exceeding $280M. The strategic rationale for this transaction is
        compelling:

        1. Complementary Product Lines. Acme's strength in cloud-based data
           analytics complements Pinnacle's established on-premises data
           warehousing solutions. Together, we can offer a hybrid platform
           that addresses the full spectrum of enterprise needs.

        2. Customer Base Expansion. Pinnacle's customer base includes 45
           Fortune 500 companies that are not current Acme customers.
           Cross-selling opportunities are significant.

        3. Expected Synergies. Our preliminary analysis, conducted with
           input from Lisa Park (Pinnacle's CFO) and our financial advisors,
           projects annual cost synergies of approximately $50M within 24
           months of closing. These synergies derive primarily from:
               - Consolidation of overlapping R&D functions ($22M)
               - Shared sales and marketing infrastructure ($15M)
               - Operational efficiencies in data center operations ($13M)

        PROPOSED STRUCTURE

        The merger would be structured as a stock-for-stock transaction with
        an exchange ratio to be determined following completion of due
        diligence. Based on preliminary discussions, I anticipate an exchange
        ratio of approximately 1.35 Acme shares per Pinnacle share, implying
        a total transaction value of approximately $420M.

        INTEGRATION PLANNING

        I propose that we establish an integration committee co-chaired by:
            - Lisa Park, CFO of Pinnacle Industries
            - Michael Torres, outside counsel at our primary law firm

        The committee will be responsible for planning the post-merger
        integration, including organizational structure, technology platform
        consolidation, and customer communication strategy.

        DUE DILIGENCE

        Our outside counsel, led by Michael Torres and Sarah Chen, has begun
        the due diligence process. The due diligence period is expected to
        conclude by March 30, 2025. Key areas of focus include:

            - Financial audit and quality of earnings
            - Intellectual property portfolio review
            - Environmental compliance (particularly the Denver plant)
            - Pending SEC inquiry into revenue recognition practices
            - Key employee retention and non-compete agreements

        I want to be transparent with the Board about two matters that
        require careful evaluation:

        First, Pinnacle's Denver manufacturing plant has been identified as
        having potential environmental contamination issues. A Phase II
        environmental assessment is underway, and we expect results by
        mid-February.

        Second, the SEC has initiated a voluntary inquiry into Pinnacle's
        revenue recognition practices. Pinnacle's outside counsel, Robert Kim
        at Wilson & Drake LLP, has advised that he expects the matter to be
        resolved without enforcement action, but we are monitoring it closely.

        TIMELINE

        I propose the following timeline:

            Jan 15, 2025    Merger announcement (completed)
            Jan 20, 2025    Board briefing (this letter)
            Feb 15, 2025    Phase II environmental report expected
            Feb 20, 2025    Board update meeting
            Mar 30, 2025    Due diligence completion deadline
            Apr 15, 2025    Target date for definitive agreement
            Q3 2025         Regulatory approvals and closing

        RECOMMENDATION

        I strongly recommend that the Board authorize management to proceed
        with due diligence and negotiate a definitive merger agreement with
        Pinnacle Industries. This transaction represents a transformative
        opportunity for Acme Corp.

        I look forward to discussing this proposal at the Board meeting
        scheduled for January 25, 2025.

        Respectfully submitted,

        John Reeves
        Chief Executive Officer
        Acme Corp
    """)


def _financial_summary_csv() -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["entity", "metric", "value", "period"])
    rows = [
        ("Acme Corp", "Revenue", "68500000", "Q3 2024"),
        ("Acme Corp", "Operating Income", "12300000", "Q3 2024"),
        ("Acme Corp", "Net Income", "8900000", "Q3 2024"),
        ("Acme Corp", "Total Assets", "245000000", "Q3 2024"),
        ("Acme Corp", "Revenue", "71200000", "Q4 2024"),
        ("Acme Corp", "Operating Income", "13100000", "Q4 2024"),
        ("Acme Corp", "Net Income", "9400000", "Q4 2024"),
        ("Acme Corp", "Total Assets", "252000000", "Q4 2024"),
        ("Pinnacle Industries", "Revenue", "62100000", "Q3 2024"),
        ("Pinnacle Industries", "Operating Income", "9800000", "Q3 2024"),
        ("Pinnacle Industries", "Net Income", "6700000", "Q3 2024"),
        ("Pinnacle Industries", "Total Assets", "198000000", "Q3 2024"),
        ("Pinnacle Industries", "Revenue", "64800000", "Q4 2024"),
        ("Pinnacle Industries", "Operating Income", "10200000", "Q4 2024"),
        ("Pinnacle Industries", "Net Income", "7100000", "Q4 2024"),
        ("Pinnacle Industries", "Total Assets", "203000000", "Q4 2024"),
        ("Pinnacle Industries", "Environmental Reserve", "2000000", "Q4 2024"),
        ("Pinnacle Industries", "SEC Inquiry Related Legal Costs", "450000", "Q4 2024"),
    ]
    writer.writerows(rows)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# File definitions
# ---------------------------------------------------------------------------

FILES: list[tuple[str, callable]] = [
    ("memo_acme_merger.txt", _memo_acme_merger),
    ("memo_privilege_review.txt", _memo_privilege_review),
    ("email_chen_to_torres.eml", _email_chen_to_torres),
    ("email_kim_to_park.eml", _email_kim_to_park),
    ("letter_reeves_board.txt", _letter_reeves_board),
    ("financial_summary.csv", _financial_summary_csv),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Generating test documents in {OUTPUT_DIR}/\n")

    for filename, generator in FILES:
        path = OUTPUT_DIR / filename
        content = generator()
        path.write_text(content, encoding="utf-8")
        size_kb = path.stat().st_size / 1024
        print(f"  {filename:<35s} {size_kb:>6.1f} KB")

    print(f"\nDone. {len(FILES)} files written to {OUTPUT_DIR}/")
    print("\nEntity overlap across documents:")
    print("  People:        Sarah Chen, Michael Torres, John Reeves, Lisa Park, Robert Kim")
    print("  Organizations: Acme Corp, Pinnacle Industries, Wilson & Drake LLP, SEC")
    print("  Locations:     Denver plant (4500 Industrial Blvd, Denver, CO)")
    print("  Key dates:     Jan 15 2025 (announcement), Mar 30 2025 (deadline)")
    print("  Key issues:    Environmental liability, SEC inquiry, merger due diligence")


if __name__ == "__main__":
    main()
