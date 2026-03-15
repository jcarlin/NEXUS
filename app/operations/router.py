"""FastAPI router for service operations management (admin-only)."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.auth.middleware import require_role
from app.auth.schemas import UserRecord
from app.config import Settings
from app.dependencies import get_db, get_settings
from app.operations.schemas import (
    CeleryOverview,
    ContainerActionRequest,
    ContainerActionResponse,
    ContainerListResponse,
    ContainerLogsResponse,
    DependencyGraphResponse,
    UptimeListResponse,
)
from app.operations.service import CeleryService, DockerService, UptimeService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/operations", tags=["admin", "operations"])


async def _docker_call(coro):
    """Execute a Docker API call, raising 503 on connection failure."""
    try:
        return await coro
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("docker.call.failed", error=str(exc))
        raise HTTPException(
            status_code=503,
            detail="Docker daemon is unavailable. Ensure Docker is running.",
        ) from exc


# ---------------------------------------------------------------------------
# Dependency providers
# ---------------------------------------------------------------------------


async def get_docker_client(settings: Settings = Depends(get_settings)) -> Any:
    """Yield an aiodocker.Docker client, closing it after the request."""
    try:
        import aiodocker
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Docker management unavailable (aiodocker not installed).",
        )
    client = None
    try:
        client = aiodocker.Docker(url=f"unix://{settings.docker_socket_path}")
        yield client
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Docker daemon is unavailable. Ensure Docker is running.",
        ) from exc
    finally:
        if client:
            await client.close()


def get_celery_app() -> Any:
    """Return the shared Celery application instance."""
    from workers.celery_app import celery_app

    return celery_app


# ---------------------------------------------------------------------------
# Docker container endpoints
# ---------------------------------------------------------------------------


@router.get("/containers", response_model=ContainerListResponse)
async def list_containers(
    _user: UserRecord = Depends(require_role("admin")),
    docker: Any = Depends(get_docker_client),
    settings: Settings = Depends(get_settings),
) -> ContainerListResponse:
    """List all Docker containers in the NEXUS compose project."""
    containers = await _docker_call(DockerService.list_containers(docker, settings.docker_compose_project))
    return ContainerListResponse(containers=containers)


@router.post("/containers/{name}/action", response_model=ContainerActionResponse)
async def container_action(
    name: str,
    request: ContainerActionRequest,
    _user: UserRecord = Depends(require_role("admin")),
    docker: Any = Depends(get_docker_client),
    settings: Settings = Depends(get_settings),
) -> ContainerActionResponse:
    """Perform an action (restart/stop/start) on a Docker container."""
    project = settings.docker_compose_project
    if request.action == "restart":
        return await _docker_call(DockerService.restart_container(docker, name, project))
    if request.action == "stop":
        return await _docker_call(DockerService.stop_container(docker, name, project))
    if request.action == "start":
        return await _docker_call(DockerService.start_container(docker, name, project))
    raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")


@router.get("/containers/{name}/logs", response_model=ContainerLogsResponse)
async def get_container_logs(
    name: str,
    tail: int = Query(default=500, ge=1, le=10000),
    _user: UserRecord = Depends(require_role("admin")),
    docker: Any = Depends(get_docker_client),
    settings: Settings = Depends(get_settings),
) -> ContainerLogsResponse:
    """Get recent log lines from a Docker container."""
    return await _docker_call(
        DockerService.get_container_logs(docker, name, settings.docker_compose_project, tail=tail)
    )


@router.get("/containers/{name}/logs/stream")
async def stream_container_logs(
    name: str,
    tail: int = Query(default=100, ge=1, le=10000),
    _user: UserRecord = Depends(require_role("admin")),
    docker: Any = Depends(get_docker_client),
    settings: Settings = Depends(get_settings),
) -> EventSourceResponse:
    """Stream container logs via Server-Sent Events."""
    # Validate Docker connectivity before opening SSE stream
    await _docker_call(DockerService.list_containers(docker, settings.docker_compose_project))

    async def _event_generator():
        async for line in DockerService.stream_container_logs(docker, name, settings.docker_compose_project, tail=tail):
            yield {"data": line}

    return EventSourceResponse(_event_generator())


# ---------------------------------------------------------------------------
# Celery endpoints
# ---------------------------------------------------------------------------


@router.get("/celery", response_model=CeleryOverview)
async def celery_overview(
    _user: UserRecord = Depends(require_role("admin")),
    celery_app: Any = Depends(get_celery_app),
) -> CeleryOverview:
    """Get an overview of Celery workers, queues, and active tasks."""
    return await CeleryService.get_workers_overview(celery_app)


@router.post("/celery/workers/{hostname}/restart")
async def restart_worker(
    hostname: str,
    _user: UserRecord = Depends(require_role("admin")),
    celery_app: Any = Depends(get_celery_app),
) -> dict[str, str]:
    """Restart the worker pool for a given hostname."""
    return await CeleryService.pool_restart(celery_app, hostname)


@router.post("/celery/workers/{hostname}/shutdown")
async def shutdown_worker(
    hostname: str,
    _user: UserRecord = Depends(require_role("admin")),
    celery_app: Any = Depends(get_celery_app),
) -> dict[str, str]:
    """Shutdown a Celery worker by hostname."""
    return await CeleryService.shutdown_worker(celery_app, hostname)


@router.post("/celery/queues/{name}/purge")
async def purge_queue(
    name: str,
    _user: UserRecord = Depends(require_role("admin")),
    celery_app: Any = Depends(get_celery_app),
) -> dict[str, Any]:
    """Purge all messages from a Celery queue."""
    return await CeleryService.purge_queue(celery_app, name)


@router.post("/celery/tasks/{task_id}/revoke")
async def revoke_task(
    task_id: str,
    terminate: bool = Query(default=False),
    _user: UserRecord = Depends(require_role("admin")),
    celery_app: Any = Depends(get_celery_app),
) -> dict[str, Any]:
    """Revoke (and optionally terminate) a Celery task."""
    return await CeleryService.revoke_task(celery_app, task_id, terminate=terminate)


# ---------------------------------------------------------------------------
# Dependency graph
# ---------------------------------------------------------------------------


@router.get("/dependencies", response_model=DependencyGraphResponse)
async def dependency_graph(
    _user: UserRecord = Depends(require_role("admin")),
    docker: Any = Depends(get_docker_client),
    settings: Settings = Depends(get_settings),
) -> DependencyGraphResponse:
    """Get the Docker Compose service dependency graph."""
    return await _docker_call(DockerService.get_dependency_graph(docker, settings.docker_compose_project))


# ---------------------------------------------------------------------------
# Uptime
# ---------------------------------------------------------------------------


@router.get("/uptime", response_model=UptimeListResponse)
async def uptime_summaries(
    _user: UserRecord = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> UptimeListResponse:
    """Get uptime summaries for all backing services (24h, 7d, 30d)."""
    return await UptimeService.get_uptime_summaries(db)
