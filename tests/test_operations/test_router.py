"""API endpoint tests for the service operations module."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.schemas import UserRecord
from app.operations.schemas import (
    CeleryOverview,
    CeleryQueueInfo,
    CeleryTaskInfo,
    CeleryWorkerInfo,
    ContainerActionResponse,
    ContainerHealthStatus,
    ContainerInfo,
    ContainerLogsResponse,
    ContainerStats,
    ContainerStatus,
    DependencyGraphResponse,
    ServiceDependency,
    UptimeListResponse,
    UptimeSummary,
)

_TEST_USER = UserRecord(
    id=UUID("00000000-0000-0000-0000-000000000099"),
    email="test@nexus.dev",
    full_name="Test User",
    role="admin",
    is_active=True,
    password_hash="$2b$12$fake",
    api_key_hash=None,
    created_at=datetime(2025, 1, 1, tzinfo=UTC),
    updated_at=datetime(2025, 1, 1, tzinfo=UTC),
)

_VIEWER_USER = UserRecord(
    id=UUID("00000000-0000-0000-0000-000000000088"),
    email="viewer@nexus.dev",
    full_name="Viewer User",
    role="viewer",
    is_active=True,
    password_hash="$2b$12$fake",
    api_key_hash=None,
    created_at=datetime(2025, 1, 1, tzinfo=UTC),
    updated_at=datetime(2025, 1, 1, tzinfo=UTC),
)

_TEST_MATTER_ID = UUID("00000000-0000-0000-0000-000000000001")

_API_PREFIX = "/api/v1/admin/operations"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def ops_client():
    """Yield an httpx AsyncClient with the operations router mounted."""
    from app import main as main_module
    from app.config import Settings

    async def _noop_lifespan(app):
        yield

    test_settings = Settings(
        enable_service_operations=True,
        anthropic_api_key="test",
        openai_api_key="test",
    )

    with (
        patch.object(main_module, "lifespan", _noop_lifespan),
        patch("app.main.get_settings", return_value=test_settings),
    ):
        test_app = main_module.create_app()

        from app.auth.middleware import get_current_user, get_matter_id
        from app.common.rate_limit import rate_limit_ingests, rate_limit_queries
        from app.operations.router import get_celery_app, get_docker_client

        test_app.dependency_overrides[rate_limit_queries] = lambda: None
        test_app.dependency_overrides[rate_limit_ingests] = lambda: None
        test_app.dependency_overrides[get_current_user] = lambda: _TEST_USER
        test_app.dependency_overrides[get_matter_id] = lambda: _TEST_MATTER_ID
        test_app.dependency_overrides[get_docker_client] = lambda: MagicMock()
        test_app.dependency_overrides[get_celery_app] = lambda: MagicMock()

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://testserver",
        ) as client:
            yield client


@pytest.fixture()
async def unauthed_ops_client():
    """Yield an httpx AsyncClient with operations router but no auth override."""
    from app import main as main_module
    from app.config import Settings

    async def _noop_lifespan(app):
        yield

    test_settings = Settings(
        enable_service_operations=True,
        anthropic_api_key="test",
        openai_api_key="test",
    )

    with (
        patch.object(main_module, "lifespan", _noop_lifespan),
        patch("app.main.get_settings", return_value=test_settings),
    ):
        test_app = main_module.create_app()

        from app.common.rate_limit import rate_limit_ingests, rate_limit_queries
        from app.operations.router import get_celery_app, get_docker_client

        test_app.dependency_overrides[rate_limit_queries] = lambda: None
        test_app.dependency_overrides[rate_limit_ingests] = lambda: None
        test_app.dependency_overrides[get_docker_client] = lambda: MagicMock()
        test_app.dependency_overrides[get_celery_app] = lambda: MagicMock()

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://testserver",
        ) as client:
            yield client


@pytest.fixture()
async def viewer_ops_client():
    """Yield an httpx AsyncClient with a non-admin (viewer) user."""
    from app import main as main_module
    from app.config import Settings

    async def _noop_lifespan(app):
        yield

    test_settings = Settings(
        enable_service_operations=True,
        anthropic_api_key="test",
        openai_api_key="test",
    )

    with (
        patch.object(main_module, "lifespan", _noop_lifespan),
        patch("app.main.get_settings", return_value=test_settings),
    ):
        test_app = main_module.create_app()

        from app.auth.middleware import get_current_user, get_matter_id
        from app.common.rate_limit import rate_limit_ingests, rate_limit_queries
        from app.operations.router import get_celery_app, get_docker_client

        test_app.dependency_overrides[rate_limit_queries] = lambda: None
        test_app.dependency_overrides[rate_limit_ingests] = lambda: None
        test_app.dependency_overrides[get_current_user] = lambda: _VIEWER_USER
        test_app.dependency_overrides[get_matter_id] = lambda: _TEST_MATTER_ID
        test_app.dependency_overrides[get_docker_client] = lambda: MagicMock()
        test_app.dependency_overrides[get_celery_app] = lambda: MagicMock()

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://testserver",
        ) as client:
            yield client


# ---------------------------------------------------------------------------
# Container endpoint tests
# ---------------------------------------------------------------------------


class TestListContainers:
    async def test_list_containers(self, ops_client: AsyncClient):
        """GET /containers returns a list of container info objects."""
        mock_containers = [
            ContainerInfo(
                container_id="abc123",
                name="nexus-api-1",
                service_name="api",
                image="nexus:latest",
                status=ContainerStatus.RUNNING,
                health=ContainerHealthStatus.HEALTHY,
                uptime_seconds=3600,
                started_at=datetime(2025, 6, 1, tzinfo=UTC),
                stats=ContainerStats(cpu_percent=5.2, memory_usage_mb=256, memory_limit_mb=1024, memory_percent=25.0),
                ports=["8000->8000/tcp"],
            ),
            ContainerInfo(
                container_id="def456",
                name="nexus-redis-1",
                service_name="redis",
                image="redis:7",
                status=ContainerStatus.RUNNING,
                health=ContainerHealthStatus.NONE,
                uptime_seconds=7200,
                ports=["6379->6379/tcp"],
            ),
        ]

        with patch(
            "app.operations.router.DockerService.list_containers",
            new_callable=AsyncMock,
            return_value=mock_containers,
        ):
            resp = await ops_client.get(f"{_API_PREFIX}/containers")

        assert resp.status_code == 200
        data = resp.json()
        assert "containers" in data
        assert len(data["containers"]) == 2
        assert data["containers"][0]["name"] == "nexus-api-1"
        assert data["containers"][0]["status"] == "running"
        assert data["containers"][1]["service_name"] == "redis"


class TestDockerUnavailable:
    async def test_list_containers_docker_unavailable(self, ops_client: AsyncClient):
        """GET /containers returns 503 when Docker daemon is not running."""
        with patch(
            "app.operations.router.DockerService.list_containers",
            new_callable=AsyncMock,
            side_effect=Exception("Cannot connect to Docker daemon"),
        ):
            resp = await ops_client.get(f"{_API_PREFIX}/containers")

        assert resp.status_code == 503
        assert "Docker daemon is unavailable" in resp.json()["detail"]

    async def test_dependency_graph_docker_unavailable(self, ops_client: AsyncClient):
        """GET /dependencies returns 503 when Docker daemon is not running."""
        with patch(
            "app.operations.router.DockerService.get_dependency_graph",
            new_callable=AsyncMock,
            side_effect=Exception("Cannot connect to Docker daemon"),
        ):
            resp = await ops_client.get(f"{_API_PREFIX}/dependencies")

        assert resp.status_code == 503
        assert "Docker daemon is unavailable" in resp.json()["detail"]

    async def test_container_action_docker_unavailable(self, ops_client: AsyncClient):
        """POST /containers/{name}/action returns 503 when Docker is down."""
        with patch(
            "app.operations.router.DockerService.restart_container",
            new_callable=AsyncMock,
            side_effect=Exception("Cannot connect to Docker daemon"),
        ):
            resp = await ops_client.post(
                f"{_API_PREFIX}/containers/nexus-api-1/action",
                json={"action": "restart"},
            )

        assert resp.status_code == 503
        assert "Docker daemon is unavailable" in resp.json()["detail"]

    async def test_container_logs_docker_unavailable(self, ops_client: AsyncClient):
        """GET /containers/{name}/logs returns 503 when Docker is down."""
        with patch(
            "app.operations.router.DockerService.get_container_logs",
            new_callable=AsyncMock,
            side_effect=Exception("Cannot connect to Docker daemon"),
        ):
            resp = await ops_client.get(f"{_API_PREFIX}/containers/nexus-api-1/logs")

        assert resp.status_code == 503
        assert "Docker daemon is unavailable" in resp.json()["detail"]


class TestContainerActions:
    async def test_container_restart(self, ops_client: AsyncClient):
        """POST /containers/{name}/action with restart succeeds."""
        mock_response = ContainerActionResponse(
            container_name="nexus-api-1",
            action="restart",
            success=True,
            message="Container restarted",
        )

        with patch(
            "app.operations.router.DockerService.restart_container",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            resp = await ops_client.post(
                f"{_API_PREFIX}/containers/nexus-api-1/action",
                json={"action": "restart"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["action"] == "restart"
        assert data["container_name"] == "nexus-api-1"

    async def test_container_stop(self, ops_client: AsyncClient):
        """POST /containers/{name}/action with stop succeeds."""
        mock_response = ContainerActionResponse(
            container_name="nexus-redis-1",
            action="stop",
            success=True,
            message="Container stopped",
        )

        with patch(
            "app.operations.router.DockerService.stop_container",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            resp = await ops_client.post(
                f"{_API_PREFIX}/containers/nexus-redis-1/action",
                json={"action": "stop"},
            )

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["action"] == "stop"

    async def test_container_start(self, ops_client: AsyncClient):
        """POST /containers/{name}/action with start succeeds."""
        mock_response = ContainerActionResponse(
            container_name="nexus-redis-1",
            action="start",
            success=True,
            message="Container started",
        )

        with patch(
            "app.operations.router.DockerService.start_container",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            resp = await ops_client.post(
                f"{_API_PREFIX}/containers/nexus-redis-1/action",
                json={"action": "start"},
            )

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["action"] == "start"

    async def test_container_invalid_action(self, ops_client: AsyncClient):
        """POST /containers/{name}/action with an invalid action returns 422."""
        resp = await ops_client.post(
            f"{_API_PREFIX}/containers/nexus-api-1/action",
            json={"action": "delete"},
        )

        assert resp.status_code == 422


class TestContainerLogs:
    async def test_container_logs(self, ops_client: AsyncClient):
        """GET /containers/{name}/logs returns log lines."""
        mock_response = ContainerLogsResponse(
            container_name="nexus-api-1",
            lines=["INFO: Application startup complete", "INFO: Uvicorn running on 0.0.0.0:8000"],
        )

        with patch(
            "app.operations.router.DockerService.get_container_logs",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            resp = await ops_client.get(f"{_API_PREFIX}/containers/nexus-api-1/logs")

        assert resp.status_code == 200
        data = resp.json()
        assert data["container_name"] == "nexus-api-1"
        assert len(data["lines"]) == 2
        assert "startup complete" in data["lines"][0]


# ---------------------------------------------------------------------------
# Celery endpoint tests
# ---------------------------------------------------------------------------


class TestCeleryOverview:
    async def test_celery_overview(self, ops_client: AsyncClient):
        """GET /celery returns overview of workers, queues, active tasks."""
        mock_overview = CeleryOverview(
            workers=[
                CeleryWorkerInfo(
                    hostname="worker-1@host",
                    status="online",
                    active_tasks=2,
                    processed=150,
                    concurrency=4,
                    queues=["default", "ingestion"],
                    uptime_seconds=86400,
                    pid=12345,
                ),
            ],
            queues=[
                CeleryQueueInfo(name="default", active_count=1, reserved_count=0, scheduled_count=0),
                CeleryQueueInfo(name="ingestion", active_count=1, reserved_count=2, scheduled_count=0),
            ],
            active_tasks=[
                CeleryTaskInfo(
                    task_id="task-abc-123",
                    name="app.ingestion.tasks.ingest_document",
                    worker="worker-1@host",
                    queue="ingestion",
                ),
            ],
        )

        with patch(
            "app.operations.router.CeleryService.get_workers_overview",
            new_callable=AsyncMock,
            return_value=mock_overview,
        ):
            resp = await ops_client.get(f"{_API_PREFIX}/celery")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["workers"]) == 1
        assert data["workers"][0]["hostname"] == "worker-1@host"
        assert data["workers"][0]["active_tasks"] == 2
        assert len(data["queues"]) == 2
        assert len(data["active_tasks"]) == 1
        assert data["active_tasks"][0]["task_id"] == "task-abc-123"


class TestCeleryWorkerActions:
    async def test_celery_worker_restart(self, ops_client: AsyncClient):
        """POST /celery/workers/{hostname}/restart sends pool restart."""
        with patch(
            "app.operations.router.CeleryService.pool_restart",
            new_callable=AsyncMock,
            return_value={"hostname": "worker-1@host", "action": "pool_restart", "status": "sent"},
        ):
            resp = await ops_client.post(f"{_API_PREFIX}/celery/workers/worker-1@host/restart")

        assert resp.status_code == 200
        assert resp.json()["action"] == "pool_restart"
        assert resp.json()["status"] == "sent"

    async def test_celery_worker_shutdown(self, ops_client: AsyncClient):
        """POST /celery/workers/{hostname}/shutdown sends shutdown command."""
        with patch(
            "app.operations.router.CeleryService.shutdown_worker",
            new_callable=AsyncMock,
            return_value={"hostname": "worker-1@host", "action": "shutdown", "status": "sent"},
        ):
            resp = await ops_client.post(f"{_API_PREFIX}/celery/workers/worker-1@host/shutdown")

        assert resp.status_code == 200
        assert resp.json()["action"] == "shutdown"


class TestCeleryQueuePurge:
    async def test_celery_queue_purge(self, ops_client: AsyncClient):
        """POST /celery/queues/{name}/purge purges the queue."""
        with patch(
            "app.operations.router.CeleryService.purge_queue",
            new_callable=AsyncMock,
            return_value={"queue": "ingestion", "purged": 5},
        ):
            resp = await ops_client.post(f"{_API_PREFIX}/celery/queues/ingestion/purge")

        assert resp.status_code == 200
        assert resp.json()["queue"] == "ingestion"
        assert resp.json()["purged"] == 5


class TestCeleryTaskRevoke:
    async def test_celery_task_revoke(self, ops_client: AsyncClient):
        """POST /celery/tasks/{task_id}/revoke revokes the task."""
        with patch(
            "app.operations.router.CeleryService.revoke_task",
            new_callable=AsyncMock,
            return_value={"task_id": "task-abc-123", "action": "revoke", "terminate": False},
        ):
            resp = await ops_client.post(f"{_API_PREFIX}/celery/tasks/task-abc-123/revoke")

        assert resp.status_code == 200
        assert resp.json()["task_id"] == "task-abc-123"
        assert resp.json()["terminate"] is False


# ---------------------------------------------------------------------------
# Dependency graph & uptime
# ---------------------------------------------------------------------------


class TestDependencyGraph:
    async def test_dependency_graph(self, ops_client: AsyncClient):
        """GET /dependencies returns the service dependency graph."""
        mock_graph = DependencyGraphResponse(
            nodes=[
                ServiceDependency(
                    service="api", depends_on=["postgres", "redis", "qdrant"], status="running", health="healthy"
                ),
                ServiceDependency(service="postgres", depends_on=[], status="running", health="healthy"),
                ServiceDependency(service="redis", depends_on=[], status="running", health="none"),
            ]
        )

        with patch(
            "app.operations.router.DockerService.get_dependency_graph",
            new_callable=AsyncMock,
            return_value=mock_graph,
        ):
            resp = await ops_client.get(f"{_API_PREFIX}/dependencies")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == 3
        api_node = next(n for n in data["nodes"] if n["service"] == "api")
        assert "postgres" in api_node["depends_on"]


class TestUptimeSummaries:
    async def test_uptime_summaries(self, ops_client: AsyncClient):
        """GET /uptime returns uptime summaries for services."""
        mock_response = UptimeListResponse(
            services=[
                UptimeSummary(
                    service_name="postgres",
                    uptime_24h=99.95,
                    uptime_7d=99.80,
                    uptime_30d=99.50,
                    total_checks_24h=1440,
                    total_checks_7d=10080,
                    total_checks_30d=43200,
                ),
                UptimeSummary(
                    service_name="redis",
                    uptime_24h=100.0,
                    uptime_7d=100.0,
                    uptime_30d=99.99,
                    total_checks_24h=1440,
                    total_checks_7d=10080,
                    total_checks_30d=43200,
                ),
            ]
        )

        with patch(
            "app.operations.router.UptimeService.get_uptime_summaries",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            resp = await ops_client.get(f"{_API_PREFIX}/uptime")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["services"]) == 2
        pg = data["services"][0]
        assert pg["service_name"] == "postgres"
        assert pg["uptime_24h"] == 99.95


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------


class TestAuthEnforcement:
    async def test_unauthenticated_returns_401(self, unauthed_ops_client: AsyncClient):
        """Requests without auth credentials return 401."""
        resp = await unauthed_ops_client.get(f"{_API_PREFIX}/containers")
        assert resp.status_code == 401

    async def test_non_admin_returns_403(self, viewer_ops_client: AsyncClient):
        """Requests from non-admin users return 403."""
        resp = await viewer_ops_client.get(f"{_API_PREFIX}/containers")
        assert resp.status_code == 403
