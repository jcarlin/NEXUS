#!/usr/bin/env python3
"""Seed the Epstein Files investigation matter in NEXUS.

Creates:
  - case_matters row for the Epstein investigation
  - Links admin user to the matter
  - Seeds initial case_parties (key individuals)
  - Seeds initial case_claims (primary legal theories)
  - Seeds case_defined_terms (key legal terms)
  - Creates a datasets row for the House Oversight release

Idempotent: safe to run multiple times (uses ON CONFLICT / upserts).

Usage::

    python scripts/seed_epstein_matter.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine, text

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Settings

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MATTER_ID = "00000000-0000-0000-0000-000000000002"
_MATTER_NAME = "Epstein Files Investigation"
_MATTER_DESC = (
    "Investigation of Jeffrey Epstein network using House Oversight Committee "
    "documents released November 2025. 20,000+ pages of depositions, flight "
    "logs, correspondence, and law enforcement records."
)


def main() -> None:
    settings = Settings()
    engine = create_engine(settings.postgres_url_sync, pool_pre_ping=True)
    now = datetime.now(UTC)

    with engine.connect() as conn:
        # ---------------------------------------------------------------
        # 1. Create matter
        # ---------------------------------------------------------------
        conn.execute(
            text("""
                INSERT INTO case_matters (id, name, description, created_at, updated_at)
                VALUES (:id, :name, :desc, :now, :now)
                ON CONFLICT (id) DO UPDATE SET name = :name, description = :desc, updated_at = :now
            """),
            {"id": _MATTER_ID, "name": _MATTER_NAME, "desc": _MATTER_DESC, "now": now},
        )
        print(f"  Matter: {_MATTER_NAME} ({_MATTER_ID})")

        # ---------------------------------------------------------------
        # 2. Link admin user(s) to matter
        # ---------------------------------------------------------------
        admin_rows = conn.execute(text("SELECT id FROM users WHERE role = 'admin'")).fetchall()
        for row in admin_rows:
            conn.execute(
                text("""
                    INSERT INTO user_case_matters (user_id, matter_id)
                    VALUES (:uid, :mid)
                    ON CONFLICT DO NOTHING
                """),
                {"uid": row.id, "mid": _MATTER_ID},
            )
        print(f"  Linked {len(admin_rows)} admin user(s) to matter")

        # ---------------------------------------------------------------
        # 3. Case context
        # ---------------------------------------------------------------
        context_id = uuid4()
        conn.execute(
            text("""
                INSERT INTO case_contexts
                    (id, matter_id, status, timeline, created_at, updated_at)
                VALUES
                    (:id, :mid, 'confirmed', :timeline::json, :now, :now)
                ON CONFLICT (matter_id) DO UPDATE
                    SET status = 'confirmed', timeline = :timeline::json, updated_at = :now
                RETURNING id
            """),
            {
                "id": context_id,
                "mid": _MATTER_ID,
                "timeline": json.dumps(
                    [
                        {
                            "date": "2006-06-30",
                            "event_text": "Epstein indicted in Palm Beach County",
                            "source_page": None,
                        },
                        {
                            "date": "2007-06-30",
                            "event_text": "Non-prosecution agreement signed with SDFL",
                            "source_page": None,
                        },
                        {
                            "date": "2008-06-30",
                            "event_text": "Epstein pleads guilty to state charges",
                            "source_page": None,
                        },
                        {
                            "date": "2019-07-06",
                            "event_text": "Epstein arrested by SDNY on federal charges",
                            "source_page": None,
                        },
                        {"date": "2019-08-10", "event_text": "Epstein found dead in MCC New York", "source_page": None},
                        {"date": "2020-07-02", "event_text": "Ghislaine Maxwell arrested", "source_page": None},
                        {
                            "date": "2021-12-29",
                            "event_text": "Maxwell convicted on trafficking charges",
                            "source_page": None,
                        },
                        {
                            "date": "2025-11-01",
                            "event_text": "House Oversight Committee releases 20,000+ pages",
                            "source_page": None,
                        },
                    ]
                ),
                "now": now,
            },
        )
        # Retrieve actual context_id
        ctx_row = conn.execute(
            text("SELECT id FROM case_contexts WHERE matter_id = :mid"),
            {"mid": _MATTER_ID},
        ).first()
        actual_ctx_id = ctx_row.id if ctx_row else context_id
        print(f"  Case context: {str(actual_ctx_id)[:8]}...")

        # Delete existing child rows for idempotency
        conn.execute(text("DELETE FROM case_claims WHERE case_context_id = :cid"), {"cid": actual_ctx_id})
        conn.execute(text("DELETE FROM case_parties WHERE case_context_id = :cid"), {"cid": actual_ctx_id})
        conn.execute(text("DELETE FROM case_defined_terms WHERE case_context_id = :cid"), {"cid": actual_ctx_id})

        # ---------------------------------------------------------------
        # 4. Case parties
        # ---------------------------------------------------------------
        parties = [
            ("Jeffrey Epstein", "defendant", "Convicted sex offender, financier"),
            ("Ghislaine Maxwell", "defendant", "Convicted co-conspirator, socialite"),
            ("Jean-Luc Brunel", "third_party", "Modeling agent, MC2 founder"),
            ("Sarah Kellen", "third_party", "Personal assistant to Epstein"),
            ("Nadia Marcinkova", "third_party", "Epstein associate"),
            ("Les Wexner", "third_party", "CEO of L Brands, Epstein financial associate"),
            ("Alan Dershowitz", "third_party", "Attorney, named in civil litigation"),
            ("Virginia Giuffre", "plaintiff", "Key accuser and civil litigant"),
        ]
        for name, role, description in parties:
            conn.execute(
                text("""
                    INSERT INTO case_parties
                        (id, case_context_id, name, role, description, created_at, updated_at)
                    VALUES (:id, :cid, :name, :role, :desc, :now, :now)
                """),
                {
                    "id": uuid4(),
                    "cid": actual_ctx_id,
                    "name": name,
                    "role": role,
                    "desc": description,
                    "now": now,
                },
            )
        print(f"  Inserted {len(parties)} parties")

        # ---------------------------------------------------------------
        # 5. Case claims
        # ---------------------------------------------------------------
        claims = [
            (
                1,
                "Sex Trafficking",
                "Conspiracy to recruit, transport, and exploit minors for sexual abuse across multiple jurisdictions",
                json.dumps(["18 USC 1591", "trafficking in persons", "TVPA"]),
                json.dumps([]),
            ),
            (
                2,
                "Conspiracy",
                "Coordination among associates to facilitate trafficking operations and obstruct justice",
                json.dumps(["18 USC 371", "RICO", "obstruction"]),
                json.dumps([]),
            ),
            (
                3,
                "Financial Crimes",
                "Money laundering and financial structures used to fund trafficking operations and silence victims",
                json.dumps(["money laundering", "shell companies", "wire fraud"]),
                json.dumps([]),
            ),
        ]
        for claim_num, label, claim_text, elements, pages in claims:
            conn.execute(
                text("""
                    INSERT INTO case_claims
                        (id, case_context_id, claim_number, claim_label, claim_text,
                         legal_elements, source_pages, created_at, updated_at)
                    VALUES (:id, :cid, :num, :label, :text, :elements::json, :pages::json, :now, :now)
                """),
                {
                    "id": uuid4(),
                    "cid": actual_ctx_id,
                    "num": claim_num,
                    "label": label,
                    "text": claim_text,
                    "elements": elements,
                    "pages": pages,
                    "now": now,
                },
            )
        print(f"  Inserted {len(claims)} claims")

        # ---------------------------------------------------------------
        # 6. Defined terms
        # ---------------------------------------------------------------
        terms = [
            (
                "NPA",
                "Non-Prosecution Agreement between Jeffrey Epstein and the U.S. Attorney's Office for the Southern District of Florida (2007)",
            ),
            ("SDFL", "Southern District of Florida, federal judicial district where the NPA was negotiated"),
            ("SDNY", "Southern District of New York, federal judicial district where 2019 indictment was filed"),
            ("MCC", "Metropolitan Correctional Center, New York — federal detention facility"),
            ("MC2", "MC2 Model Management, modeling agency founded by Jean-Luc Brunel"),
            ("Palm Beach PD", "Palm Beach Police Department, initiated original 2005 investigation"),
        ]
        for term, definition in terms:
            conn.execute(
                text("""
                    INSERT INTO case_defined_terms
                        (id, case_context_id, term, definition, created_at, updated_at)
                    VALUES (:id, :cid, :term, :def, :now, :now)
                """),
                {
                    "id": uuid4(),
                    "cid": actual_ctx_id,
                    "term": term,
                    "def": definition,
                    "now": now,
                },
            )
        print(f"  Inserted {len(terms)} defined terms")

        # ---------------------------------------------------------------
        # 7. Dataset record
        # ---------------------------------------------------------------
        conn.execute(
            text("""
                INSERT INTO datasets
                    (id, matter_id, name, description, created_by, created_at, updated_at)
                VALUES (:id, :mid, :name, :desc, :created_by, :now, :now)
                ON CONFLICT DO NOTHING
            """),
            {
                "id": uuid4(),
                "mid": _MATTER_ID,
                "name": "House Oversight Nov 2025",
                "desc": "25,000+ pages released by the House Oversight Committee, November 2025. Pre-OCR'd via Tesseract.",
                "created_by": admin_rows[0].id if admin_rows else uuid4(),
                "now": now,
            },
        )
        print("  Created dataset: House Oversight Nov 2025")

        conn.commit()

    print(f"\n  Seed complete! Matter ID: {_MATTER_ID}")


if __name__ == "__main__":
    main()
