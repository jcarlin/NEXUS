"""ASGI middleware: request IDs, structured logging, audit logging, CORS configuration."""

import time
import uuid
from uuid import UUID

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Request-ID middleware
# ---------------------------------------------------------------------------


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Injects a unique X-Request-ID into every request/response cycle."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        session_id = request.headers.get("X-Session-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        request.state.session_id = session_id
        structlog.contextvars.bind_contextvars(request_id=request_id, session_id=session_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()


# ---------------------------------------------------------------------------
# Request-logging middleware
# ---------------------------------------------------------------------------


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs method, path, status code, and duration for every request using structlog."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            status = response.status_code if response else 500
            logger.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=status,
                duration_ms=elapsed_ms,
            )


# ---------------------------------------------------------------------------
# CORS helper
# ---------------------------------------------------------------------------


def setup_cors(app: FastAPI) -> None:
    """Configure CORS from ``Settings.cors_allowed_origins`` (comma-separated)."""
    from app.dependencies import get_settings

    settings = get_settings()
    origins_str = settings.cors_allowed_origins.strip()
    if origins_str:
        origins = [o.strip() for o in origins_str.split(",") if o.strip()]
    else:
        origins = ["http://localhost:5173", "http://localhost:3000"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ---------------------------------------------------------------------------
# Audit-logging middleware
# ---------------------------------------------------------------------------

# Endpoints to skip for audit logging (noisy / non-business)
_AUDIT_SKIP_PREFIXES = ("/api/v1/health", "/docs", "/openapi.json", "/redoc")


def _derive_resource_type(path: str) -> str | None:
    """Extract the resource type from a URL path like ``/api/v1/documents/...``."""
    parts = path.split("/")
    # /api/v1/{resource_type}/...  → parts = ["", "api", "v1", resource_type, ...]
    if len(parts) >= 4 and parts[1] == "api" and parts[2] == "v1":
        return parts[3]
    return None


def _get_client_ip(request: Request) -> str:
    """Return the client IP, preferring X-Forwarded-For when present."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Records every API call to the ``audit_log`` table in PostgreSQL."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip noisy endpoints
        path = request.url.path
        if any(path.startswith(prefix) for prefix in _AUDIT_SKIP_PREFIXES):
            return await call_next(request)

        start = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            status_code = response.status_code if response else 500
            await self._write_audit_log(request, status_code, elapsed_ms)

    @staticmethod
    async def _write_audit_log(request: Request, status_code: int, duration_ms: float) -> None:
        """Delegate audit log INSERT to AuditService (fire-and-forget)."""
        try:
            from app.audit.service import AuditService
            from app.dependencies import get_session_factory

            user = getattr(request.state, "user", None)
            user_id = user.id if user else None
            user_email = user.email if user else None

            matter_header = request.headers.get("X-Matter-ID")
            matter_id: UUID | None = None
            if matter_header:
                try:
                    matter_id = UUID(matter_header)
                except ValueError:
                    pass  # Invalid UUID in header — store as NULL

            await AuditService.log_request(
                get_session_factory(),
                user_id=user_id,
                user_email=user_email,
                action=request.method,
                resource=str(request.url.path),
                resource_type=_derive_resource_type(str(request.url.path)),
                matter_id=matter_id,
                ip_address=_get_client_ip(request),
                user_agent=request.headers.get("User-Agent"),
                status_code=status_code,
                duration_ms=duration_ms,
                request_id=getattr(request.state, "request_id", None),
                session_id=getattr(request.state, "session_id", None),
            )
        except Exception:
            # Acceptable degradation: audit logging must not block user
            # requests or return errors to the client.
            logger.warning("audit_log.write_failed", exc_info=True)
