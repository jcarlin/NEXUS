"""Unit tests for the operations service layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from app.operations.schemas import (
    CeleryOverview,
    ContainerActionResponse,
    ContainerHealthStatus,
    ContainerLogsResponse,
    ContainerStatus,
    DependencyGraphResponse,
    UptimeListResponse,
)
from app.operations.service import CeleryService, DockerService, UptimeService

# ---------------------------------------------------------------------------
# Helpers to build mock Docker containers
# ---------------------------------------------------------------------------


def _make_mock_container(
    name: str,
    compose_project: str,
    service_name: str = "api",
    status: str = "running",
    image: str = "nexus:latest",
    health_status: str = "none",
) -> AsyncMock:
    """Create a mock aiodocker container with a `.show()` that returns container info."""
    info = {
        "Id": "abcdef123456789012",
        "Name": f"/{name}",
        "Config": {
            "Image": image,
            "Labels": {
                "com.docker.compose.project": compose_project,
                "com.docker.compose.service": service_name,
            },
        },
        "State": {
            "Status": status,
            "Health": {"Status": health_status},
            "StartedAt": "2025-06-01T00:00:00Z",
        },
        "NetworkSettings": {
            "Ports": {
                "8000/tcp": [{"HostPort": "8000"}],
            },
        },
    }

    container = AsyncMock()
    container.show = AsyncMock(return_value=info)
    container.restart = AsyncMock()
    container.stop = AsyncMock()
    container.start = AsyncMock()
    container.log = AsyncMock(return_value=["line1", "line2", "line3"])
    return container


def _make_mock_docker(containers: list[AsyncMock]) -> AsyncMock:
    """Create a mock aiodocker.Docker client."""
    docker = AsyncMock()
    docker.containers.list = AsyncMock(return_value=containers)
    return docker


# ---------------------------------------------------------------------------
# DockerService tests
# ---------------------------------------------------------------------------


class TestDockerServiceListContainers:
    async def test_list_containers_filters_by_project(self):
        """Only containers matching the compose project label are returned."""
        matching = _make_mock_container("nexus-api-1", "nexus", service_name="api")
        non_matching = _make_mock_container("other-db-1", "other-project", service_name="db")

        docker = _make_mock_docker([matching, non_matching])

        result = await DockerService.list_containers(docker, "nexus")

        assert len(result) == 1
        assert result[0].name == "nexus-api-1"
        assert result[0].service_name == "api"

    async def test_list_containers_parses_status(self):
        """Container status and health are parsed correctly."""
        container = _make_mock_container(
            "nexus-api-1",
            "nexus",
            status="running",
            health_status="healthy",
        )
        docker = _make_mock_docker([container])

        result = await DockerService.list_containers(docker, "nexus")

        assert result[0].status == ContainerStatus.RUNNING
        assert result[0].health == ContainerHealthStatus.HEALTHY

    async def test_list_containers_parses_ports(self):
        """Port mappings are correctly extracted."""
        container = _make_mock_container("nexus-api-1", "nexus")
        docker = _make_mock_docker([container])

        result = await DockerService.list_containers(docker, "nexus")

        assert "8000->8000/tcp" in result[0].ports


class TestDockerServiceRestart:
    async def test_restart_container_not_found(self):
        """Restart returns failure when container doesn't exist in the project."""
        docker = _make_mock_docker([])

        result = await DockerService.restart_container(docker, "nonexistent", "nexus")

        assert isinstance(result, ContainerActionResponse)
        assert result.success is False
        assert "not found" in result.message

    async def test_restart_container_success(self):
        """Restart calls container.restart() for a valid project container."""
        container = _make_mock_container("nexus-api-1", "nexus")
        docker = _make_mock_docker([container])

        result = await DockerService.restart_container(docker, "nexus-api-1", "nexus")

        assert result.success is True
        assert result.action == "restart"
        container.restart.assert_awaited_once()

    async def test_restart_container_wrong_project(self):
        """Restart refuses containers belonging to a different project."""
        container = _make_mock_container("other-api-1", "other-project")
        docker = _make_mock_docker([container])

        result = await DockerService.restart_container(docker, "other-api-1", "nexus")

        assert result.success is False


class TestDockerServiceStop:
    async def test_stop_container_success(self):
        """Stop calls container.stop() for a valid project container."""
        container = _make_mock_container("nexus-redis-1", "nexus", service_name="redis")
        docker = _make_mock_docker([container])

        result = await DockerService.stop_container(docker, "nexus-redis-1", "nexus")

        assert result.success is True
        assert result.action == "stop"
        container.stop.assert_awaited_once()

    async def test_stop_container_not_found(self):
        """Stop returns failure when container is not found."""
        docker = _make_mock_docker([])

        result = await DockerService.stop_container(docker, "nonexistent", "nexus")

        assert result.success is False


