"""E2E test fixtures — real Docker services, real data flows.

Fixture hierarchy:
  Session-scoped: env vars, service checks, DB/Qdrant/Neo4j/MinIO/Redis setup, Celery eager
  Module-scoped:  FastAPI app, httpx client, auth tokens, ingested document
  Function-scoped: sample file objects

All fixtures skip gracefully if Docker services are unreachable.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

E2E_DB_NAME = "nexus_e2e_test"
E2E_BUCKET = "e2e-test"
E2E_REDIS_DB = 14
E2E_MATTER_ID = "00000000-0000-0000-0000-000000000001"  # Seed data from migration 002
E2E_ADMIN_EMAIL = "admin@example.com"
E2E_ADMIN_PASSWORD = "password123"

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Embedding config for E2E: local model, 384d
E2E_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
E2E_EMBEDDING_DIM = 384


# ---------------------------------------------------------------------------
# Session-scoped: environment variable isolation
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def e2e_env_vars():
    """Set environment variables so that Settings() instances created by
    Celery tasks and other code paths read test-isolated config.

    This must run BEFORE any Settings() is instantiated.
    """
    overrides = {
        "POSTGRES_URL": f"postgresql+asyncpg://nexus:changeme@localhost:5432/{E2E_DB_NAME}",
        "POSTGRES_URL_SYNC": f"postgresql://nexus:changeme@localhost:5432/{E2E_DB_NAME}",
        "REDIS_URL": f"redis://localhost:6379/{E2E_REDIS_DB}",
        "QDRANT_URL": "http://localhost:6333",
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "changeme",
        "MINIO_ENDPOINT": "localhost:9000",
        "MINIO_ACCESS_KEY": "nexus-admin",
        "MINIO_SECRET_KEY": "changeme",
        "MINIO_BUCKET": E2E_BUCKET,
        "EMBEDDING_PROVIDER": "local",
        "LOCAL_EMBEDDING_MODEL": E2E_EMBEDDING_MODEL,
        "EMBEDDING_DIMENSIONS": str(E2E_EMBEDDING_DIM),
        "ENABLE_AGENTIC_PIPELINE": "false",
        "ENABLE_SPARSE_EMBEDDINGS": "false",
        "ENABLE_VISUAL_EMBEDDINGS": "false",
        "ENABLE_RERANKER": "false",
        "ENABLE_RELATIONSHIP_EXTRACTION": "false",
        "ENABLE_NEAR_DUPLICATE_DETECTION": "false",
        "ENABLE_COREFERENCE_RESOLUTION": "false",
        "ENABLE_AI_AUDIT_LOGGING": "false",
        "ENABLE_REDACTION": "false",
        "ENABLE_GRAPH_CENTRALITY": "false",
        "ENABLE_HOT_DOC_DETECTION": "false",
        "ENABLE_TOPIC_CLUSTERING": "false",
        "ENABLE_CITATION_VERIFICATION": "false",
        "JWT_SECRET_KEY": "e2e-test-secret-key-do-not-use-in-production",
        "ANTHROPIC_API_KEY": "fake-key",
        "OPENAI_API_KEY": "fake-key",
    }
    saved = {}
    for key, val in overrides.items():
        saved[key] = os.environ.get(key)
        os.environ[key] = val

    yield

    # Restore original env
    for key, original in saved.items():
        if original is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original


# ---------------------------------------------------------------------------
# Session-scoped: service connectivity checks
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def e2e_services_check(e2e_env_vars):
    """Ping all 5 services; skip the entire E2E suite if any is unreachable."""
    import socket

    services = {
        "postgres": ("localhost", 5432),
        "redis": ("localhost", 6379),
        "qdrant": ("localhost", 6333),
        "neo4j": ("localhost", 7687),
        "minio": ("localhost", 9000),
    }
    for name, (host, port) in services.items():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        try:
            sock.connect((host, port))
        except (ConnectionRefusedError, TimeoutError, OSError):
            pytest.skip(f"E2E service '{name}' not reachable at {host}:{port}")
        finally:
            sock.close()


# ---------------------------------------------------------------------------
# Session-scoped: PostgreSQL database setup
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def e2e_postgres_db(e2e_services_check):
    """Create the E2E test database, run Alembic migrations, tear down after."""
    from sqlalchemy import create_engine, text

    admin_url = "postgresql://nexus:changeme@localhost:5432/postgres"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")

    with admin_engine.connect() as conn:
        # Terminate existing connections to the test DB
        conn.execute(
            text(
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{E2E_DB_NAME}' AND pid <> pg_backend_pid()"
            )
        )
        conn.execute(text(f"DROP DATABASE IF EXISTS {E2E_DB_NAME}"))
        conn.execute(text(f"CREATE DATABASE {E2E_DB_NAME} OWNER nexus"))

    admin_engine.dispose()

    # Run Alembic migrations against the E2E database
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    alembic_cfg.set_main_option(
        "sqlalchemy.url",
        f"postgresql://nexus:changeme@localhost:5432/{E2E_DB_NAME}",
    )
    command.upgrade(alembic_cfg, "head")

    yield

    # Cleanup: drop the E2E database
    cleanup_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with cleanup_engine.connect() as conn:
        conn.execute(
            text(
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{E2E_DB_NAME}' AND pid <> pg_backend_pid()"
            )
        )
        conn.execute(text(f"DROP DATABASE IF EXISTS {E2E_DB_NAME}"))
    cleanup_engine.dispose()


# ---------------------------------------------------------------------------
# Session-scoped: Qdrant collection setup
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def e2e_qdrant(e2e_services_check):
    """Ensure Qdrant text collection exists with E2E dimensions (384d)."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams

    client = QdrantClient(url="http://localhost:6333")
    collection_name = "nexus_text"

    # Delete ALL existing collections (clean slate — prevents config mismatches
    # from leftover production collections with named/sparse vectors)
    for c in client.get_collections().collections:
        client.delete_collection(c.name)

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=E2E_EMBEDDING_DIM,
            distance=Distance.COSINE,
        ),
    )

    yield client

    # Cleanup
    for c in client.get_collections().collections:
        try:
            client.delete_collection(c.name)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Session-scoped: Neo4j schema setup
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def e2e_neo4j(e2e_services_check):
    """Ensure Neo4j schema, clear existing data."""

    from neo4j import AsyncGraphDatabase

    async def _setup():
        driver = AsyncGraphDatabase.driver(
            "bolt://localhost:7687",
            auth=("neo4j", "changeme"),
        )
        try:
            # Clear all data
            async with driver.session() as session:
                await session.run("MATCH (n) DETACH DELETE n")

            # Ensure schema
            from app.entities.schema import ensure_schema

            await ensure_schema(driver)
        finally:
            await driver.close()

    asyncio.run(_setup())

    yield

    # Cleanup: clear graph data
    async def _teardown():
        driver = AsyncGraphDatabase.driver(
            "bolt://localhost:7687",
            auth=("neo4j", "changeme"),
        )
        try:
            async with driver.session() as session:
                await session.run("MATCH (n) DETACH DELETE n")
        finally:
            await driver.close()

    asyncio.run(_teardown())


