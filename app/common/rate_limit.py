"""Redis sliding-window rate limiter for FastAPI endpoints.

Uses sorted sets in Redis to track request timestamps per client IP.
Designed as FastAPI ``Depends()`` callables.  Fails open on Redis errors
(logs a warning but allows the request through).
"""

from __future__ import annotations

import time

import structlog
from fastapi import Depends, HTTPException, Request

from app.config import Settings
from app.dependencies import get_redis, get_settings

logger = structlog.get_logger(__name__)


async def _check_rate_limit(
    request: Request,
    key_prefix: str,
    max_requests: int,
    window_seconds: int = 60,
) -> None:
    """Check and enforce a sliding-window rate limit.

    Uses a Redis sorted set keyed by ``{key_prefix}:{client_ip}``.
    Each request timestamp is scored by its epoch time.  Old entries
    outside the window are pruned, and the current count is checked
    against ``max_requests``.

    Raises ``HTTPException(429)`` with a ``Retry-After`` header when
    the limit is exceeded.  Fails open (allows request) on Redis errors.
    """
    client_ip = request.client.host if request.client else "unknown"
    redis_key = f"ratelimit:{key_prefix}:{client_ip}"
    now = time.time()
    window_start = now - window_seconds

    try:
        redis = get_redis()
        pipe = redis.pipeline()
        # Remove entries older than the window
        pipe.zremrangebyscore(redis_key, "-inf", window_start)
        # Count current entries
        pipe.zcard(redis_key)
        # Add the current request
        pipe.zadd(redis_key, {f"{now}": now})
        # Set expiry on the key to auto-cleanup
        pipe.expire(redis_key, window_seconds + 10)
        results = await pipe.execute()

        current_count = results[1]  # zcard result

        if current_count >= max_requests:
            # Calculate retry-after from the oldest entry in the window
            retry_after = int(window_seconds - (now - window_start)) or 1
            logger.warning(
                "rate_limit.exceeded",
                key=redis_key,
                count=current_count,
                limit=max_requests,
            )
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )
    except HTTPException:
        raise
    except Exception:
        # Fail open: allow the request if Redis is unavailable
        logger.warning("rate_limit.redis_error", key_prefix=key_prefix)


async def rate_limit_queries(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    """Rate limiter dependency for query endpoints."""
    await _check_rate_limit(
        request,
        key_prefix="queries",
        max_requests=settings.rate_limit_queries_per_minute,
        window_seconds=60,
    )


async def rate_limit_ingests(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    """Rate limiter dependency for ingestion endpoints."""
    await _check_rate_limit(
        request,
        key_prefix="ingests",
        max_requests=settings.rate_limit_ingests_per_minute,
        window_seconds=60,
    )


async def rate_limit_login(
    request: Request,
) -> None:
    """Rate limiter dependency for the login endpoint (10 req/min per IP)."""
    await _check_rate_limit(
        request,
        key_prefix="login",
        max_requests=10,
        window_seconds=60,
    )