class TestDockerServiceStart:
    async def test_start_container_success(self):
        """Start calls container.start() for a valid project container."""
        container = _make_mock_container("nexus-redis-1", "nexus", service_name="redis")
        docker = _make_mock_docker([container])

        result = await DockerService.start_container(docker, "nexus-redis-1", "nexus")

        assert result.success is True
        assert result.action == "start"
        container.start.assert_awaited_once()

    async def test_start_container_not_found(self):
        """Start returns failure when container is not found."""
        docker = _make_mock_docker([])

        result = await DockerService.start_container(docker, "nonexistent", "nexus")

        assert result.success is False


class TestDockerServiceLogs:
    async def test_get_container_logs(self):
        """Container logs are returned as a list of lines."""
        container = _make_mock_container("nexus-api-1", "nexus")
        docker = _make_mock_docker([container])

        result = await DockerService.get_container_logs(docker, "nexus-api-1", "nexus", tail=100)

        assert isinstance(result, ContainerLogsResponse)
        assert result.container_name == "nexus-api-1"
        assert len(result.lines) == 3
        container.log.assert_awaited_once_with(stdout=True, stderr=True, tail=100)

    async def test_get_container_logs_not_found(self):
        """Logs for a missing container return a not-found message."""
        docker = _make_mock_docker([])

        result = await DockerService.get_container_logs(docker, "missing", "nexus")

        assert "not found" in result.lines[0]


class TestDockerServiceDependencyGraph:
    async def test_get_dependency_graph(self):
        """Dependency graph is parsed from docker-compose YAML files."""
        compose_yaml = """
services:
  api:
    image: nexus:latest
    depends_on:
      - postgres
      - redis
  postgres:
    image: postgres:16
  redis:
    image: redis:7
"""
        # Mock containers for status lookup
        api_container = _make_mock_container("nexus-api-1", "nexus", service_name="api")
        pg_container = _make_mock_container("nexus-postgres-1", "nexus", service_name="postgres")
        docker = _make_mock_docker([api_container, pg_container])

        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__ = lambda s: s
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            mock_open.return_value.read = MagicMock(return_value=compose_yaml)

            with patch("pathlib.Path.exists", return_value=True):
                import yaml

                with patch("yaml.safe_load", return_value=yaml.safe_load(compose_yaml)):
                    result = await DockerService.get_dependency_graph(docker, "nexus")

        assert isinstance(result, DependencyGraphResponse)
        assert len(result.nodes) >= 2
        api_node = next((n for n in result.nodes if n.service == "api"), None)
        assert api_node is not None
        assert "postgres" in api_node.depends_on
        assert "redis" in api_node.depends_on


# ---------------------------------------------------------------------------
# CeleryService tests
# ---------------------------------------------------------------------------


class TestCeleryServiceOverview:
    async def test_get_workers_overview(self):
        """Workers overview aggregates inspect data into CeleryOverview."""
        mock_inspect = MagicMock()
        mock_inspect.active.return_value = {
            "worker-1@host": [
                {
                    "id": "task-1",
                    "name": "app.ingestion.tasks.ingest",
                    "args": "()",
                    "kwargs": "{}",
                    "time_start": 1000000.0,
                    "delivery_info": {"routing_key": "default"},
                },
            ]
        }
        mock_inspect.stats.return_value = {
            "worker-1@host": {
                "total": {"worker-1@host": 50},
                "pool": {"max-concurrency": 4},
                "clock": 86400,
                "pid": 12345,
            }
        }
        mock_inspect.active_queues.return_value = {
            "worker-1@host": [
                {"name": "default"},
                {"name": "ingestion"},
            ]
        }
        mock_inspect.reserved.return_value = {}
        mock_inspect.scheduled.return_value = {}

        mock_app = MagicMock()
        mock_app.control.inspect.return_value = mock_inspect

        result = await CeleryService.get_workers_overview(mock_app)

        assert isinstance(result, CeleryOverview)
        assert len(result.workers) == 1
        assert result.workers[0].hostname == "worker-1@host"
        assert result.workers[0].active_tasks == 1
        assert result.workers[0].concurrency == 4
        assert result.workers[0].pid == 12345
        assert "default" in result.workers[0].queues
        assert len(result.active_tasks) == 1
        assert result.active_tasks[0].task_id == "task-1"

    async def test_get_workers_overview_no_workers(self):
        """When no workers are online, returns empty overview."""
        mock_inspect = MagicMock()
        mock_inspect.active.return_value = None
        mock_inspect.stats.return_value = None
        mock_inspect.active_queues.return_value = None
        mock_inspect.reserved.return_value = None
        mock_inspect.scheduled.return_value = None

        mock_app = MagicMock()
        mock_app.control.inspect.return_value = mock_inspect

        result = await CeleryService.get_workers_overview(mock_app)

        assert isinstance(result, CeleryOverview)
        assert len(result.workers) == 0
        assert len(result.queues) == 0
        assert len(result.active_tasks) == 0


