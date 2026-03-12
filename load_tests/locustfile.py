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

import load_tests.sla  # noqa: F401 — registers SLA event listeners
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
        with self.client.get(
            "/api/v1/documents",
            params={"offset": offset, "limit": limit},
            headers=self._headers(),
            name="/api/v1/documents",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Status {response.status_code}")

    @task(3)
    def search_entities(self) -> None:
        """Entity listing with optional type filter."""
        params: dict[str, str | int] = {"limit": 50, "offset": 0}
        # Randomly apply a type filter ~50% of the time
        if random.random() < 0.5:
            params["entity_type"] = random.choice(["person", "organization", "location", "date"])
        with self.client.get(
            "/api/v1/entities",
            params=params,
            headers=self._headers(),
            name="/api/v1/entities",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Status {response.status_code}")

    @task(2)
    def run_query(self) -> None:
        """Synchronous investigation query (non-streaming).

        Uses POST /api/v1/query which returns the full response once the
        pipeline finishes.  For load testing purposes this is more useful
        than the SSE streaming endpoint because Locust can measure the
        complete request lifecycle.
        """
        query_text = random.choice(QUERY_POOL)
        with self.client.post(
            "/api/v1/query",
            json={"query": query_text},
            headers=self._headers(),
            name="/api/v1/query",
            # Query pipeline can take 30-60s under load — generous timeout.
            timeout=120,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Status {response.status_code}")

    @task(2)
    def run_query_stream(self) -> None:
        """SSE streaming investigation query."""
        query_text = random.choice(QUERY_POOL)
        with self.client.post(
            "/api/v1/query/stream",
            json={"query": query_text},
            headers=self._headers(),
            name="/api/v1/query/stream",
            stream=True,
            timeout=120,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Status {response.status_code}")
                return
            # Validate SSE format - at minimum we should get a done event
            got_data = False
            for line in response.iter_lines():
                if line:
                    got_data = True
                    break
            if not got_data:
                response.failure("No SSE data received")

    @task(1)
    def health_check(self) -> None:
        """Baseline latency measurement against the health endpoint."""
        with self.client.get(
            "/api/v1/health",
            name="/api/v1/health",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Status {response.status_code}")

    @task(1)
    def upload_file(self) -> None:
        """Upload a small test file to exercise ingestion concurrency.

        Creates a 1KB in-memory text file on each call to avoid
        needing a fixture file on disk.
        """
        # Generate ~1KB of content
        doc_id = random.randint(1, 100_000)
        line = f"Load test document {doc_id}. "
        # Repeat the line to reach ~1KB
        repeat_count = max(1, 1024 // len(line))
        content = (line * repeat_count)[:1024]
        file_obj = io.BytesIO(content.encode())
        self.client.post(
            "/api/v1/ingest",
            files={"file": ("load_test.txt", file_obj, "text/plain")},
            headers=self._headers(),
            name="/api/v1/ingest",
        )
