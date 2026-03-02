"""Generate a synthetic legal corpus for end-to-end testing of the NEXUS platform.

Creates 14 documents with overlapping entities, dates, and legal issues that
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


def _email_park_to_reeves() -> str:
    msg = EmailMessage()
    msg["From"] = "Lisa Park <lisa.park@pinnacle.com>"
    msg["To"] = "John Reeves <john.reeves@acme.com>"
    msg["Date"] = format_datetime(datetime(2025, 2, 12, 16, 10, 0, tzinfo=UTC))
    msg["Subject"] = "RE: Environmental Reserve Discussion"
    msg["Message-ID"] = "<20250212161000.ghi789@pinnacle.com>"
    msg["In-Reply-To"] = "<20250211083000.jkl012@acme.com>"
    msg["MIME-Version"] = "1.0"
    msg.set_content(
        textwrap.dedent("""\
        John,

        Thank you for your patience as we worked through the numbers on our end.

        After consulting with our board's audit committee yesterday, I can confirm
        that Pinnacle is prepared to increase the environmental reserve from $2M
        to $3.5M. This reflects our updated estimate based on preliminary Phase II
        data from EcoTech Environmental Consultants.

        Key points for your consideration:

        1. RESERVE INCREASE
           The $3.5M reserve covers estimated remediation of TCE contamination
           at the Denver Plant. This figure is based on the mid-range scenario
           in EcoTech's preliminary assessment. The full Phase II report is
           expected by February 15, 2025, and may refine this estimate.

        2. INDEMNIFICATION PROPOSAL
           Robert Kim at Wilson & Drake is drafting an indemnification provision
           that would cap Acme's exposure at $5M for environmental matters
           discovered during the first 36 months post-closing. Any costs above
           the $3.5M reserve but below the $5M cap would be shared 60/40
           (Pinnacle/Acme).

        3. INSURANCE COVERAGE
           Our environmental insurance policy (AIG, Policy No. ENV-2023-44891)
           provides up to $10M in coverage for pre-existing conditions discovered
           during ownership transition. Robert Kim is reviewing whether the TCE
           contamination qualifies under the policy terms.

        4. BOARD APPROVAL TIMELINE
           Our board meets on February 18, 2025, to formally approve the
           increased reserve. I do not anticipate any opposition — the audit
           committee has already endorsed the figure.

        I suggest we schedule a call with Michael Torres and Sarah Chen from your
        legal team to discuss the indemnification framework before the February 20
        board update on your side.

        Please let me know your availability.

        Best regards,

        Lisa Park
        Chief Financial Officer
        Pinnacle Industries
        (303) 555-0298
        lisa.park@pinnacle.com
    """)
    )
    return msg.as_string()


def _email_torres_to_team() -> str:
    msg = EmailMessage()
    msg["From"] = "Michael Torres <michael.torres@lawfirm.com>"
    msg["To"] = "team@lawfirm.com"
    msg["Cc"] = "Sarah Chen <sarah.chen@lawfirm.com>"
    msg["Date"] = format_datetime(datetime(2025, 2, 14, 8, 30, 0, tzinfo=UTC))
    msg["Subject"] = "Acme/Pinnacle -- Status Update and Action Items"
    msg["Message-ID"] = "<20250214083000.mno345@lawfirm.com>"
    msg["MIME-Version"] = "1.0"
    msg.set_content(
        textwrap.dedent("""\
        Team,

        Quick status update on the Acme Corp / Pinnacle Industries matter as we
        approach several critical deadlines.

        CURRENT STATUS

        1. Environmental (Sarah Chen leading)
           - Phase II report from EcoTech expected tomorrow (Feb 15)
           - Pinnacle has increased environmental reserve to $3.5M
           - Indemnification cap of $5M being drafted by Robert Kim
           - CDPHE inspection reports from 2015-2024 received and under review

        2. SEC Inquiry (Sarah Chen leading)
           - Meeting at Pinnacle Denver office scheduled Feb 15 at 10 AM
           - Attendees: Lisa Park, Robert Kim, Sarah Chen, David Huang
           - Focus: Meridian Technologies ($14.2M) and GlobalSync Logistics ($9.8M)
           - No Wells notice issued; staff-level voluntary process continues

        3. Common Interest Agreement
           - Draft circulated to Robert Kim on Feb 10
           - Awaiting comments; expected turnaround by Feb 17
           - Critical for protecting shared privilege in joint defense materials

        4. Financial Due Diligence
           - Quality of earnings review 60% complete
           - Combined revenue exceeds $280M annually
           - Synergy estimate of $50M within 24 months appears reasonable

        ACTION ITEMS (by Feb 20 board meeting)

           [ ] Sarah: Summarize Phase II findings for board presentation
           [ ] Sarah: Prepare SEC inquiry risk assessment memo
           [ ] Associates: Complete Tier 2 privilege review (currently at 65%)
           [ ] Me: Finalize common interest agreement with Robert Kim
           [ ] Me: Brief John Reeves on indemnification framework

        TIMELINE REMINDER

           Feb 15    Phase II report + SEC meeting
           Feb 17    Common interest agreement finalized
           Feb 18    Pinnacle board approves increased reserve
           Feb 20    Acme board update meeting
           Mar 15    Tier 2 privilege review complete
           Mar 30    Due diligence deadline

        This matter is tracking well but the next two weeks are critical. Please
        prioritize Acme/Pinnacle work over other matters during this period.

        Thanks,
        Michael Torres
        Partner

        PRIVILEGED AND CONFIDENTIAL — ATTORNEY WORK PRODUCT
    """)
    )
    return msg.as_string()


def _contract_excerpt_merger() -> str:
    return textwrap.dedent("""\
        DRAFT — SUBJECT TO REVISION
        PRIVILEGED AND CONFIDENTIAL

        AGREEMENT AND PLAN OF MERGER

        by and among

        ACME CORP,
        a Delaware corporation ("Parent"),

        PINNACLE INDUSTRIES, INC.,
        a Colorado corporation (the "Company"),

        and

        ALPINE MERGER SUB, INC.,
        a Colorado corporation and wholly owned subsidiary of Parent ("Merger Sub")

        Dated as of [________], 2025

        ===================================================================

        ARTICLE I — THE MERGER

        Section 1.1  The Merger. Upon the terms and subject to the conditions
        set forth in this Agreement, and in accordance with the Colorado
        Business Corporation Act (the "CBCA"), at the Effective Time, Merger
        Sub shall be merged with and into the Company (the "Merger"), with
        the Company surviving the Merger as a wholly owned subsidiary of
        Parent (the "Surviving Corporation").

        Section 1.2  Closing Date. The closing of the Merger (the "Closing")
        shall take place on the third business day following the satisfaction
        or waiver of the conditions set forth in Article VII (other than those
        conditions that by their nature can only be satisfied at the Closing),
        unless another date is agreed to in writing by the parties (the
        "Closing Date"). The target Closing Date is [Q3 2025].

        ===================================================================

        ARTICLE V — REPRESENTATIONS AND WARRANTIES OF THE COMPANY

        Section 5.15  Environmental Matters.

        (a) Except as set forth in Section 5.15 of the Company Disclosure
        Schedule, the Company and its Subsidiaries are in compliance in
        all material respects with all applicable Environmental Laws.

        (b) "Environmental Cap" means the aggregate amount of Five Million
        Dollars ($5,000,000) with respect to Losses arising out of or
        related to the environmental condition of the Denver Plant (as
        defined in Section 5.15(c)).

        (c) "Denver Plant" means the manufacturing facility located at
        4500 Industrial Blvd, Denver, CO 80216, including all buildings,
        improvements, fixtures, and underlying real property.

        (d) "Material Adverse Change" or "Material Adverse Effect" means
        any change, event, occurrence, or development that, individually
        or in the aggregate, has had or would reasonably be expected to
        have a material adverse effect on (i) the business, assets,
        liabilities, financial condition, or results of operations of
        the Company and its Subsidiaries, taken as a whole, or (ii) the
        ability of the Company to consummate the Merger; provided,
        however, that none of the following shall constitute a Material
        Adverse Change: [market conditions, industry changes, etc.]

        ===================================================================

        ARTICLE VIII — INDEMNIFICATION

        Section 8.3  Environmental Indemnification.

        (a) The Company shall indemnify Parent against any Losses arising
        from the environmental condition of the Denver Plant, subject to
        the Environmental Cap.

        (b) The first Three Million Five Hundred Thousand Dollars ($3,500,000)
        of such Losses shall be borne exclusively by the Company from
        the Environmental Reserve established pursuant to Section 5.15(e).

        (c) Losses between $3,500,000 and the Environmental Cap shall be
        shared sixty percent (60%) by the Company and forty percent (40%)
        by Parent.

        ===================================================================

        [REMAINDER OF AGREEMENT INTENTIONALLY OMITTED — DRAFT IN PROGRESS]

        Prepared by: Wilson & Drake LLP
        Contact: Robert Kim, Partner
        Date: February 2025
    """)


def _memo_environmental_assessment() -> str:
    return textwrap.dedent("""\
        ECOTECH ENVIRONMENTAL CONSULTANTS
        Phase II Environmental Site Assessment — Preliminary Findings
        ===================================================================

        Site:           Pinnacle Industries Denver Manufacturing Facility
        Address:        4500 Industrial Blvd, Denver, CO 80216
        Client:         Wilson & Drake LLP (on behalf of Pinnacle Industries)
        Project No:     ECT-2024-1847
        Date:           February 14, 2025
        Prepared by:    Dr. Amanda Reyes, P.E., Senior Environmental Engineer
        Reviewed by:    James Whitfield, P.G., Principal Geologist

        ===================================================================

        1. EXECUTIVE SUMMARY

        EcoTech Environmental Consultants ("EcoTech") was retained by Wilson &
        Drake LLP, on behalf of Pinnacle Industries, Inc. ("Pinnacle"), to
        conduct a Phase II Environmental Site Assessment ("ESA") at the Denver
        manufacturing facility (the "Site"). This assessment follows the Phase I
        ESA completed in September 2024, which identified recognized
        environmental conditions ("RECs") associated with historical solvent use.

        PRINCIPAL FINDINGS:

        Trichloroethylene ("TCE") contamination has been confirmed in
        groundwater at concentrations exceeding the Colorado Department of
        Public Health and Environment ("CDPHE") Regulation 41 groundwater
        quality standards in two of six monitoring wells.

        - Well MW-3 (eastern boundary): TCE at 12.4 ug/L (standard: 5.0 ug/L)
        - Well MW-5 (southeast corner): TCE at 8.7 ug/L (standard: 5.0 ug/L)
        - Wells MW-1, MW-2, MW-4, MW-6: Below detection limits

        The contamination plume appears to originate from the former solvent
        storage area near Building C and extends approximately 200 feet toward
        the eastern property boundary.

        2. SITE HISTORY

        The Site has been used for manufacturing since 1978. Historical records
        indicate that chlorinated solvents, including TCE and perchloroethylene
        ("PCE"), were used as degreasing agents in the machining operations
        conducted in Building C from approximately 1982 through 2003.

        Three underground storage tanks ("USTs") were removed in 2005. Tank
        closure reports (Colorado OPS File Nos. 12-4478, 12-4479, 12-4480)
        indicated minor soil staining but no groundwater impacts at that time.

        3. REMEDIATION COST ESTIMATES

        Based on the current extent of contamination and applicable CDPHE
        standards, EcoTech has developed the following remediation cost
        estimates under three scenarios:

        Low Scenario (limited plume, in-situ treatment):
            - Monitored Natural Attenuation + Enhanced Bioremediation
            - Estimated cost: $3.2M over 5 years
            - Timeline: 3-5 years to achieve compliance

        Mid Scenario (moderate plume, active treatment):
            - Groundwater Pump-and-Treat + Soil Vapor Extraction
            - Estimated cost: $5.1M over 7 years
            - Timeline: 5-7 years to achieve compliance

        High Scenario (extended plume, aggressive treatment):
            - Full-Scale Pump-and-Treat + Thermal Remediation
            - Estimated cost: $7.8M over 10 years
            - Timeline: 7-10 years to achieve compliance

        4. REGULATORY STATUS

        The Site is not currently listed on the CDPHE Contaminated Sites list
        or the EPA National Priorities List. However, based on these findings,
        notification to CDPHE under the Voluntary Cleanup Program may be
        advisable. Robert Kim of Wilson & Drake LLP has been advised of this
        recommendation.

        5. RECOMMENDATIONS

        (a) Install two additional monitoring wells (MW-7, MW-8) along the
            eastern boundary to delineate the full extent of the plume.
        (b) Conduct quarterly groundwater monitoring for a minimum of one year.
        (c) Evaluate in-situ bioremediation pilot testing in the vicinity
            of MW-3 and MW-5.
        (d) Notify CDPHE and consider enrollment in the Voluntary Cleanup
            Program to obtain a No Further Action determination upon
            completion of remediation.

        ===================================================================
        This report was prepared for the exclusive use of Wilson & Drake LLP
        and Pinnacle Industries. Distribution to third parties requires
        written consent from EcoTech Environmental Consultants.

        EcoTech Environmental Consultants
        8900 E. Hampden Ave, Suite 200
        Denver, CO 80231
        (303) 555-0175
    """)


def _email_chen_to_kim() -> str:
    msg = EmailMessage()
    msg["From"] = "Sarah Chen <sarah.chen@lawfirm.com>"
    msg["To"] = "Robert Kim <robert.kim@wilsondrake.com>"
    msg["Date"] = format_datetime(datetime(2025, 2, 16, 11, 5, 0, tzinfo=UTC))
    msg["Subject"] = "Common Interest Agreement — Draft Comments"
    msg["Message-ID"] = "<20250216110500.pqr678@lawfirm.com>"
    msg["In-Reply-To"] = "<20250210094500.def456@wilsondrake.com>"
    msg["MIME-Version"] = "1.0"
    msg.set_content(
        textwrap.dedent("""\
        Robert,

        I hope the meeting with Lisa Park and David Huang went well yesterday.
        Michael Torres and I reviewed the Phase II preliminary findings from
        EcoTech and have the following observations.

        ENVIRONMENTAL ASSESSMENT

        The TCE contamination at MW-3 (12.4 ug/L) and MW-5 (8.7 ug/L) is
        concerning but not unexpected given the Phase I findings. The mid-range
        remediation estimate of $5.1M is within the range we discussed with
        John Reeves. The proposed $5M environmental cap in the merger agreement
        should be sufficient if the low-to-mid scenario materializes.

        We recommend that the merger agreement include:
        - A requirement for Pinnacle to enroll in CDPHE Voluntary Cleanup
        - Quarterly monitoring reports shared with Acme for 3 years post-closing
        - A mechanism to adjust the 60/40 cost-sharing if the plume extends
          beyond the current delineation

        COMMON INTEREST AGREEMENT

        Attached are our comments on the draft common interest agreement. Key
        changes:
        1. Broadened the scope to include SEC inquiry materials (not just
           environmental — we need shared privilege for the revenue recognition
           documents as well)
        2. Added a provision for joint defense meetings
        3. Clarified that the agreement survives termination of merger talks

        Michael would like to schedule a call with you on Monday, February 17,
        to finalize. Would 2:00 PM MST work?

        SEC INQUIRY UPDATE

        One more item — after our meeting yesterday, Lisa mentioned that the SEC
        staff has requested supplemental documents related to the Meridian
        Technologies contract. Specifically, they want the original proposal,
        the executed contract, and all change orders. David Huang indicated
        these would be available by end of week.

        This is a normal progression in a voluntary inquiry. However, we should
        coordinate our review of these documents before production to ensure
        nothing privileged is inadvertently disclosed.

        Best regards,
        Sarah Chen
        Senior Associate

        PRIVILEGED AND CONFIDENTIAL — ATTORNEY WORK PRODUCT
    """)
    )
    return msg.as_string()


def _timeline_of_events() -> str:
    return textwrap.dedent("""\
        ACME CORP / PINNACLE INDUSTRIES MERGER
        CHRONOLOGICAL TIMELINE OF KEY EVENTS
        ===================================================================

        Prepared by: Sarah Chen, Senior Associate
        Last updated: February 16, 2025
        Status: WORKING DRAFT — ATTORNEY WORK PRODUCT

        ===================================================================

        2003-06-30   Pinnacle Industries discontinues use of chlorinated
                     solvents (TCE, PCE) in Building C machining operations
                     at the Denver Plant.

        2005-03-15   Three underground storage tanks removed from the Denver
                     Plant. Closure reports filed with Colorado OPS (File
                     Nos. 12-4478, 12-4479, 12-4480). Minor soil staining
                     noted; no groundwater impacts detected.

        2019-08-22   CDPHE routine inspection of Denver Plant. Minor
                     violations cited for hazardous waste storage labeling.
                     Violations corrected within 30 days.

        2022-01-15   Pinnacle Industries enters into long-term service
                     contract with GlobalSync Logistics. Contract value:
                     $9.8M over 3 years. Revenue recognition begins under
                     ASC 606.

        2023-04-01   Pinnacle Industries enters into long-term service
                     contract with Meridian Technologies. Contract value:
                     $14.2M over 4 years. Revenue recognized over performance
                     period per ASC 606.

        2024-09-10   Phase I Environmental Site Assessment conducted at
                     Denver Plant by EcoTech Environmental Consultants
                     (Project No. ECT-2024-1847). Recognized Environmental
                     Conditions identified related to historical solvent use.

        2024-11-08   SEC Division of Enforcement issues voluntary document
                     request to Pinnacle Industries. Focus: revenue
                     recognition practices in FY 2022 and FY 2023,
                     specifically the Meridian Technologies and GlobalSync
                     Logistics contracts.

        2024-12-05   First telephone conference between Pinnacle (Lisa Park,
                     Robert Kim) and SEC staff regarding voluntary inquiry.

        2025-01-14   Second telephone conference with SEC staff. Staff
                     indicates focus on Meridian Technologies contract
                     ($14.2M recognized revenue) and GlobalSync Logistics
                     contract ($9.8M). No Wells notice issued.

        2025-01-15   Acme Corp and Pinnacle Industries publicly announce
                     proposed merger. Stock-for-stock transaction at
                     approximately 1.35 exchange ratio. Total transaction
                     value: ~$420M.

        2025-01-20   John Reeves (CEO, Acme) sends letter to Acme Board of
                     Directors outlining merger rationale, due diligence plan,
                     and known risk factors (environmental, SEC inquiry).

        2025-01-22   John Reeves and Sarah Chen discuss environmental
                     remediation costs. Reeves states Acme board requires
                     remediation cost cap before proceeding.

        2025-01-25   Sarah Chen completes due diligence summary memorandum
                     for Michael Torres. Identifies environmental liability
                     and SEC inquiry as primary risk areas.

        2025-01-25   Acme Board of Directors meeting. Board authorizes
                     management to proceed with due diligence.

        2025-02-01   Sarah Chen emails Michael Torres with update on
                     environmental concerns. Reports Reeves wants $5M cap;
                     Lisa Park may increase Pinnacle reserve to $3.5M.

        2025-02-05   Michael Torres issues privilege review protocol memo
                     to litigation team. Establishes three-tier review process.

        2025-02-10   Robert Kim emails Lisa Park (cc: Sarah Chen) regarding
                     SEC response timeline. Meeting scheduled for Feb 15.
                     Common interest agreement under preparation.

        2025-02-12   Lisa Park confirms to John Reeves that Pinnacle will
                     increase environmental reserve to $3.5M. Indemnification
                     proposal: $5M cap with 60/40 cost sharing above reserve.

        2025-02-14   Michael Torres sends team-wide status update. Phase II
                     report expected Feb 15. SEC meeting same day.

        2025-02-14   EcoTech Environmental releases preliminary Phase II
                     findings. TCE confirmed at MW-3 (12.4 ug/L) and MW-5
                     (8.7 ug/L). Remediation cost range: $3.2M-$7.8M.

        2025-02-15   Meeting at Pinnacle Denver office: Lisa Park, Robert
                     Kim, Sarah Chen, David Huang. Revenue recognition
                     methodology review for SEC inquiry.

        2025-02-16   Sarah Chen sends common interest agreement comments to
                     Robert Kim. Broadens scope to include SEC materials.

        ===================================================================

        UPCOMING MILESTONES

        2025-02-17   Common interest agreement finalization call
        2025-02-18   Pinnacle board approves increased environmental reserve
        2025-02-20   Acme Board update meeting
        2025-03-01   SEC document production substantially complete
        2025-03-15   Tier 2 privilege review complete
        2025-03-30   Due diligence completion deadline
        2025-04-15   Target date for definitive merger agreement
        Q3 2025      Regulatory approvals and closing (target)

        ===================================================================
        PRIVILEGED AND CONFIDENTIAL — ATTORNEY WORK PRODUCT
    """)


def _board_minutes_jan25() -> str:
    return textwrap.dedent("""\
        ACME CORP
        MINUTES OF THE BOARD OF DIRECTORS
        REGULAR MEETING — JANUARY 25, 2025

        ===================================================================

        PRESENT:
            John Reeves, Chief Executive Officer and Chairman
            Margaret Liu, Independent Director
            Thomas Bradley, Independent Director
            Patricia Fernandez, Independent Director
            David Park, Independent Director (no relation to Lisa Park)

        ALSO PRESENT:
            Michael Torres, Partner, outside counsel
            Sarah Chen, Senior Associate, outside counsel
            Jennifer Walsh, Corporate Secretary

        ABSENT:
            None

        LOCATION:
            Acme Corp headquarters, 1000 Innovation Drive, San Jose, CA

        CALL TO ORDER:
            The meeting was called to order at 9:00 AM PST by Chairman Reeves.

        ===================================================================

        1. APPROVAL OF MINUTES

        MOTION: Director Bradley moved to approve the minutes of the December 12,
        2024 regular meeting. Seconded by Director Liu.
        VOTE: Approved unanimously (5-0).

        ===================================================================

        2. CEO REPORT — PROPOSED MERGER WITH PINNACLE INDUSTRIES

        Chairman Reeves presented the proposed merger with Pinnacle Industries,
        Inc., referring the Board to his letter dated January 20, 2025,
        previously distributed to all directors.

        Key points of the presentation:

        (a) Strategic Rationale: Combined entity would have revenues exceeding
            $280M. Complementary product lines in cloud analytics (Acme) and
            on-premises data warehousing (Pinnacle). Estimated $50M in annual
            cost synergies within 24 months.

        (b) Transaction Structure: Stock-for-stock merger at approximately
            1.35 exchange ratio. Total transaction value approximately $420M.
            Alpine Merger Sub, Inc. to be created as a wholly owned subsidiary
            for the reverse triangular merger.

        (c) Risk Factors: Chairman Reeves disclosed two areas of concern:
            - Environmental contamination at Pinnacle's Denver manufacturing
              plant (4500 Industrial Blvd, Denver, CO). Phase II assessment
              underway by EcoTech Environmental Consultants. Estimated
              remediation costs: $3.2M to $7.8M.
            - SEC voluntary inquiry into Pinnacle's revenue recognition
              practices for FY 2022-2023. No formal investigation or Wells
              notice issued. Outside counsel Robert Kim of Wilson & Drake LLP
              is coordinating Pinnacle's response.

        (d) Due Diligence Plan: Michael Torres outlined the due diligence
            scope and timeline. Key deadline: March 30, 2025. Sarah Chen is
            leading the day-to-day document review and analysis.

        Director Fernandez asked about the environmental exposure. Michael
        Torres responded that remediation cost estimates range from $3.2M to
        $7.8M, and that the merger agreement will include an indemnification
        provision with an environmental cap. Lisa Park (Pinnacle CFO) has
        indicated willingness to increase Pinnacle's environmental reserve.

        Director Liu inquired about the SEC inquiry's potential impact on
        closing. Torres advised that Robert Kim believes the matter will be
        resolved through the voluntary process, but recommended that the
        merger agreement include a condition precedent tied to SEC resolution.

        Director Bradley raised the question of employee retention at
        Pinnacle. Chairman Reeves stated that key employee retention
        agreements would be negotiated as part of the definitive agreement.

        MOTION: Director Liu moved to authorize management to proceed with
        due diligence and negotiate a definitive merger agreement with
        Pinnacle Industries, Inc., subject to Board approval of the final
        terms. Seconded by Director Fernandez.
        VOTE: Approved unanimously (5-0).

        ===================================================================

        3. FINANCIAL UPDATE — Q4 2024

        Chairman Reeves presented the Q4 2024 financial summary:

            Revenue:           $71.2M (up 3.9% from Q3)
            Operating Income:  $13.1M (up 6.5% from Q3)
            Net Income:        $9.4M (up 5.6% from Q3)
            Total Assets:      $252M

        The Board noted the continued positive financial trajectory.

        ===================================================================

        4. EXECUTIVE SESSION

        At 11:30 AM, the Board entered executive session (independent
        directors only) to discuss CEO compensation and merger-related
        executive retention matters.

        [Executive session minutes maintained separately by Corporate Secretary]

        ===================================================================

        5. ADJOURNMENT

        There being no further business, the meeting was adjourned at
        12:15 PM PST.

        MOTION: Director Bradley moved to adjourn. Seconded by Director Park.
        VOTE: Approved unanimously (5-0).

        ___________________________________
        Jennifer Walsh, Corporate Secretary

        Date approved: ___________________
    """)


def _memo_financial_analysis() -> str:
    return textwrap.dedent("""\
        PRIVILEGED AND CONFIDENTIAL
        ATTORNEY WORK PRODUCT

        MEMORANDUM

        TO:      Michael Torres, Partner
        FROM:    Sarah Chen, Senior Associate
        DATE:    February 18, 2025
        RE:      Financial Analysis — Acme/Pinnacle Merger Valuation Implications

        -----------------------------------------------------------------------

        I. PURPOSE

        This memorandum analyzes the financial implications of the proposed
        merger between Acme Corp and Pinnacle Industries, with particular
        attention to risk factors that may affect the transaction valuation.

        II. COMBINED ENTITY FINANCIALS

        Based on the most recent quarterly filings (Q4 2024):

        ACME CORP (Q4 2024)
            Revenue:           $71.2M (annualized: ~$280M)
            Operating Income:  $13.1M (margin: 18.4%)
            Net Income:        $9.4M (margin: 13.2%)
            Total Assets:      $252M

        PINNACLE INDUSTRIES (Q4 2024)
            Revenue:           $64.8M (annualized: ~$256M)
            Operating Income:  $10.2M (margin: 15.7%)
            Net Income:        $7.1M (margin: 11.0%)
            Total Assets:      $203M

        COMBINED (pro forma)
            Revenue:           $136.0M quarterly (~$536M annualized)
            Operating Income:  $23.3M quarterly
            Total Assets:      $455M
            Expected Synergies: $50M annually (within 24 months)

        III. RISK-ADJUSTED VALUATION FACTORS

        A. Environmental Liability Impact

        The Phase II assessment by EcoTech Environmental Consultants
        (February 14, 2025) establishes a remediation cost range of $3.2M
        to $7.8M for TCE contamination at the Denver Plant.

        Under the proposed deal terms:
            - Pinnacle environmental reserve: $3.5M (absorbs low scenario)
            - Environmental cap: $5M (shared 60/40 above reserve)
            - Maximum Acme exposure: $600K (40% of $1.5M above reserve)
            - Worst case beyond cap: Requires renegotiation or insurance claim

        Risk-adjusted environmental cost to Acme: ~$400K (probability-weighted)
        Impact on transaction value: Negligible (<0.1% of $420M deal value)

        B. SEC Inquiry Impact

        The SEC voluntary inquiry regarding Meridian Technologies ($14.2M,
        FY 2023) and GlobalSync Logistics ($9.8M, FY 2022) introduces
        uncertainty but has not escalated to formal investigation.

        Scenario analysis:
            1. No action (70% probability): Zero impact
            2. Restatement (20% probability): Revenue adjustment of ~$5M,
               reducing Pinnacle trailing revenue by ~2%. Potential exchange
               ratio adjustment of 0.02-0.03x.
            3. Enforcement (10% probability): Fines estimated at $1-3M plus
               legal costs. Potential delay of 3-6 months. Material impact
               on deal certainty.

        Probability-weighted SEC cost: ~$1.4M
        Recommended: Include MAC clause covering SEC escalation beyond
        voluntary inquiry stage.

        C. Synergy Realization Risk

        The $50M annual synergy target breaks down as:
            - R&D consolidation: $22M (HIGH confidence)
            - Sales & marketing: $15M (MEDIUM confidence)
            - Data center operations: $13M (MEDIUM confidence)

        Conservative realization estimate: $38M (76% of target)
        This still supports the proposed exchange ratio.

        IV. COUNTERPARTY ANALYSIS

        Meridian Technologies (Pinnacle client since 2023):
            - $14.2M service contract over 4 years
            - Revenue recognition methodology: percentage-of-completion
            - SEC focus area: timing of milestone recognition
            - Risk: Potential restatement of $2-3M if milestones are recharacterized

        GlobalSync Logistics (Pinnacle client since 2022):
            - $9.8M service contract over 3 years
            - Revenue recognition methodology: output method
            - SEC focus area: allocation of variable consideration
            - Risk: Potential restatement of $1-2M

        V. RECOMMENDATIONS

        1. Proceed with merger at proposed terms. Risk-adjusted costs are
           manageable within the deal structure.
        2. Include SEC-related MAC clause in definitive agreement.
        3. Negotiate environmental monitoring reporting obligations for
           3 years post-closing.
        4. Build $2M contingency into integration budget for SEC-related
           costs.

        -----------------------------------------------------------------------
        This memorandum is protected by the attorney-client privilege and the
        work product doctrine. Do not distribute outside the firm.
    """)


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
    ("email_park_to_reeves.eml", _email_park_to_reeves),
    ("email_torres_to_team.eml", _email_torres_to_team),
    ("contract_excerpt_merger.txt", _contract_excerpt_merger),
    ("memo_environmental_assessment.txt", _memo_environmental_assessment),
    ("email_chen_to_kim.eml", _email_chen_to_kim),
    ("timeline_of_events.txt", _timeline_of_events),
    ("board_minutes_jan25.txt", _board_minutes_jan25),
    ("memo_financial_analysis.txt", _memo_financial_analysis),
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
    print("  People:        Sarah Chen, Michael Torres, John Reeves, Lisa Park, Robert Kim,")
    print("                 David Huang, Dr. Amanda Reyes, Margaret Liu, Thomas Bradley")
    print("  Organizations: Acme Corp, Pinnacle Industries, Wilson & Drake LLP, SEC,")
    print("                 EcoTech Environmental, Meridian Technologies, GlobalSync Logistics")
    print("  Locations:     Denver Plant (4500 Industrial Blvd, Denver, CO)")
    print("  Key dates:     Jan 15 2025 (announcement), Mar 30 2025 (deadline)")
    print("  Key issues:    Environmental liability ($3.2M-$7.8M), SEC inquiry,")
    print("                 merger due diligence, common interest agreement")


if __name__ == "__main__":
    main()