class TestCeleryServiceShutdown:
    async def test_shutdown_worker(self):
        """Shutdown sends control command to the correct worker."""
        mock_app = MagicMock()

        result = await CeleryService.shutdown_worker(mock_app, "worker-1@host")

        assert result["hostname"] == "worker-1@host"
        assert result["action"] == "shutdown"
        assert result["status"] == "sent"
        mock_app.control.shutdown.assert_called_once_with(destination=["worker-1@host"])


class TestCeleryServicePoolRestart:
    async def test_pool_restart(self):
        """Pool restart sends control command to the correct worker."""
        mock_app = MagicMock()

        result = await CeleryService.pool_restart(mock_app, "worker-1@host")

        assert result["hostname"] == "worker-1@host"
        assert result["action"] == "pool_restart"
        mock_app.control.pool_restart.assert_called_once_with(destination=["worker-1@host"])


class TestCeleryServicePurgeQueue:
    async def test_purge_queue(self):
        """Purge queue connects and purges the named queue."""
        mock_app = MagicMock()

        # Mock the connection context manager
        mock_conn = MagicMock()
        mock_app.connection_or_acquire.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_app.connection_or_acquire.return_value.__exit__ = MagicMock(return_value=False)

        # Mock kombu.Queue
        mock_bound_queue = MagicMock()
        mock_bound_queue.purge.return_value = 3

        with patch("kombu.Queue") as mock_queue_cls:
            mock_queue_cls.return_value.bind.return_value = mock_bound_queue
            result = await CeleryService.purge_queue(mock_app, "ingestion")

        assert result["queue"] == "ingestion"
        assert result["purged"] == 3


class TestCeleryServiceRevokeTask:
    async def test_revoke_task(self):
        """Revoke sends control command with correct task_id and terminate flag."""
        mock_app = MagicMock()

        result = await CeleryService.revoke_task(mock_app, "task-abc-123", terminate=True)

        assert result["task_id"] == "task-abc-123"
        assert result["action"] == "revoke"
        assert result["terminate"] is True
        mock_app.control.revoke.assert_called_once_with("task-abc-123", terminate=True)

    async def test_revoke_task_no_terminate(self):
        """Revoke without terminate defaults to False."""
        mock_app = MagicMock()

        result = await CeleryService.revoke_task(mock_app, "task-xyz-789")

        assert result["terminate"] is False
        mock_app.control.revoke.assert_called_once_with("task-xyz-789", terminate=False)


# ---------------------------------------------------------------------------
# UptimeService tests
# ---------------------------------------------------------------------------


class TestUptimeService:
    async def test_get_uptime_summaries(self):
        """Uptime summaries are correctly calculated from DB rows."""
        # Build mock rows: (service_name, total_24h, ok_24h, total_7d, ok_7d, total_30d, ok_30d)
        mock_row_1 = ("postgres", 1440, 1439, 10080, 10000, 43200, 43000)
        mock_row_2 = ("redis", 1440, 1440, 10080, 10080, 43200, 43200)

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row_1, mock_row_2]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await UptimeService.get_uptime_summaries(mock_db)

        assert isinstance(result, UptimeListResponse)
        assert len(result.services) == 2
        pg = result.services[0]
        assert pg.service_name == "postgres"
        assert pg.total_checks_24h == 1440
        assert pg.uptime_24h == round((1439 / 1440) * 100, 2)
        redis_svc = result.services[1]
        assert redis_svc.service_name == "redis"
        assert redis_svc.uptime_24h == 100.0
        assert redis_svc.uptime_30d == 100.0

    async def test_get_uptime_summaries_empty(self):
        """Empty DB returns no services."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await UptimeService.get_uptime_summaries(mock_db)

        assert isinstance(result, UptimeListResponse)
        assert len(result.services) == 0
