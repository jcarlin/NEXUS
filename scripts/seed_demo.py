"""Seed all NEXUS data stores with demo data so every frontend page has content.

Phases:
  0. Prerequisites — check env vars, API health
  1. Users — create 4 demo users via direct SQL
  2. Upload documents — ingest 14 test docs via API
  3. Wait for ingestion — poll until all jobs complete or timeout
  4. Post-ingestion — hot docs, comms, datasets, case context, eval data, chat
  5. Summary — print credentials and counts

Usage:
    python scripts/seed_demo.py

Idempotent: safe to run multiple times (uses ON CONFLICT / upserts).
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: python-dotenv is required. Install it with: pip install python-dotenv")
    sys.exit(1)

import httpx

from app.auth.service import AuthService
from app.config import Settings

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_API_BASE = "http://localhost:8000/api/v1"
_DEFAULT_MATTER_ID = "00000000-0000-0000-0000-000000000001"
_DEFAULT_MATTER_NAME = "Acme-Pinnacle Merger Investigation"
_DEFAULT_PASSWORD = "password123"
_TEST_DOCS_DIR = Path(__file__).resolve().parent / "generate_test_docs" / "output"
_INGEST_TIMEOUT_SECONDS = 600  # 10 minutes

USERS = [
    {"email": "admin@example.com", "role": "admin", "full_name": "System Administrator"},
    {"email": "attorney@nexus.dev", "role": "attorney", "full_name": "Demo Attorney"},
    {"email": "paralegal@nexus.dev", "role": "paralegal", "full_name": "Demo Paralegal"},
    {"email": "reviewer@nexus.dev", "role": "reviewer", "full_name": "Demo Reviewer"},
]

HOT_DOCS = [
    {"filename": "memo_acme_merger.txt", "score": 0.85},
    {"filename": "email_kim_to_park.eml", "score": 0.78},
    {"filename": "letter_reeves_board.txt", "score": 0.72},
    {"filename": "memo_environmental_assessment.txt", "score": 0.75},
]

COMM_PAIRS = [
    {
        "sender_name": "Sarah Chen",
        "sender_email": "sarah.chen@lawfirm.com",
        "recipient_name": "Michael Torres",
        "recipient_email": "michael.torres@lawfirm.com",
        "relationship_type": "to",
        "message_count": 2,
        "earliest": "2025-01-20",
        "latest": "2025-02-10",
    },
    {
        "sender_name": "Robert Kim",
        "sender_email": "robert.kim@wilsondrake.com",
        "recipient_name": "Lisa Park",
        "recipient_email": "lisa.park@pinnacle.com",
        "relationship_type": "to",
        "message_count": 1,
        "earliest": "2025-01-25",
        "latest": "2025-01-25",
    },
    {
        "sender_name": "Robert Kim",
        "sender_email": "robert.kim@wilsondrake.com",
        "recipient_name": "Sarah Chen",
        "recipient_email": "sarah.chen@lawfirm.com",
        "relationship_type": "cc",
        "message_count": 1,
        "earliest": "2025-01-25",
        "latest": "2025-01-25",
    },
    {
        "sender_name": "Lisa Park",
        "sender_email": "lisa.park@pinnacle.com",
        "recipient_name": "John Reeves",
        "recipient_email": "john.reeves@acme.com",
        "relationship_type": "to",
        "message_count": 1,
        "earliest": "2025-02-05",
        "latest": "2025-02-05",
    },
    {
        "sender_name": "Michael Torres",
        "sender_email": "michael.torres@lawfirm.com",
        "recipient_name": "Litigation Team",
        "recipient_email": "team@lawfirm.com",
        "relationship_type": "to",
        "message_count": 1,
        "earliest": "2025-02-10",
        "latest": "2025-02-10",
    },
    {
        "sender_name": "Michael Torres",
        "sender_email": "michael.torres@lawfirm.com",
        "recipient_name": "Sarah Chen",
        "recipient_email": "sarah.chen@lawfirm.com",
        "relationship_type": "cc",
        "message_count": 1,
        "earliest": "2025-02-10",
        "latest": "2025-02-10",
    },
    {
        "sender_name": "Sarah Chen",
        "sender_email": "sarah.chen@lawfirm.com",
        "recipient_name": "Robert Kim",
        "recipient_email": "robert.kim@wilsondrake.com",
        "relationship_type": "to",
        "message_count": 1,
        "earliest": "2025-02-14",
        "latest": "2025-02-14",
    },
]

# ---------------------------------------------------------------------------
# Terminal colours (only when interactive)
# ---------------------------------------------------------------------------

_USE_COLOR = sys.stdout.isatty()


def _green(msg: str) -> str:
    return f"\033[92m{msg}\033[0m" if _USE_COLOR else msg


def _yellow(msg: str) -> str:
    return f"\033[93m{msg}\033[0m" if _USE_COLOR else msg


def _red(msg: str) -> str:
    return f"\033[91m{msg}\033[0m" if _USE_COLOR else msg


def _bold(msg: str) -> str:
    return f"\033[1m{msg}\033[0m" if _USE_COLOR else msg


# ---------------------------------------------------------------------------
# Phase 0: Prerequisites
# ---------------------------------------------------------------------------


def phase0_prerequisites() -> Settings:
    """Load .env, check API keys, verify API health. Returns Settings."""
    print(f"\n{_bold('=== Phase 0: Prerequisites ===')}")

    load_dotenv()

    missing = []
    if not os.environ.get("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY")
    if missing:
        print(_yellow(f"  WARNING: Missing env vars: {', '.join(missing)} (ingestion/query may fail)"))
    else:
        print(_green("  API keys present"))

    # Health check
    try:
        resp = httpx.get(f"{_API_BASE}/health", timeout=10)
        resp.raise_for_status()
        print(_green(f"  API healthy at {_API_BASE}"))
    except (httpx.ConnectError, httpx.HTTPStatusError, httpx.TimeoutException) as exc:
        print(_red(f"  ERROR: API not reachable at {_API_BASE}: {exc}"))
        print(_red("  Start the API with: uvicorn app.main:app --reload --port 8000"))
        sys.exit(1)

    settings = Settings()
    print(_green("  Settings loaded"))
    return settings


# ---------------------------------------------------------------------------
# Phase 1: Users (direct SQL)
# ---------------------------------------------------------------------------


def phase1_users(settings: Settings) -> None:
    """Create demo users and link them to the default matter."""
    print(f"\n{_bold('=== Phase 1: Creating Users ===')}")

    engine = create_engine(settings.postgres_url_sync, pool_pre_ping=True)
    password_hash = AuthService.hash_password(_DEFAULT_PASSWORD)
    now = datetime.now(UTC)

    with engine.connect() as conn:
        # Ensure default matter exists
        conn.execute(
            text("""
                INSERT INTO case_matters (id, name, description, created_at, updated_at)
                VALUES (:id, :name, :desc, :now, :now)
                ON CONFLICT (id) DO UPDATE SET name = :name, updated_at = :now
            """),
            {
                "id": _DEFAULT_MATTER_ID,
                "name": _DEFAULT_MATTER_NAME,
                "desc": "Demo matter for the Acme Corp / Pinnacle Industries merger investigation",
                "now": now,
            },
        )
        print(f"  Matter: {_DEFAULT_MATTER_NAME}")

        for user in USERS:
            email, role, full_name = user["email"], user["role"], user["full_name"]
            user_id = uuid4()
            conn.execute(
                text("""
                    INSERT INTO users (id, email, password_hash, full_name, role, is_active, created_at, updated_at)
                    VALUES (:id, :email, :ph, :fn, :role, true, :now, :now)
                    ON CONFLICT (email) DO UPDATE
                        SET password_hash = :ph, role = :role, full_name = :fn, updated_at = :now
                    RETURNING id
                """),
                {
                    "id": user_id,
                    "email": email,
                    "ph": password_hash,
                    "fn": full_name,
                    "role": role,
                    "now": now,
                },
            )
            row = conn.execute(
                text("SELECT id FROM users WHERE email = :email"),
                {"email": email},
            ).first()
            actual_id = row.id if row else user_id

            conn.execute(
                text("""
                    INSERT INTO user_case_matters (user_id, matter_id)
                    VALUES (:uid, :mid)
                    ON CONFLICT DO NOTHING
                """),
                {"uid": actual_id, "mid": _DEFAULT_MATTER_ID},
            )
            print(f"  User: {email} ({role})")

        conn.commit()
    print(_green("  All users created and linked to matter"))


# ---------------------------------------------------------------------------
# Phase 2: Upload documents via API
# ---------------------------------------------------------------------------


def _login(client: httpx.Client) -> str:
    """Login as admin and return the access token."""
    resp = client.post(
        f"{_API_BASE}/auth/login",
        json={"email": "admin@example.com", "password": _DEFAULT_PASSWORD},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def phase2_upload_documents(client: httpx.Client, token: str) -> list[str]:
    """Upload all test documents and return list of job_ids."""
    print(f"\n{_bold('=== Phase 2: Uploading Documents ===')}")

    if not _TEST_DOCS_DIR.exists():
        print(_red(f"  ERROR: Test docs directory not found: {_TEST_DOCS_DIR}"))
        print(_red("  Run: python scripts/generate_test_docs/generate.py"))
        return []

    files = sorted(_TEST_DOCS_DIR.iterdir())
    if not files:
        print(_red("  ERROR: No files found in test docs directory"))
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Matter-ID": _DEFAULT_MATTER_ID,
    }

    job_ids: list[str] = []
    for i, fpath in enumerate(files, 1):
        if fpath.is_dir():
            continue
        try:
            with open(fpath, "rb") as f:
                resp = client.post(
                    f"{_API_BASE}/ingest",
                    headers=headers,
                    files={"file": (fpath.name, f)},
                    timeout=30,
                )
            if resp.status_code == 200:
                job_id = resp.json()["job_id"]
                job_ids.append(job_id)
                print(f"  [{i}/{len(files)}] {fpath.name} -> job {job_id[:8]}...")
            else:
                print(_yellow(f"  [{i}/{len(files)}] {fpath.name} -> HTTP {resp.status_code}: {resp.text[:100]}"))
        except Exception as exc:
            print(_red(f"  [{i}/{len(files)}] {fpath.name} -> ERROR: {exc}"))

    print(_green(f"  Submitted {len(job_ids)} / {len(files)} files"))
    return job_ids


# ---------------------------------------------------------------------------
# Phase 3: Wait for ingestion
# ---------------------------------------------------------------------------


def phase3_wait_for_ingestion(client: httpx.Client, token: str, job_ids: list[str]) -> dict[str, str]:
    """Poll jobs until all complete or timeout. Returns {job_id: status}."""
    print(f"\n{_bold('=== Phase 3: Waiting for Ingestion ===')}")

    if not job_ids:
        print(_yellow("  No jobs to wait for"))
        return {}

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Matter-ID": _DEFAULT_MATTER_ID,
    }

    terminal_statuses = {"complete", "failed", "completed"}
    results: dict[str, str] = {}
    start = time.time()

    while time.time() - start < _INGEST_TIMEOUT_SECONDS:
        pending = 0
        for job_id in job_ids:
            if job_id in results:
                continue
            try:
                resp = client.get(f"{_API_BASE}/jobs/{job_id}", headers=headers, timeout=10)
                if resp.status_code == 200:
                    status = resp.json()["status"]
                    if status in terminal_statuses:
                        results[job_id] = status
                    else:
                        pending += 1
                else:
                    pending += 1
            except Exception:
                pending += 1

        done = len(results)
        total = len(job_ids)
        failed = sum(1 for s in results.values() if s == "failed")
        elapsed = int(time.time() - start)

        print(f"\r  Ingesting... {done}/{total} complete, {failed} failed ({elapsed}s elapsed)", end="", flush=True)

        if done == total:
            break
        time.sleep(3)

    print()  # newline after \r progress

    # Check for any remaining unfinished
    for job_id in job_ids:
        if job_id not in results:
            results[job_id] = "timeout"

    completed = sum(1 for s in results.values() if s in {"complete", "completed"})
    failed = sum(1 for s in results.values() if s == "failed")
    timed_out = sum(1 for s in results.values() if s == "timeout")

    if failed > 0:
        print(_yellow(f"  {failed} job(s) failed"))
    if timed_out > 0:
        print(_yellow(f"  {timed_out} job(s) timed out"))
    print(_green(f"  {completed} / {len(job_ids)} documents ingested successfully"))

    return results


# ---------------------------------------------------------------------------
# Phase 4: Post-ingestion seeding
# ---------------------------------------------------------------------------


def phase4a_hot_doc_scores(settings: Settings) -> None:
    """Set hot-doc scores on key documents."""
    print(f"\n  {_bold('--- 4a: Hot Doc Scores ---')}")

    engine = create_engine(settings.postgres_url_sync, pool_pre_ping=True)

    with engine.connect() as conn:
        for doc in HOT_DOCS:
            filename, score = doc["filename"], doc["score"]
            # Try hot_doc_score column first, fall back to metadata_ JSONB
            try:
                result = conn.execute(
                    text("""
                        UPDATE documents SET hot_doc_score = :score, updated_at = :now
                        WHERE filename = :fn AND matter_id = :mid
                    """),
                    {
                        "score": score,
                        "fn": filename,
                        "mid": _DEFAULT_MATTER_ID,
                        "now": datetime.now(UTC),
                    },
                )
                if result.rowcount > 0:
                    print(f"    {filename} -> score={score} (column)")
                else:
                    print(_yellow(f"    {filename} -> document not found (skipped)"))
            except Exception:
                # Column doesn't exist; use metadata_ JSONB
                try:
                    result = conn.execute(
                        text("""
                            UPDATE documents
                            SET metadata_ = jsonb_set(
                                COALESCE(metadata_, '{}'),
                                '{hot_doc_score}',
                                CAST(:score_json AS jsonb)
                            ),
                            updated_at = :now
                            WHERE filename = :fn AND matter_id = :mid
                        """),
                        {
                            "score_json": json.dumps(score),
                            "fn": filename,
                            "mid": _DEFAULT_MATTER_ID,
                            "now": datetime.now(UTC),
                        },
                    )
                    if result.rowcount > 0:
                        print(f"    {filename} -> score={score} (metadata_)")
                    else:
                        print(_yellow(f"    {filename} -> document not found (skipped)"))
                except Exception as exc2:
                    print(_yellow(f"    {filename} -> ERROR: {exc2}"))

        conn.commit()


def phase4b_communication_pairs(settings: Settings) -> None:
    """Seed communication pair records."""
    print(f"\n  {_bold('--- 4b: Communication Pairs ---')}")

    engine = create_engine(settings.postgres_url_sync, pool_pre_ping=True)
    now = datetime.now(UTC)

    with engine.connect() as conn:
        for pair in COMM_PAIRS:
            sender_name = pair["sender_name"]
            sender_email = pair["sender_email"]
            recip_name = pair["recipient_name"]
            recip_email = pair["recipient_email"]
            rel_type = pair["relationship_type"]
            count = pair["message_count"]
            earliest = pair["earliest"]
            latest = pair["latest"]
            conn.execute(
                text("""
                    INSERT INTO communication_pairs
                        (id, matter_id, sender_name, sender_email, recipient_name, recipient_email,
                         relationship_type, message_count, earliest, latest, created_at, updated_at)
                    VALUES
                        (:id, :mid, :sn, :se, :rn, :re, :rt, :mc, :earliest, :latest, :now, :now)
                    ON CONFLICT (matter_id, sender_email, recipient_email, relationship_type)
                    DO UPDATE SET message_count = :mc, earliest = :earliest, latest = :latest, updated_at = :now
                """),
                {
                    "id": uuid4(),
                    "mid": _DEFAULT_MATTER_ID,
                    "sn": sender_name,
                    "se": sender_email,
                    "rn": recip_name,
                    "re": recip_email,
                    "rt": rel_type,
                    "mc": count,
                    "earliest": datetime.fromisoformat(earliest),
                    "latest": datetime.fromisoformat(latest),
                    "now": now,
                },
            )
            print(f"    {sender_name} -> {recip_name} ({rel_type}, {count} msgs)")

        conn.commit()
    print(_green("    Communication pairs seeded"))


def phase4c_datasets(client: httpx.Client, token: str, settings: Settings) -> None:
    """Create datasets and assign documents."""
    print(f"\n  {_bold('--- 4c: Datasets ---')}")

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Matter-ID": _DEFAULT_MATTER_ID,
        "Content-Type": "application/json",
    }

    # Fetch existing datasets to avoid duplicates on re-run
    existing_datasets: dict[str, str] = {}  # name -> id
    tree_resp = client.get(f"{_API_BASE}/datasets/tree", headers=headers, timeout=10)
    if tree_resp.status_code == 200:

        def _collect(nodes: list[dict], parent: str | None = None) -> None:
            for n in nodes:
                key = f"{parent}/{n['name']}" if parent else n["name"]
                existing_datasets[key] = n["id"]
                _collect(n.get("children", []), parent=n["name"])

        _collect(tree_resp.json().get("roots", []))

    # Create root datasets
    def _create_dataset(name: str, description: str, parent_id: str | None = None) -> str | None:
        # Check if dataset already exists (use parent-scoped key for children)
        lookup_key = name
        if parent_id:
            # Find parent name from existing_datasets values
            for k, v in existing_datasets.items():
                if v == parent_id:
                    parent_name = k.split("/")[-1] if "/" in k else k
                    lookup_key = f"{parent_name}/{name}"
                    break
        if lookup_key in existing_datasets:
            ds_id = existing_datasets[lookup_key]
            print(f"    Dataset '{name}' already exists ({ds_id[:8]}...), skipping")
            return ds_id

        payload: dict = {"name": name, "description": description}
        if parent_id:
            payload["parent_id"] = parent_id
        resp = client.post(f"{_API_BASE}/datasets", headers=headers, json=payload, timeout=10)
        if resp.status_code == 201:
            ds_id = resp.json()["id"]
            print(f"    Created dataset: {name} ({ds_id[:8]}...)")
            existing_datasets[lookup_key] = ds_id
            return ds_id
        else:
            print(_yellow(f"    Failed to create dataset '{name}': {resp.status_code} {resp.text[:100]}"))
            return None

    due_diligence_id = _create_dataset("Due Diligence", "Core due diligence documents")
    correspondence_id = _create_dataset("Correspondence", "Email correspondence and letters")

    environmental_id = None
    sec_inquiry_id = None
    if due_diligence_id:
        environmental_id = _create_dataset("Environmental", "Environmental assessment documents", due_diligence_id)
        sec_inquiry_id = _create_dataset("SEC Inquiry", "SEC inquiry related documents", due_diligence_id)

    # Query document IDs from DB
    engine = create_engine(settings.postgres_url_sync, pool_pre_ping=True)

    # Mapping: filename -> document_id
    doc_ids: dict[str, str] = {}
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, filename FROM documents WHERE matter_id = :mid"),
            {"mid": _DEFAULT_MATTER_ID},
        ).fetchall()
        for row in rows:
            doc_ids[row.filename] = str(row.id)

    if not doc_ids:
        print(_yellow("    No documents found — skipping dataset assignment"))
        return

    def _assign(dataset_id: str | None, filenames: list[str], label: str) -> None:
        if not dataset_id:
            print(_yellow(f"    Skipping {label} assignment (no dataset ID)"))
            return
        ids = [doc_ids[fn] for fn in filenames if fn in doc_ids]
        if not ids:
            print(_yellow(f"    No matching docs for {label}"))
            return
        resp = client.post(
            f"{_API_BASE}/datasets/{dataset_id}/documents",
            headers=headers,
            json={"document_ids": ids},
            timeout=10,
        )
        if resp.status_code == 200:
            print(f"    Assigned {resp.json().get('assigned', len(ids))} docs to {label}")
        else:
            print(_yellow(f"    Assignment to {label} failed: {resp.status_code} {resp.text[:100]}"))

    _assign(environmental_id, ["memo_environmental_assessment.txt"], "Environmental")
    _assign(sec_inquiry_id, ["email_kim_to_park.eml", "memo_financial_analysis.txt"], "SEC Inquiry")

    eml_files = [fn for fn in doc_ids if fn.endswith(".eml")]
    _assign(correspondence_id, eml_files, "Correspondence")

    _assign(
        due_diligence_id,
        ["memo_acme_merger.txt", "contract_excerpt_merger.txt", "letter_reeves_board.txt"],
        "Due Diligence",
    )

    print(_green("    Datasets seeded"))


def phase4d_case_context(settings: Settings) -> None:
    """Seed case context, claims, parties, and defined terms."""
    print(f"\n  {_bold('--- 4d: Case Context ---')}")

    engine = create_engine(settings.postgres_url_sync, pool_pre_ping=True)
    now = datetime.now(UTC)
    context_id = uuid4()

    timeline = json.dumps(
        [
            {"date": "2025-01-15", "event_text": "Merger publicly announced", "source_page": None},
            {"date": "2025-01-25", "event_text": "Board of Directors authorizes due diligence", "source_page": None},
            {"date": "2025-02-05", "event_text": "Privilege review protocol established", "source_page": None},
            {"date": "2025-02-14", "event_text": "Phase II environmental report released", "source_page": None},
            {"date": "2025-02-15", "event_text": "SEC inquiry meeting at Pinnacle Denver office", "source_page": None},
            {"date": "2025-03-30", "event_text": "Due diligence completion deadline", "source_page": None},
        ]
    )

    with engine.connect() as conn:
        # Find an anchor document
        row = conn.execute(
            text("SELECT id FROM documents WHERE matter_id = :mid LIMIT 1"),
            {"mid": _DEFAULT_MATTER_ID},
        ).first()
        anchor_doc_id = str(row.id) if row else str(uuid4())

        # Upsert case_contexts (unique on matter_id)
        conn.execute(
            text("""
                INSERT INTO case_contexts
                    (id, matter_id, anchor_document_id, status, timeline, created_at, updated_at)
                VALUES
                    (:id, :mid, :anchor, 'confirmed', :timeline::json, :now, :now)
                ON CONFLICT (matter_id) DO UPDATE
                    SET anchor_document_id = :anchor,
                        status = 'confirmed',
                        timeline = :timeline::json,
                        updated_at = :now
                RETURNING id
            """),
            {
                "id": context_id,
                "mid": _DEFAULT_MATTER_ID,
                "anchor": anchor_doc_id,
                "timeline": timeline,
                "now": now,
            },
        )
        # Retrieve the actual context_id (may differ if ON CONFLICT fires)
        ctx_row = conn.execute(
            text("SELECT id FROM case_contexts WHERE matter_id = :mid"),
            {"mid": _DEFAULT_MATTER_ID},
        ).first()
        actual_ctx_id = ctx_row.id if ctx_row else context_id
        print(f"    Case context: {str(actual_ctx_id)[:8]}...")

        # Delete existing child rows for idempotency
        conn.execute(text("DELETE FROM case_claims WHERE case_context_id = :cid"), {"cid": actual_ctx_id})
        conn.execute(text("DELETE FROM case_parties WHERE case_context_id = :cid"), {"cid": actual_ctx_id})
        conn.execute(text("DELETE FROM case_defined_terms WHERE case_context_id = :cid"), {"cid": actual_ctx_id})

        # Claims
        claims = [
            (
                1,
                "Environmental Liability",
                "Potential TCE contamination at Pinnacle's Denver Plant requiring remediation estimated at $3.2M-$7.8M",
                json.dumps(["CERCLA liability", "Phase II ESA findings", "Remediation cost allocation"]),
                json.dumps([3, 5, 8]),
            ),
            (
                2,
                "Securities Fraud Risk",
                "SEC voluntary inquiry into Pinnacle's revenue recognition practices for Meridian Technologies and GlobalSync Logistics contracts",
                json.dumps(["Revenue recognition", "Material misstatement", "Voluntary disclosure"]),
                json.dumps([2, 6]),
            ),
            (
                3,
                "Merger Valuation Dispute",
                "Risk that environmental and SEC issues materially affect the $420M transaction valuation and 1.35 exchange ratio",
                json.dumps(["Material adverse change", "Purchase price adjustment", "Indemnification"]),
                json.dumps([1, 4, 7]),
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
        print(f"    Inserted {len(claims)} claims")

        # Parties
        parties = [
            ("John Reeves", "defendant", "Chief Executive Officer, Acme Corp"),
            ("Lisa Park", "defendant", "Chief Financial Officer, Pinnacle Industries"),
            ("Robert Kim", "third_party", "Outside counsel at Wilson & Drake LLP"),
            ("Sarah Chen", "third_party", "Senior Associate, outside counsel to Acme Corp"),
            (
                "Securities and Exchange Commission",
                "plaintiff",
                "Federal securities regulator conducting voluntary inquiry",
            ),
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
        print(f"    Inserted {len(parties)} parties")

        # Defined terms
        terms = [
            ("Acme", "Acme Corp, a Delaware corporation, the acquiring party in the proposed merger"),
            ("Pinnacle", "Pinnacle Industries, Inc., a Colorado corporation, the target company"),
            (
                "Denver Plant",
                "Manufacturing facility at 4500 Industrial Blvd, Denver, CO 80216, owned by Pinnacle Industries",
            ),
            ("Closing Date", "The third business day following satisfaction of merger conditions, target Q3 2025"),
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
        print(f"    Inserted {len(terms)} defined terms")

        conn.commit()
    print(_green("    Case context seeded"))


def phase4e_evaluation_data(settings: Settings) -> None:
    """Seed evaluation dataset items and a completed evaluation run."""
    print(f"\n  {_bold('--- 4e: Evaluation Data ---')}")

    engine = create_engine(settings.postgres_url_sync, pool_pre_ping=True)
    now = datetime.now(UTC)

    items = [
        (
            "What are the main environmental risks in the Acme-Pinnacle merger?",
            "TCE contamination at Pinnacle's Denver Plant (4500 Industrial Blvd, Denver, CO 80216) poses significant environmental liability. Phase II ESA findings indicate trichloroethylene contamination requiring remediation estimated at $3.2M to $7.8M.",
            ["environmental", "merger", "risk"],
        ),
        (
            "Who is leading the due diligence for Acme Corp?",
            "Michael Torres (Partner) and Sarah Chen (Senior Associate) at the outside counsel firm are leading due diligence for Acme Corp. Robert Kim at Wilson & Drake LLP represents Pinnacle Industries.",
            ["people", "due-diligence"],
        ),
        (
            "What is the estimated remediation cost range?",
            "$3.2M to $7.8M for TCE contamination remediation at the Denver Plant, based on Phase II environmental assessment findings.",
            ["environmental", "costs"],
        ),
        (
            "What contracts is the SEC investigating?",
            "Meridian Technologies ($14.2M, FY 2023) and GlobalSync Logistics ($9.8M, FY 2022) — the SEC voluntary inquiry focuses on Pinnacle's revenue recognition practices for these two contracts.",
            ["SEC", "contracts", "investigation"],
        ),
        (
            "What is the proposed environmental cap in the merger agreement?",
            "$5M, with costs between $3.5M reserve and $5M cap shared 60/40 (Pinnacle/Acme). Costs below the $3.5M reserve are Pinnacle's sole responsibility.",
            ["environmental", "merger", "financial"],
        ),
    ]

    metrics = json.dumps(
        {
            "accuracy": 0.84,
            "faithfulness": 0.82,
            "relevance": 0.79,
            "citation_precision": 0.85,
            "citation_recall": 0.77,
            "latency_p50_ms": 2340,
            "latency_p95_ms": 5120,
        }
    )

    with engine.connect() as conn:
        for question, answer, tags in items:
            conn.execute(
                text("""
                    INSERT INTO evaluation_dataset_items
                        (id, dataset_type, question, expected_answer, tags, metadata_, created_at)
                    VALUES
                        (:id, 'ground_truth', :q, :a, :tags::json, :meta::json, :now)
                    ON CONFLICT (id) DO NOTHING
                """),
                {
                    "id": uuid4(),
                    "q": question,
                    "a": answer,
                    "tags": json.dumps(tags),
                    "meta": json.dumps({}),
                    "now": now,
                },
            )
        print(f"    Inserted {len(items)} evaluation dataset items")

        # Evaluation run
        conn.execute(
            text("""
                INSERT INTO evaluation_runs
                    (id, mode, status, metrics, config_overrides, total_items,
                     processed_items, created_at, completed_at)
                VALUES
                    (:id, 'full', 'completed', :metrics::json, :overrides::json,
                     :total, :processed, :created, :completed)
            """),
            {
                "id": uuid4(),
                "metrics": metrics,
                "overrides": json.dumps({}),
                "total": 5,
                "processed": 5,
                "created": now - timedelta(minutes=15),
                "completed": now - timedelta(minutes=10),
            },
        )
        print("    Inserted 1 completed evaluation run")

        conn.commit()
    print(_green("    Evaluation data seeded"))


def phase4f_chat_thread(client: httpx.Client, token: str) -> str | None:
    """Create a demo chat thread via the query API. Returns thread_id or None."""
    print(f"\n  {_bold('--- 4f: Chat Thread ---')}")

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Matter-ID": _DEFAULT_MATTER_ID,
        "Content-Type": "application/json",
    }

    thread_id = None
    try:
        # First query
        resp = client.post(
            f"{_API_BASE}/query",
            headers=headers,
            json={"query": "What are the main risks in the Acme-Pinnacle merger?"},
            timeout=120,
        )
        if resp.status_code == 200:
            thread_id = resp.json().get("thread_id")
            print(f"    Query 1 complete (thread={str(thread_id)[:8]}...)")
        else:
            print(_yellow(f"    Query 1 failed: {resp.status_code} {resp.text[:100]}"))
            return None

        # Follow-up query
        resp = client.post(
            f"{_API_BASE}/query",
            headers=headers,
            json={
                "query": "Tell me about the environmental issues at the Denver plant",
                "thread_id": thread_id,
            },
            timeout=120,
        )
        if resp.status_code == 200:
            print("    Query 2 complete (follow-up)")
        else:
            print(_yellow(f"    Query 2 failed: {resp.status_code} {resp.text[:100]}"))

    except Exception as exc:
        print(_yellow(f"    Chat seeding failed (LLM may not be available): {exc}"))

    if thread_id:
        print(_green(f"    Chat thread seeded: {thread_id}"))
    return thread_id


# ---------------------------------------------------------------------------
# Phase 5: Summary
# ---------------------------------------------------------------------------


def phase5_summary(settings: Settings, thread_id: str | None) -> None:
    """Print final summary with counts and credentials."""
    print(f"\n{_bold('=== Phase 5: Summary ===')}")

    engine = create_engine(settings.postgres_url_sync, pool_pre_ping=True)

    with engine.connect() as conn:
        doc_count = (
            conn.execute(
                text("SELECT COUNT(*) FROM documents WHERE matter_id = :mid"),
                {"mid": _DEFAULT_MATTER_ID},
            ).scalar()
            or 0
        )

        entity_count = 0
        try:
            entity_count = (
                conn.execute(
                    text("SELECT COUNT(*) FROM entities WHERE matter_id = :mid"),
                    {"mid": _DEFAULT_MATTER_ID},
                ).scalar()
                or 0
            )
        except Exception:
            pass  # entities table may not exist yet

        user_count = conn.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0

        thread_count = 0
        try:
            thread_count = (
                conn.execute(
                    text("SELECT COUNT(DISTINCT thread_id) FROM chat_messages WHERE matter_id = :mid"),
                    {"mid": _DEFAULT_MATTER_ID},
                ).scalar()
                or 0
            )
        except Exception:
            # Try LangGraph checkpointer table
            try:
                thread_count = (
                    conn.execute(
                        text("SELECT COUNT(DISTINCT thread_id) FROM checkpoints"),
                    ).scalar()
                    or 0
                )
            except Exception:
                thread_count = 1 if thread_id else 0

    print(f"  Documents:  {doc_count}")
    print(f"  Entities:   {entity_count}")
    print(f"  Users:      {user_count}")
    print(f"  Threads:    {thread_count}")
    print()
    print(_bold("  Credentials:"))
    print(f"    admin@example.com      / {_DEFAULT_PASSWORD}  (admin)")
    print(f"    attorney@nexus.dev     / {_DEFAULT_PASSWORD}  (attorney)")
    print(f"    paralegal@nexus.dev    / {_DEFAULT_PASSWORD}  (paralegal)")
    print(f"    reviewer@nexus.dev     / {_DEFAULT_PASSWORD}  (reviewer)")
    print()
    print(f"  API:       {_API_BASE}")
    print(f"  Matter ID: {_DEFAULT_MATTER_ID}")
    print()
    print(_green("  Seed complete!"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    settings = phase0_prerequisites()
    phase1_users(settings)

    client = httpx.Client()
    try:
        token = _login(client)
        print(_green("  Logged in as admin@example.com"))

        job_ids = phase2_upload_documents(client, token)
        phase3_wait_for_ingestion(client, token, job_ids)

        print(f"\n{_bold('=== Phase 4: Post-Ingestion Seeding ===')}")
        phase4a_hot_doc_scores(settings)
        phase4b_communication_pairs(settings)
        phase4c_datasets(client, token, settings)
        phase4d_case_context(settings)
        phase4e_evaluation_data(settings)
        thread_id = phase4f_chat_thread(client, token)

        phase5_summary(settings, thread_id)
    finally:
        client.close()


if __name__ == "__main__":
    main()
