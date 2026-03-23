"""Service layer for Docker container management, Celery control, and uptime tracking."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
    SystemMetrics,
    UptimeListResponse,
    UptimeSummary,
)

logger = structlog.get_logger(__name__)


class DockerService:
    """Docker container management via aiodocker."""

    @staticmethod
    async def list_containers(docker: Any, compose_project: str) -> list[ContainerInfo]:
        """List all containers belonging to the configured Docker Compose project."""
        containers = await docker.containers.list(all=True)
        results: list[ContainerInfo] = []

        for c in containers:
            info = await c.show()
            labels = info.get("Config", {}).get("Labels", {})
            project = labels.get("com.docker.compose.project", "")
            if project != compose_project:
                continue

            service_name = labels.get("com.docker.compose.service", "")
            name = info.get("Name", "").lstrip("/")
            container_id = info.get("Id", "")[:12]
            image = info.get("Config", {}).get("Image", "")

            # Status
            state = info.get("State", {})
            raw_status = state.get("Status", "unknown").lower()
            try:
                status = ContainerStatus(raw_status)
            except ValueError:
                status = ContainerStatus.EXITED

            # Health
            health_obj = state.get("Health", {})
            raw_health = health_obj.get("Status", "none").lower()
            try:
                health = ContainerHealthStatus(raw_health)
            except ValueError:
                health = ContainerHealthStatus.NONE

            # Uptime
            started_at_str = state.get("StartedAt", "")
            started_at: datetime | None = None
            uptime_seconds = 0
            if started_at_str and raw_status == "running":
                try:
                    started_at = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
                    uptime_seconds = int((datetime.now(UTC) - started_at).total_seconds())
                except (ValueError, TypeError):
                    pass

            # Ports
            ports: list[str] = []
            network_settings = info.get("NetworkSettings", {})
            port_map = network_settings.get("Ports", {}) or {}
            for container_port, bindings in port_map.items():
                if bindings:
                    for b in bindings:
                        host_port = b.get("HostPort", "")
                        if host_port:
                            ports.append(f"{host_port}->{container_port}")
                else:
                    ports.append(container_port)

            results.append(
                ContainerInfo(
                    container_id=container_id,
                    name=name,
                    service_name=service_name,
                    image=image,
                    status=status,
                    health=health,
                    uptime_seconds=uptime_seconds,
                    started_at=started_at,
                    ports=ports,
                )
            )

        return results

    @staticmethod
    async def get_container_stats(docker: Any, container_id: str) -> ContainerStats:
        """Get CPU/memory stats for a container using a two-read delta."""
        container = await docker.containers.get(container_id)
        stats = await container.stats(stream=False)

        # CPU percentage (delta between two reads)
        cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats["precpu_stats"]["cpu_usage"]["total_usage"]
        system_delta = stats["cpu_stats"].get("system_cpu_usage", 0) - stats["precpu_stats"].get("system_cpu_usage", 0)
        online_cpus = stats["cpu_stats"].get("online_cpus", 1)
        cpu_percent = 0.0
        if system_delta > 0:
            cpu_percent = round((cpu_delta / system_delta) * online_cpus * 100.0, 2)

        # Memory
        mem_stats = stats.get("memory_stats", {})
        mem_usage = mem_stats.get("usage", 0)
        mem_limit = mem_stats.get("limit", 0)
        cache = mem_stats.get("stats", {}).get("cache", 0)
        actual_usage = mem_usage - cache

        memory_usage_mb = round(actual_usage / (1024 * 1024), 2)
        memory_limit_mb = round(mem_limit / (1024 * 1024), 2)
        memory_percent = round((actual_usage / mem_limit) * 100, 2) if mem_limit > 0 else 0.0

        return ContainerStats(
            cpu_percent=cpu_percent,
            memory_usage_mb=memory_usage_mb,
            memory_limit_mb=memory_limit_mb,
            memory_percent=memory_percent,
        )

    @staticmethod
    async def _get_project_container(docker: Any, name: str, compose_project: str) -> Any:
        """Look up a container by name and verify it belongs to the compose project."""
        containers = await docker.containers.list(all=True)
        for c in containers:
            info = await c.show()
            container_name = info.get("Name", "").lstrip("/")
            labels = info.get("Config", {}).get("Labels", {})
            project = labels.get("com.docker.compose.project", "")
            if container_name == name and project == compose_project:
                return c
        return None

    @staticmethod
    async def restart_container(docker: Any, name: str, compose_project: str) -> ContainerActionResponse:
        """Restart a container by name (must belong to compose project)."""
        container = await DockerService._get_project_container(docker, name, compose_project)
        if container is None:
            return ContainerActionResponse(
                container_name=name, action="restart", success=False, message=f"Container '{name}' not found"
            )
        try:
            await container.restart()
            logger.info("container.restart.ok", container=name)
            return ContainerActionResponse(
                container_name=name, action="restart", success=True, message="Container restarted"
            )
        except Exception as exc:
            logger.error("container.restart.failed", container=name, error=str(exc))
            return ContainerActionResponse(container_name=name, action="restart", success=False, message=str(exc))

    @staticmethod
    async def stop_container(docker: Any, name: str, compose_project: str) -> ContainerActionResponse:
        """Stop a container by name (must belong to compose project)."""
        container = await DockerService._get_project_container(docker, name, compose_project)
        if container is None:
            return ContainerActionResponse(
                container_name=name, action="stop", success=False, message=f"Container '{name}' not found"
            )
        try:
            await container.stop()
            logger.info("container.stop.ok", container=name)
            return ContainerActionResponse(
                container_name=name, action="stop", success=True, message="Container stopped"
            )
        except Exception as exc:
            logger.error("container.stop.failed", container=name, error=str(exc))
            return ContainerActionResponse(container_name=name, action="stop", success=False, message=str(exc))

    @staticmethod
    async def start_container(docker: Any, name: str, compose_project: str) -> ContainerActionResponse:
        """Start a container by name (must belong to compose project)."""
        container = await DockerService._get_project_container(docker, name, compose_project)
        if container is None:
            return ContainerActionResponse(
                container_name=name, action="start", success=False, message=f"Container '{name}' not found"
            )
        try:
            await container.start()
            logger.info("container.start.ok", container=name)
            return ContainerActionResponse(
                container_name=name, action="start", success=True, message="Container started"
            )
        except Exception as exc:
            logger.error("container.start.failed", container=name, error=str(exc))
            return ContainerActionResponse(container_name=name, action="start", success=False, message=str(exc))

    @staticmethod
    async def get_container_logs(
        docker: Any, name: str, compose_project: str, tail: int = 500
    ) -> ContainerLogsResponse:
        """Get recent log lines from a container."""
        container = await DockerService._get_project_container(docker, name, compose_project)
        if container is None:
            return ContainerLogsResponse(container_name=name, lines=[f"Container '{name}' not found"])
        log_lines = await container.log(stdout=True, stderr=True, tail=tail)
        return ContainerLogsResponse(container_name=name, lines=log_lines)

    @staticmethod
    async def stream_container_logs(
        docker: Any, name: str, compose_project: str, tail: int = 100
    ) -> AsyncIterator[str]:
        """Async generator that yields log lines for SSE streaming."""
        container = await DockerService._get_project_container(docker, name, compose_project)
        if container is None:
            yield f"Container '{name}' not found"
            return

        log_stream = container.log(stdout=True, stderr=True, follow=True, tail=tail)
        async for line in log_stream:
            yield line

    @staticmethod
    async def get_dependency_graph(docker: Any, compose_project: str) -> DependencyGraphResponse:
        """Parse docker-compose YAML files to build a service dependency graph."""
        import yaml

        compose_files = [
            Path("docker-compose.yml"),
            Path("docker-compose.prod.yml"),
            Path("docker-compose.local.yml"),
        ]

        services_deps: dict[str, list[str]] = {}

        for compose_file in compose_files:
            if not compose_file.exists():
                continue
            try:
                with open(compose_file) as f:
                    data = yaml.safe_load(f) or {}
                for svc_name, svc_config in (data.get("services") or {}).items():
                    if svc_name not in services_deps:
                        services_deps[svc_name] = []
                    depends = svc_config.get("depends_on")
                    if isinstance(depends, list):
                        services_deps[svc_name].extend(depends)
                    elif isinstance(depends, dict):
                        services_deps[svc_name].extend(depends.keys())
            except Exception:
                logger.warning("dependency_graph.parse_failed", file=str(compose_file), exc_info=True)

        # Deduplicate deps
        for svc_name in services_deps:
            services_deps[svc_name] = sorted(set(services_deps[svc_name]))

        # Get running container statuses
        container_statuses: dict[str, tuple[str, str]] = {}
        try:
            containers = await docker.containers.list(all=True)
            for c in containers:
                info = await c.show()
                labels = info.get("Config", {}).get("Labels", {})
                if labels.get("com.docker.compose.project", "") != compose_project:
                    continue
                svc = labels.get("com.docker.compose.service", "")
                state = info.get("State", {})
                status = state.get("Status", "unknown")
                health_obj = state.get("Health", {})
                health = health_obj.get("Status", "none")
                container_statuses[svc] = (status, health)
        except Exception:
            logger.warning("dependency_graph.status_fetch_failed", exc_info=True)

        nodes: list[ServiceDependency] = []
        for svc_name, deps in services_deps.items():
            status, health = container_statuses.get(svc_name, ("unknown", "unknown"))
            nodes.append(
                ServiceDependency(
                    service=svc_name,
                    depends_on=deps,
                    status=status,
                    health=health,
                )
            )

        return DependencyGraphResponse(nodes=nodes)


class CeleryService:
    """Celery worker and queue management."""

    @staticmethod
    async def get_workers_overview(celery_app: Any) -> CeleryOverview:
        """Get overview of all Celery workers, queues, and active tasks."""
        inspect = celery_app.control.inspect()

        active = await asyncio.to_thread(inspect.active) or {}
        stats = await asyncio.to_thread(inspect.stats) or {}
        active_queues = await asyncio.to_thread(inspect.active_queues) or {}
        reserved = await asyncio.to_thread(inspect.reserved) or {}
        scheduled = await asyncio.to_thread(inspect.scheduled) or {}

        # Build worker info
        workers: list[CeleryWorkerInfo] = []
        all_hostnames = set(active.keys()) | set(stats.keys()) | set(active_queues.keys())
        for hostname in sorted(all_hostnames):
            worker_stats = stats.get(hostname, {})
            worker_active = active.get(hostname, [])
            worker_queues = active_queues.get(hostname, [])
            queue_names = [q.get("name", "") for q in worker_queues]

            workers.append(
                CeleryWorkerInfo(
                    hostname=hostname,
                    status="online",
                    active_tasks=len(worker_active),
                    processed=worker_stats.get("total", {}).get(hostname, sum(worker_stats.get("total", {}).values()))
                    if isinstance(worker_stats.get("total"), dict)
                    else 0,
                    concurrency=worker_stats.get("pool", {}).get("max-concurrency", 0),
                    queues=queue_names,
                    uptime_seconds=int(worker_stats.get("clock", 0)),
                    pid=worker_stats.get("pid"),
                )
            )

        # Build queue info
        queue_map: dict[str, CeleryQueueInfo] = {}
        for hostname, tasks in active.items():
            for task in tasks:
                queue = task.get("delivery_info", {}).get("routing_key", "default")
                if queue not in queue_map:
                    queue_map[queue] = CeleryQueueInfo(name=queue)
                queue_map[queue].active_count += 1
        for hostname, tasks in reserved.items():
            for task in tasks:
                queue = task.get("delivery_info", {}).get("routing_key", "default")
                if queue not in queue_map:
                    queue_map[queue] = CeleryQueueInfo(name=queue)
                queue_map[queue].reserved_count += 1
        for hostname, tasks in scheduled.items():
            for task in tasks:
                queue = task.get("request", {}).get("delivery_info", {}).get("routing_key", "default")
                if queue not in queue_map:
                    queue_map[queue] = CeleryQueueInfo(name=queue)
                queue_map[queue].scheduled_count += 1

        # Query broker for pending message counts (tasks not yet claimed)
        try:
            broker_url = celery_app.conf.broker_url or ""
            if "amqp" in broker_url:
                import httpx

                mgmt_url = "http://rabbitmq:15672/api/queues/nexus"
                rmq_user = "nexus"
                rmq_pass = "nexus"
                resp = httpx.get(mgmt_url, auth=(rmq_user, rmq_pass), timeout=5)
                if resp.status_code == 200:
                    for q_info in resp.json():
                        q_name = q_info.get("name", "")
                        pending = q_info.get("messages_ready", 0)
                        if q_name in queue_map:
                            queue_map[q_name].pending_count = pending
                        elif pending > 0:
                            queue_map[q_name] = CeleryQueueInfo(name=q_name, pending_count=pending)
        except Exception:
            logger.debug("celery.broker_queue_query.failed")

        queues = sorted(queue_map.values(), key=lambda q: q.name)

        # Build active tasks
        active_tasks: list[CeleryTaskInfo] = []
        for hostname, tasks in active.items():
            for task in tasks:
                active_tasks.append(
                    CeleryTaskInfo(
                        task_id=task.get("id", ""),
                        name=task.get("name", ""),
                        args=str(task.get("args", "")),
                        kwargs=str(task.get("kwargs", "")),
                        started_at=task.get("time_start"),
                        worker=hostname,
                        queue=task.get("delivery_info", {}).get("routing_key", ""),
                    )
                )

        return CeleryOverview(workers=workers, queues=queues, active_tasks=active_tasks)

    @staticmethod
    async def shutdown_worker(celery_app: Any, hostname: str) -> dict[str, str]:
        """Shutdown a Celery worker by hostname."""
        await asyncio.to_thread(celery_app.control.shutdown, destination=[hostname])
        logger.info("celery.worker.shutdown", hostname=hostname)
        return {"hostname": hostname, "action": "shutdown", "status": "sent"}

    @staticmethod
    async def pool_restart(celery_app: Any, hostname: str) -> dict[str, str]:
        """Restart the worker pool for a given hostname."""
        await asyncio.to_thread(celery_app.control.pool_restart, destination=[hostname])
        logger.info("celery.worker.pool_restart", hostname=hostname)
        return {"hostname": hostname, "action": "pool_restart", "status": "sent"}

    @staticmethod
    async def purge_queue(celery_app: Any, queue_name: str) -> dict[str, Any]:
        """Purge all messages from a Celery queue."""
        from kombu import Queue

        def _purge() -> int:
            with celery_app.connection_or_acquire() as conn:
                bound_queue = Queue(queue_name).bind(conn)
                return bound_queue.purge()

        count = await asyncio.to_thread(_purge)
        logger.info("celery.queue.purge", queue=queue_name, purged=count)
        return {"queue": queue_name, "purged": count}

    @staticmethod
    async def revoke_task(celery_app: Any, task_id: str, terminate: bool = False) -> dict[str, Any]:
        """Revoke (and optionally terminate) a Celery task."""
        await asyncio.to_thread(celery_app.control.revoke, task_id, terminate=terminate)
        logger.info("celery.task.revoke", task_id=task_id, terminate=terminate)
        return {"task_id": task_id, "action": "revoke", "terminate": terminate}


class UptimeService:
    """Service health uptime tracking via service_health_history table."""

    @staticmethod
    async def get_uptime_summaries(db: AsyncSession) -> UptimeListResponse:
        """Query uptime percentages for all services over 24h, 7d, and 30d windows."""
        result = await db.execute(
            text("""
                SELECT
                    service_name,
                    COUNT(*) FILTER (WHERE checked_at > NOW() - INTERVAL '24 hours') AS total_24h,
                    COUNT(*) FILTER (WHERE checked_at > NOW() - INTERVAL '24 hours' AND status = 'ok') AS ok_24h,
                    COUNT(*) FILTER (WHERE checked_at > NOW() - INTERVAL '7 days') AS total_7d,
                    COUNT(*) FILTER (WHERE checked_at > NOW() - INTERVAL '7 days' AND status = 'ok') AS ok_7d,
                    COUNT(*) FILTER (WHERE checked_at > NOW() - INTERVAL '30 days') AS total_30d,
                    COUNT(*) FILTER (WHERE checked_at > NOW() - INTERVAL '30 days' AND status = 'ok') AS ok_30d
                FROM service_health_history
                GROUP BY service_name
                ORDER BY service_name
            """)
        )
        rows = result.fetchall()

        services: list[UptimeSummary] = []
        for row in rows:
            total_24h = row[1] or 0
            ok_24h = row[2] or 0
            total_7d = row[3] or 0
            ok_7d = row[4] or 0
            total_30d = row[5] or 0
            ok_30d = row[6] or 0

            services.append(
                UptimeSummary(
                    service_name=row[0],
                    uptime_24h=round((ok_24h / total_24h) * 100, 2) if total_24h > 0 else 0.0,
                    uptime_7d=round((ok_7d / total_7d) * 100, 2) if total_7d > 0 else 0.0,
                    uptime_30d=round((ok_30d / total_30d) * 100, 2) if total_30d > 0 else 0.0,
                    total_checks_24h=total_24h,
                    total_checks_7d=total_7d,
                    total_checks_30d=total_30d,
                )
            )

        return UptimeListResponse(services=services)


class SystemMetricsService:
    """Host-level CPU, memory, and disk metrics collection."""

    @staticmethod
    async def get_system_metrics() -> SystemMetrics:
        """Collect host CPU, memory, and disk usage.

        Uses /proc/stat and /proc/meminfo on Linux (including inside Docker
        containers where these reflect the host). Falls back gracefully on
        platforms where /proc is unavailable (macOS dev).
        """

        cpu = await SystemMetricsService._read_cpu()
        mem = await SystemMetricsService._read_memory()
        disk = await asyncio.to_thread(SystemMetricsService._read_disk)

        gpu = await asyncio.to_thread(SystemMetricsService._read_gpu)

        return SystemMetrics(
            cpu_percent=cpu,
            memory_used_mb=mem[0],
            memory_total_mb=mem[1],
            memory_percent=mem[2],
            disk_used_gb=disk[0],
            disk_total_gb=disk[1],
            disk_percent=disk[2],
            gpu_name=gpu.get("name"),
            gpu_utilization_percent=gpu.get("utilization"),
            gpu_memory_used_mb=gpu.get("memory_used"),
            gpu_memory_total_mb=gpu.get("memory_total"),
            gpu_temperature_c=gpu.get("temperature"),
        )

    @staticmethod
    async def _read_cpu() -> float:
        """Compute host CPU% from two /proc/stat samples 100ms apart."""
        try:
            idle1, total1 = await asyncio.to_thread(SystemMetricsService._parse_proc_stat)
            await asyncio.sleep(0.1)
            idle2, total2 = await asyncio.to_thread(SystemMetricsService._parse_proc_stat)

            idle_delta = idle2 - idle1
            total_delta = total2 - total1
            if total_delta <= 0:
                return 0.0
            return round((1.0 - idle_delta / total_delta) * 100.0, 1)
        except FileNotFoundError:
            logger.debug("system_metrics.cpu.unavailable", reason="/proc/stat not found")
            return 0.0
        except Exception as exc:
            logger.warning("system_metrics.cpu.error", error=str(exc))
            return 0.0

    @staticmethod
    def _parse_proc_stat() -> tuple[float, float]:
        """Parse the first line of /proc/stat and return (idle, total) jiffies."""
        with open("/proc/stat") as f:
            line = f.readline()
        # cpu  user nice system idle iowait irq softirq steal guest guest_nice
        parts = line.split()
        values = [float(v) for v in parts[1:]]
        idle = values[3] + values[4]  # idle + iowait
        total = sum(values)
        return idle, total

    @staticmethod
    async def _read_memory() -> tuple[float, float, float]:
        """Read host memory from /proc/meminfo. Returns (used_mb, total_mb, percent)."""
        try:
            total, available = await asyncio.to_thread(SystemMetricsService._parse_proc_meminfo)
            used = total - available
            percent = round((used / total) * 100.0, 1) if total > 0 else 0.0
            return (round(used / 1024, 1), round(total / 1024, 1), percent)
        except FileNotFoundError:
            logger.debug("system_metrics.memory.unavailable", reason="/proc/meminfo not found")
            # macOS fallback: os.sysconf for total only
            try:
                import os

                total_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
                total_mb = round(total_bytes / (1024 * 1024), 1)
                return (0.0, total_mb, 0.0)
            except (ValueError, OSError):
                return (0.0, 0.0, 0.0)
        except Exception as exc:
            logger.warning("system_metrics.memory.error", error=str(exc))
            return (0.0, 0.0, 0.0)

    @staticmethod
    def _parse_proc_meminfo() -> tuple[float, float]:
        """Parse /proc/meminfo and return (total_kb, available_kb)."""
        total_kb = 0.0
        available_kb = 0.0
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total_kb = float(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    available_kb = float(line.split()[1])
                    break
        return total_kb, available_kb

    @staticmethod
    def _read_disk() -> tuple[float, float, float]:
        """Read disk usage for the root filesystem. Returns (used_gb, total_gb, percent)."""
        import shutil

        try:
            usage = shutil.disk_usage("/")
            total_gb = round(usage.total / (1024**3), 1)
            used_gb = round(usage.used / (1024**3), 1)
            percent = round((usage.used / usage.total) * 100.0, 1) if usage.total > 0 else 0.0
            return (used_gb, total_gb, percent)
        except Exception as exc:
            logger.warning("system_metrics.disk.error", error=str(exc))
            return (0.0, 0.0, 0.0)

    @staticmethod
    def _read_gpu() -> dict:
        """Read NVIDIA GPU metrics via Docker API exec into a GPU container.

        The API container doesn't have nvidia-smi or the docker CLI, but
        has the Docker socket mounted. Uses aiodocker (sync wrapper) to
        exec into the Ollama container which has GPU access.
        """
        import subprocess

        # Try local nvidia-smi first (works if API has direct GPU access)
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                line = result.stdout.strip().split("\n")[0]
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 5:
                    return {
                        "name": parts[0],
                        "utilization": float(parts[1]),
                        "memory_used": float(parts[2]),
                        "memory_total": float(parts[3]),
                        "temperature": float(parts[4]),
                    }
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        except Exception:
            pass

        # Fallback: exec into GPU container via Docker socket + aiodocker
        try:
            import asyncio

            return asyncio.run(SystemMetricsService._read_gpu_via_docker())
        except Exception:
            return {}

    @staticmethod
    async def _read_gpu_via_docker() -> dict:
        """Exec nvidia-smi inside a GPU container via the Docker socket."""
        import aiodocker

        docker = aiodocker.Docker()
        try:
            containers = await docker.containers.list(
                filters={"name": ["nexus-ollama-1"]},
            )
            if not containers:
                return {}
            container = containers[0]
            exec_obj = await container.exec(
                cmd=[
                    "nvidia-smi",
                    "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
            )
            stream = exec_obj.start()
            output = b""
            async for chunk in stream:
                output += chunk
            line = output.decode().strip().split("\n")[0]
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 5:
                return {}
            return {
                "name": parts[0],
                "utilization": float(parts[1]),
                "memory_used": float(parts[2]),
                "memory_total": float(parts[3]),
                "temperature": float(parts[4]),
            }
        finally:
            await docker.close()
