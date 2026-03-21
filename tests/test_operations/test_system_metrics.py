"""Unit tests for the SystemMetrics feature (service + endpoint)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.schemas import UserRecord
from app.operations.schemas import SystemMetrics
from app.operations.service import SystemMetricsService

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
    """Yield an httpx AsyncClient with the operations router mounted (admin user)."""
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
# Service tests
# ---------------------------------------------------------------------------


class TestGetSystemMetricsAllSources:
    async def test_get_system_metrics_all_sources(self):
        """All 7 fields are populated when proc files and disk are available."""
        # _parse_proc_stat is called twice (100ms apart) to compute CPU delta.
        # First call: idle=100, total=1000. Second call: idle=150, total=1100.
        # idle_delta = 50, total_delta = 100 → cpu% = (1 - 50/100) * 100 = 50.0
        call_count = 0

        def _mock_proc_stat() -> tuple[float, float]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (100.0, 1000.0)  # idle, total
            return (150.0, 1100.0)

        # _parse_proc_meminfo returns (total_kb, available_kb).
        # total=8_000_000 kB, available=4_000_000 kB → used=4_000_000 kB
        # used_mb = 4_000_000/1024 ≈ 3906.2, total_mb = 8_000_000/1024 ≈ 7812.5
        # percent = (4_000_000/8_000_000)*100 = 50.0
        def _mock_proc_meminfo() -> tuple[float, float]:
            return (8_000_000.0, 4_000_000.0)

        # shutil.disk_usage returns a named-tuple-like with .total, .used, .free
        mock_disk = MagicMock()
        mock_disk.total = 500 * (1024**3)  # 500 GB
        mock_disk.used = 200 * (1024**3)  # 200 GB
        mock_disk.free = 300 * (1024**3)

        with (
            patch.object(SystemMetricsService, "_parse_proc_stat", side_effect=_mock_proc_stat),
            patch.object(SystemMetricsService, "_parse_proc_meminfo", side_effect=_mock_proc_meminfo),
            patch("shutil.disk_usage", return_value=mock_disk),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await SystemMetricsService.get_system_metrics()

        assert isinstance(result, SystemMetrics)
        assert result.cpu_percent == 50.0
        assert result.memory_used_mb == round(4_000_000 / 1024, 1)
        assert result.memory_total_mb == round(8_000_000 / 1024, 1)
        assert result.memory_percent == 50.0
        assert result.disk_used_gb == 200.0
        assert result.disk_total_gb == 500.0
        assert result.disk_percent == round((200 / 500) * 100, 1)


class TestCpuProcStatNotFound:
    async def test_cpu_proc_stat_not_found(self):
        """CPU falls back to 0 when /proc/stat is missing; other metrics still work."""

        def _mock_proc_meminfo() -> tuple[float, float]:
            return (8_000_000.0, 4_000_000.0)

        mock_disk = MagicMock()
        mock_disk.total = 500 * (1024**3)
        mock_disk.used = 200 * (1024**3)
        mock_disk.free = 300 * (1024**3)

        with (
            patch.object(
                SystemMetricsService,
                "_parse_proc_stat",
                side_effect=FileNotFoundError("/proc/stat"),
            ),
            patch.object(SystemMetricsService, "_parse_proc_meminfo", side_effect=_mock_proc_meminfo),
            patch("shutil.disk_usage", return_value=mock_disk),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await SystemMetricsService.get_system_metrics()

        assert result.cpu_percent == 0.0
        # Memory and disk should still be populated
        assert result.memory_total_mb > 0
        assert result.memory_used_mb > 0
        assert result.disk_total_gb > 0
        assert result.disk_used_gb > 0


class TestMemoryProcMeminfoNotFound:
    async def test_memory_proc_meminfo_not_found(self):
        """Memory falls back to os.sysconf when /proc/meminfo is missing."""
        call_count = 0

        def _mock_proc_stat() -> tuple[float, float]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (100.0, 1000.0)
            return (150.0, 1100.0)

        mock_disk = MagicMock()
        mock_disk.total = 500 * (1024**3)
        mock_disk.used = 200 * (1024**3)
        mock_disk.free = 300 * (1024**3)

        # os.sysconf("SC_PAGE_SIZE")=4096, os.sysconf("SC_PHYS_PAGES")=1048576
        # total_bytes = 4096 * 1048576 = 4294967296 = 4096 MB
        def _mock_sysconf(name: str) -> int:
            if name == "SC_PAGE_SIZE":
                return 4096
            if name == "SC_PHYS_PAGES":
                return 1048576
            raise ValueError(f"unknown: {name}")

        with (
            patch.object(SystemMetricsService, "_parse_proc_stat", side_effect=_mock_proc_stat),
            patch.object(
                SystemMetricsService,
                "_parse_proc_meminfo",
                side_effect=FileNotFoundError("/proc/meminfo"),
            ),
            patch("shutil.disk_usage", return_value=mock_disk),
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch("os.sysconf", side_effect=_mock_sysconf),
        ):
            result = await SystemMetricsService.get_system_metrics()

        # Fallback: total populated from sysconf, used=0, percent=0
        expected_total_mb = round((4096 * 1048576) / (1024 * 1024), 1)
        assert result.memory_total_mb == expected_total_mb
        assert result.memory_used_mb == 0.0
        assert result.memory_percent == 0.0
        # CPU and disk should still work
        assert result.cpu_percent == 50.0
        assert result.disk_total_gb > 0


class TestDiskFailure:
    async def test_disk_failure(self):
        """Disk fields are 0 when shutil.disk_usage raises; other metrics still work."""
        call_count = 0

        def _mock_proc_stat() -> tuple[float, float]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (100.0, 1000.0)
            return (150.0, 1100.0)

        def _mock_proc_meminfo() -> tuple[float, float]:
            return (8_000_000.0, 4_000_000.0)

        with (
            patch.object(SystemMetricsService, "_parse_proc_stat", side_effect=_mock_proc_stat),
            patch.object(SystemMetricsService, "_parse_proc_meminfo", side_effect=_mock_proc_meminfo),
            patch("shutil.disk_usage", side_effect=OSError("disk unavailable")),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await SystemMetricsService.get_system_metrics()

        assert result.disk_used_gb == 0.0
        assert result.disk_total_gb == 0.0
        assert result.disk_percent == 0.0
        # CPU and memory should still be populated
        assert result.cpu_percent == 50.0
        assert result.memory_total_mb > 0


class TestAllSourcesUnavailable:
    async def test_all_sources_unavailable(self):
        """All fields are 0 when every source fails; no exception raised."""
        with (
            patch.object(
                SystemMetricsService,
                "_parse_proc_stat",
                side_effect=FileNotFoundError("/proc/stat"),
            ),
            patch.object(
                SystemMetricsService,
                "_parse_proc_meminfo",
                side_effect=FileNotFoundError("/proc/meminfo"),
            ),
            patch("shutil.disk_usage", side_effect=OSError("disk unavailable")),
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch("os.sysconf", side_effect=OSError("sysconf unavailable")),
        ):
            result = await SystemMetricsService.get_system_metrics()

        assert isinstance(result, SystemMetrics)
        assert result.cpu_percent == 0.0
        assert result.memory_used_mb == 0.0
        assert result.memory_total_mb == 0.0
        assert result.memory_percent == 0.0
        assert result.disk_used_gb == 0.0
        assert result.disk_total_gb == 0.0
        assert result.disk_percent == 0.0


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------

_FIXED_METRICS = SystemMetrics(
    cpu_percent=25.5,
    memory_used_mb=4096.0,
    memory_total_mb=16384.0,
    memory_percent=25.0,
    disk_used_gb=120.0,
    disk_total_gb=500.0,
    disk_percent=24.0,
)


class TestSystemMetricsEndpointAdmin:
    async def test_system_metrics_endpoint_admin(self, ops_client: AsyncClient):
        """Admin user receives 200 with valid SystemMetrics JSON."""
        with patch(
            "app.operations.router.SystemMetricsService.get_system_metrics",
            new_callable=AsyncMock,
            return_value=_FIXED_METRICS,
        ):
            resp = await ops_client.get(f"{_API_PREFIX}/system-metrics")

        assert resp.status_code == 200
        data = resp.json()
        assert data["cpu_percent"] == 25.5
        assert data["memory_used_mb"] == 4096.0
        assert data["memory_total_mb"] == 16384.0
        assert data["memory_percent"] == 25.0
        assert data["disk_used_gb"] == 120.0
        assert data["disk_total_gb"] == 500.0
        assert data["disk_percent"] == 24.0


class TestSystemMetricsEndpointViewerForbidden:
    async def test_system_metrics_endpoint_viewer_forbidden(self, viewer_ops_client: AsyncClient):
        """Viewer (non-admin) user receives 403 Forbidden."""
        with patch(
            "app.operations.router.SystemMetricsService.get_system_metrics",
            new_callable=AsyncMock,
            return_value=_FIXED_METRICS,
        ):
            resp = await viewer_ops_client.get(f"{_API_PREFIX}/system-metrics")

        assert resp.status_code == 403