# ---------------------------------------------------------------------------
# Session-scoped: MinIO bucket setup
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def e2e_minio(e2e_services_check):
    """Ensure the E2E test bucket exists in MinIO."""
    import boto3
    from botocore.config import Config as BotoConfig
    from botocore.exceptions import ClientError

    client = boto3.client(
        "s3",
        endpoint_url="http://localhost:9000",
        aws_access_key_id="nexus-admin",
        aws_secret_access_key="changeme",
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )

    try:
        client.head_bucket(Bucket=E2E_BUCKET)
    except ClientError:
        client.create_bucket(Bucket=E2E_BUCKET)

    yield client

    # Cleanup: delete all objects then bucket
    try:
        resp = client.list_objects_v2(Bucket=E2E_BUCKET)
        for obj in resp.get("Contents", []):
            client.delete_object(Bucket=E2E_BUCKET, Key=obj["Key"])
        client.delete_bucket(Bucket=E2E_BUCKET)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Session-scoped: Redis flush
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def e2e_redis(e2e_services_check):
    """Flush the E2E Redis DB."""
    import redis

    r = redis.Redis(host="localhost", port=6379, db=E2E_REDIS_DB)
    r.flushdb()
    yield r
    r.flushdb()
    r.close()


# ---------------------------------------------------------------------------
# Session-scoped: Celery eager mode
# ---------------------------------------------------------------------------


