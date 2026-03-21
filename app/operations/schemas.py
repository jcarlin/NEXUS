"""Pydantic schemas for service operations management."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ContainerStatus(StrEnum):
    RUNNING = "running"
    STOPPED = "stopped"
    RESTARTING = "restarting"
    PAUSED = "paused"
    EXITED = "exited"
    DEAD = "dead"
    CREATED = "created"


class ContainerHealthStatus(StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    NONE = "none"


class ContainerStats(BaseModel):
    cpu_percent: float = 0.0
    memory_usage_mb: float = 0.0
    memory_limit_mb: float = 0.0
    memory_percent: float = 0.0


class SystemMetrics(BaseModel):
    """Host-level CPU, memory, and disk usage."""

    cpu_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    memory_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    disk_percent: float = 0.0


class ContainerInfo(BaseModel):
    container_id: str
    name: str
    service_name: str
    image: str
    status: ContainerStatus
    health: ContainerHealthStatus = ContainerHealthStatus.NONE
    uptime_seconds: int = 0
    started_at: datetime | None = None
    stats: ContainerStats | None = None
    ports: list[str] = Field(default_factory=list)


class ContainerListResponse(BaseModel):
    containers: list[ContainerInfo]


class ContainerActionRequest(BaseModel):
    action: str = Field(..., pattern="^(restart|stop|start)$")


class ContainerActionResponse(BaseModel):
    container_name: str
    action: str
    success: bool
    message: str


class ContainerLogsResponse(BaseModel):
    container_name: str
    lines: list[str]


class CeleryWorkerInfo(BaseModel):
    hostname: str
    status: str  # "online" | "offline"
    active_tasks: int = 0
    processed: int = 0
    concurrency: int = 0
    queues: list[str] = Field(default_factory=list)
    uptime_seconds: int = 0
    pid: int | None = None


class CeleryTaskInfo(BaseModel):
    task_id: str
    name: str
    args: str = ""
    kwargs: str = ""
    started_at: float | None = None
    worker: str = ""
    queue: str = ""


class CeleryQueueInfo(BaseModel):
    name: str
    active_count: int = 0
    reserved_count: int = 0
    scheduled_count: int = 0


class CeleryOverview(BaseModel):
    workers: list[CeleryWorkerInfo] = Field(default_factory=list)
    queues: list[CeleryQueueInfo] = Field(default_factory=list)
    active_tasks: list[CeleryTaskInfo] = Field(default_factory=list)


class ServiceDependency(BaseModel):
    service: str
    depends_on: list[str] = Field(default_factory=list)
    status: str = "unknown"
    health: str = "unknown"


class DependencyGraphResponse(BaseModel):
    nodes: list[ServiceDependency]


class UptimeRecord(BaseModel):
    service_name: str
    status: str
    latency_ms: int | None = None
    checked_at: datetime


class UptimeSummary(BaseModel):
    service_name: str
    uptime_24h: float = 0.0
    uptime_7d: float = 0.0
    uptime_30d: float = 0.0
    total_checks_24h: int = 0
    total_checks_7d: int = 0
    total_checks_30d: int = 0


class UptimeListResponse(BaseModel):
    services: list[UptimeSummary]
