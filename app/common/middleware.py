"""ASGI middleware: request IDs, structured logging, CORS configuration."""

import time
import uuid

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
        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id)
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
            request_id = getattr(request.state, "request_id", "unknown")
            status = response.status_code if response else 500
            logger.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=status,
                duration_ms=elapsed_ms,
                request_id=request_id,
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