_PENDING_TASKS: list[tuple[str, str]] = []
"""Accumulated (job_id, minio_path) pairs from patched ``.delay()`` calls."""


@pytest.fixture(scope="session")
def celery_eager(e2e_env_vars):
    """Patch ``process_document.delay()`` to be a no-op that records args.

    Celery eager mode cannot work inside FastAPI's async handler because
    the task calls ``asyncio.run()`` which conflicts with the running
    event loop.  Instead we capture the task args and run the task
    directly from the test fixture via ``run_pending_tasks()``.

    Celery eager mode IS still enabled so that subtasks dispatched from
    within ``process_document`` (e.g. ``resolve_entities.delay()``) run
    in-process without needing a real broker connection.
    """
    from workers.celery_app import celery_app

    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=False,
    )

    from app.ingestion.tasks import process_document

    _original_delay = process_document.delay

    def _capture_delay(*args, **kwargs):
        """Store the task args for later execution — don't run anything."""
        _PENDING_TASKS.append(args[:2])  # (job_id, minio_path)

    process_document.delay = _capture_delay  # type: ignore[assignment]

    yield

    process_document.delay = _original_delay  # type: ignore[assignment]
    celery_app.conf.update(
        task_always_eager=False,
        task_eager_propagates=False,
    )


def run_pending_tasks() -> None:
    """Execute captured ``process_document`` calls in a fresh thread.

    Each task gets its own event loop in a separate thread so that
    ``asyncio.run()`` inside the task doesn't conflict with FastAPI's loop.

    Uses ``task.apply()`` (not direct call) so that:
    1. The ``bind=True`` self parameter is handled correctly.
    2. Subtask ``.delay()`` calls respect ``task_always_eager=True``.
    """
    from concurrent.futures import ThreadPoolExecutor

    from app.ingestion.tasks import process_document

    if not _PENDING_TASKS:
        return

    tasks = list(_PENDING_TASKS)
    _PENDING_TASKS.clear()

    def _run_task(args: tuple) -> None:
        # Celery uses thread-local state for the current app — set it
        # so that subtask .delay() calls respect task_always_eager.
        from workers.celery_app import celery_app

        celery_app.set_current()
        celery_app.set_default()
        process_document.apply(args=list(args))

    with ThreadPoolExecutor(max_workers=1) as executor:
        for args in tasks:
            future = executor.submit(_run_task, args)
            future.result()  # Block until task completes


# ---------------------------------------------------------------------------
# Module-scoped: FastAPI app with real lifespan + overrides
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module")
async def e2e_app(
    e2e_postgres_db,
    e2e_qdrant,
    e2e_neo4j,
    e2e_minio,
    e2e_redis,
    celery_eager,
):
    """Create the FastAPI app with real infrastructure but FakeLLMClient."""
    # Clear all cached singletons from dependencies so they re-read env vars
    from app.dependencies import _ALL_CACHED_FACTORIES

    for fn in _ALL_CACHED_FACTORIES:
        fn.cache_clear()

    from app.main import create_app

    app = create_app()

    # Override LLM with fake
    from app.dependencies import get_llm
    from tests.test_e2e.stubs.llm_stub import FakeLLMClient

    fake_llm = FakeLLMClient()
    app.dependency_overrides[get_llm] = lambda: fake_llm

    # Disable rate limiters for E2E tests
    from app.common.rate_limit import rate_limit_ingests, rate_limit_queries

    app.dependency_overrides[rate_limit_queries] = lambda: None
    app.dependency_overrides[rate_limit_ingests] = lambda: None

    yield app

    # Cleanup: clear caches so production singletons aren't polluted
    for fn in _ALL_CACHED_FACTORIES:
        fn.cache_clear()


