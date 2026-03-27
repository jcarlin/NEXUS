"""Lightweight helper for scripts to register as tracked tasks in the NEXUS UI.

Usage::

    from scripts.lib.task_tracker import TaskTracker

    with TaskTracker("NER Backfill", "run_ner_pass.py", total=500) as tracker:
        for i, doc in enumerate(docs):
            process(doc)
            tracker.update(processed=i + 1)

The task appears in the Pipeline Monitor > Scripts tab with live progress.
Updates are throttled to at most 1 API call per ``update_interval`` seconds.
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests


class TaskTracker:
    """Register and track an external script task via the NEXUS API."""

    def __init__(
        self,
        name: str,
        script_name: str,
        total: int = 0,
        api_url: str | None = None,
        api_key: str | None = None,
        update_interval: float = 5.0,
    ) -> None:
        self.api_url = (api_url or os.environ.get("NEXUS_API_URL", "http://localhost:8000")).rstrip("/")
        self.api_key = api_key or os.environ.get("NEXUS_API_KEY", "")
        self.update_interval = update_interval
        self._last_update: float = 0.0
        self._task_id: str | None = None

        headers = self._headers()
        resp = requests.post(
            f"{self.api_url}/api/v1/scripts/tasks",
            json={"name": name, "script_name": script_name, "total": total},
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        self._task_id = resp.json()["id"]

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def update(
        self,
        processed: int | None = None,
        failed: int | None = None,
        total: int | None = None,
        force: bool = False,
    ) -> None:
        """Update progress (throttled to ``update_interval`` seconds)."""
        now = time.monotonic()
        if not force and (now - self._last_update) < self.update_interval:
            return
        self._last_update = now
        self._patch(processed=processed, failed=failed, total=total)

    def complete(self) -> None:
        """Mark the task as complete."""
        self._patch(status="complete")

    def fail(self, error: str) -> None:
        """Mark the task as failed with an error message."""
        self._patch(status="failed", error=error)

    def _patch(self, **kwargs: Any) -> None:
        if not self._task_id:
            return
        body = {k: v for k, v in kwargs.items() if v is not None}
        if not body:
            return
        try:
            requests.patch(
                f"{self.api_url}/api/v1/scripts/tasks/{self._task_id}",
                json=body,
                headers=self._headers(),
                timeout=10,
            )
        except Exception:
            pass  # Best-effort — don't break the script

    def __enter__(self) -> TaskTracker:
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        if exc_type:
            self.fail(str(exc_val))
        else:
            self.complete()
