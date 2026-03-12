"""Load test configuration from environment variables."""

from __future__ import annotations

import os

# Target NEXUS instance
TARGET_HOST: str = os.getenv("NEXUS_TARGET_HOST", "http://localhost:8000")

# Auth credentials for the test user
TEST_EMAIL: str = os.getenv("NEXUS_TEST_EMAIL", "admin@nexus.local")
TEST_PASSWORD: str = os.getenv("NEXUS_TEST_PASSWORD", "changeme")

# Matter ID to scope all data requests
TEST_MATTER_ID: str = os.getenv("NEXUS_TEST_MATTER_ID", "")

# Pool of realistic legal investigation queries
QUERY_POOL: list[str] = [
    q.strip()
    for q in os.getenv(
        "NEXUS_QUERY_POOL",
        (
            "Who are the key parties involved in this matter?"
            "|What financial transactions occurred between the parties?"
            "|Summarize the timeline of events."
            "|What evidence supports the plaintiff's claims?"
            "|Are there any privilege issues with the produced documents?"
            "|Which documents reference wire transfers or payments?"
            "|What is the relationship between the named entities?"
            "|Identify any communications that discuss settlement terms."
        ),
    ).split("|")
    if q.strip()
]

# Performance SLA constants (imported by sla.py for reference)
P95_BROWSE_MS = 500
P95_QUERY_MS = 30_000
P95_HEALTH_MS = 200
ERROR_RATE_MAX = 0.01