# ---------------------------------------------------------------------------
# Module-scoped: httpx AsyncClient
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module")
async def e2e_client(e2e_app) -> AsyncIterator[AsyncClient]:
    """Yield an httpx AsyncClient wired to the E2E FastAPI app."""
    transport = ASGITransport(app=e2e_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Module-scoped: auth helpers
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module")
async def admin_auth_headers(e2e_client: AsyncClient) -> dict[str, str]:
    """Login as the seed admin user and return auth + matter headers."""
    resp = await e2e_client.post(
        "/api/v1/auth/login",
        json={"email": E2E_ADMIN_EMAIL, "password": E2E_ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {
        "Authorization": f"Bearer {token}",
        "X-Matter-ID": E2E_MATTER_ID,
    }


async def _ensure_user_and_login(
    e2e_client: AsyncClient,
    email: str,
    password: str,
    full_name: str,
    role: str,
) -> dict[str, str]:
    """Create a user in the DB (if not exists) and return auth headers.

    There is no admin user-creation API endpoint, so we insert directly
    into Postgres via the AuthService and a raw session.
    """
    from app.auth.service import AuthService
    from app.dependencies import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        existing = await AuthService.get_user_by_email(session, email)
        if existing is None:
            await AuthService.create_user(session, email, password, full_name, role)
            # Assign user to the default matter
            from sqlalchemy import text

            user = await AuthService.get_user_by_email(session, email)
            await session.execute(
                text(
                    "INSERT INTO user_case_matters (user_id, matter_id) "
                    "VALUES (:user_id, :matter_id) ON CONFLICT DO NOTHING"
                ),
                {"user_id": user.id, "matter_id": UUID(E2E_MATTER_ID)},
            )
            await session.commit()

    resp = await e2e_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, f"Login failed for {email}: {resp.text}"
    token = resp.json()["access_token"]
    return {
        "Authorization": f"Bearer {token}",
        "X-Matter-ID": E2E_MATTER_ID,
    }


@pytest_asyncio.fixture(scope="module")
async def attorney_auth_headers(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
) -> dict[str, str]:
    """Create an attorney user and return auth headers."""
    return await _ensure_user_and_login(
        e2e_client,
        email="attorney@nexus.dev",
        password="attorney-pass-123!",
        full_name="Test Attorney",
        role="attorney",
    )


@pytest_asyncio.fixture(scope="module")
async def reviewer_auth_headers(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
) -> dict[str, str]:
    """Create a reviewer user and return auth headers."""
    return await _ensure_user_and_login(
        e2e_client,
        email="reviewer@nexus.dev",
        password="reviewer-pass-123!",
        full_name="Test Reviewer",
        role="reviewer",
    )


# ---------------------------------------------------------------------------
# Module-scoped: ingested document (runs the full Celery pipeline)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module")
async def ingested_document(
    e2e_client: AsyncClient,
    admin_auth_headers: dict[str, str],
) -> dict:
    """Upload sample_legal_doc.txt and wait for ingestion to complete.

    Returns the job status response dict with job_id, status, etc.
    """
    file_path = FIXTURES_DIR / "sample_legal_doc.txt"
    file_bytes = file_path.read_bytes()

    resp = await e2e_client.post(
        "/api/v1/ingest",
        files={"file": ("sample_legal_doc.txt", BytesIO(file_bytes), "text/plain")},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, f"Ingest failed: {resp.text}"
    data = resp.json()
    job_id = data["job_id"]

    # .delay() was captured as a no-op — run the task in a thread now.
    run_pending_tasks()

    # Task completed synchronously (in thread) — fetch final status.
    resp = await e2e_client.get(
        f"/api/v1/jobs/{job_id}",
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200
    status = resp.json()
    assert status["status"] == "complete", f"Job did not complete: {status}"
    return status


# ---------------------------------------------------------------------------
# Function-scoped: sample file objects
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_txt_file() -> BytesIO:
    """Return a BytesIO with the sample legal doc content."""
    file_path = FIXTURES_DIR / "sample_legal_doc.txt"
    return BytesIO(file_path.read_bytes())
