"""Locust load test suite for the NEXUS platform.

Models attorney workflows: document browsing, entity search, investigation
queries, and file upload concurrency.  Authenticates via JWT on start.

Usage:
    # Web UI (default port 8089)
    locust -f load_tests/locustfile.py

    # Headless smoke test
    locust -f load_tests/locustfile.py --headless -u 10 -r 2 --run-time 60s

Configuration is read from environment variables — see ``load_tests/config.py``.
"""

from __future__ import annotations

import io
import random

from locust import HttpUser, between, task

from load_tests.config import (
    QUERY_POOL,
    TEST_EMAIL,
    TEST_MATTER_ID,
    TEST_PASSWORD,
)


class NexusUser(HttpUser):
    """Simulates an attorney interacting with the NEXUS platform.

    Task weights reflect a realistic session: mostly browsing documents and
    entities, with occasional investigation queries and rare file uploads.
    """

    # Wait 1-3 seconds between tasks to simulate human think-time.
    wait_time = between(1, 3)

    # Set on login — reused for every subsequent request.
    _token: str = ""
    _matter_id: str = ""

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def on_start(self) -> None:
        """Authenticate and obtain a JWT access token."""
        self._matter_id = TEST_MATTER_ID

        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            name="/api/v1/auth/login",
        )

        if response.status_code == 200:
            data = response.json()
            self._token = data["access_token"]
        else:
            # Log failure but let Locust continue — tasks will fail with 401
            # which surfaces clearly in the results dashboard.
            self._token = ""

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _headers(self) -> dict[str, str]:
        """Return auth + matter-scoped headers for data endpoints."""
        headers: dict[str, str] = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if self._matter_id:
            headers["X-Matter-ID"] = self._matter_id
        return headers

    # ------------------------------------------------------------------ #
    # Tasks — weighted by realistic attorney usage patterns
    # ------------------------------------------------------------------ #

    @task(5)
    def browse_documents(self) -> None:
        """Paginated document listing with random offset."""
        offset = random.randint(0, 100)
        limit = random.choice([20, 50])
        self.client.get(
            "/api/v1/documents",
            params={"offset": offset, "limit": limit},
            headers=self._headers(),
            name="/api/v1/documents",
        )

    @task(3)
    def search_entities(self) -> None:
        """Entity listing with optional type filter."""
        params: dict[str, str | int] = {"limit": 50, "offset": 0}
        # Randomly apply a type filter ~50% of the time
        if random.random() < 0.5:
            params["entity_type"] = random.choice(["person", "organization", "location", "date"])
        self.client.get(
            "/api/v1/entities",
            params=params,
            headers=self._headers(),
            name="/api/v1/entities",
        )

    @task(2)
    def run_query(self) -> None:
        """Synchronous investigation query (non-streaming).

        Uses POST /api/v1/query which returns the full response once the
        pipeline finishes.  For load testing purposes this is more useful
        than the SSE streaming endpoint because Locust can measure the
        complete request lifecycle.
        """
        query_text = random.choice(QUERY_POOL)
        self.client.post(
            "/api/v1/query",
            json={"query": query_text},
            headers=self._headers(),
            name="/api/v1/query",
            # Query pipeline can take 30-60s under load — generous timeout.
            timeout=120,
        )

    @task(1)
    def health_check(self) -> None:
        """Baseline latency measurement against the health endpoint."""
        self.client.get(
            "/api/v1/health",
            name="/api/v1/health",
        )

    @task(1)
    def upload_file(self) -> None:
        """Upload a small test file to exercise ingestion concurrency.

        Creates a tiny in-memory text file on each call to avoid
        needing a fixture file on disk.
        """
        content = f"Load test document {random.randint(1, 100_000)}.\n"
        file_obj = io.BytesIO(content.encode())
        self.client.post(
            "/api/v1/ingest",
            files={"file": ("load_test.txt", file_obj, "text/plain")},
            headers=self._headers(),
            name="/api/v1/ingest",
        )
