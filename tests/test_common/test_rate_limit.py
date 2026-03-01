"""Tests for the Redis sliding-window rate limiter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _make_mock_redis(zcard_count: int, *, raise_on_execute: Exception | None = None):
    """Create a mock Redis client with a pipeline that returns the given zcard count."""
    mock_pipe = MagicMock()
    # pipeline methods return self for chaining
    mock_pipe.zremrangebyscore.return_value = mock_pipe
    mock_pipe.zcard.return_value = mock_pipe
    mock_pipe.zadd.return_value = mock_pipe
    mock_pipe.expire.return_value = mock_pipe

    if raise_on_execute:
        mock_pipe.execute = AsyncMock(side_effect=raise_on_execute)
    else:
        mock_pipe.execute = AsyncMock(
            return_value=[
                None,  # zremrangebyscore
                zcard_count,  # zcard
                None,  # zadd
                None,  # expire
            ]
        )

    mock_redis = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe
    return mock_redis


def _make_mock_request(ip: str = "127.0.0.1"):
    mock_request = MagicMock()
    mock_request.client.host = ip
    return mock_request


@pytest.mark.asyncio
async def test_rate_limit_allows_under_limit():
    """Requests under the limit should pass through without error."""
    mock_redis = _make_mock_redis(zcard_count=5)
    mock_request = _make_mock_request()

    with patch("app.common.rate_limit.get_redis", return_value=mock_redis):
        from app.common.rate_limit import _check_rate_limit

        await _check_rate_limit(mock_request, "queries", max_requests=30)


@pytest.mark.asyncio
async def test_rate_limit_blocks_over_limit():
    """Requests over the limit should raise 429."""
    mock_redis = _make_mock_redis(zcard_count=30)
    mock_request = _make_mock_request()

    with patch("app.common.rate_limit.get_redis", return_value=mock_redis):
        from app.common.rate_limit import _check_rate_limit

        with pytest.raises(HTTPException) as exc_info:
            await _check_rate_limit(mock_request, "queries", max_requests=30)

        assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_includes_retry_after():
    """The 429 response should include a Retry-After header."""
    mock_redis = _make_mock_redis(zcard_count=30)
    mock_request = _make_mock_request()

    with patch("app.common.rate_limit.get_redis", return_value=mock_redis):
        from app.common.rate_limit import _check_rate_limit

        with pytest.raises(HTTPException) as exc_info:
            await _check_rate_limit(mock_request, "queries", max_requests=30)

        assert "Retry-After" in exc_info.value.headers


@pytest.mark.asyncio
async def test_rate_limit_fails_open_on_redis_error():
    """Redis errors should fail open (allow the request)."""
    mock_redis = _make_mock_redis(zcard_count=0, raise_on_execute=ConnectionError("Redis down"))
    mock_request = _make_mock_request()

    with patch("app.common.rate_limit.get_redis", return_value=mock_redis):
        from app.common.rate_limit import _check_rate_limit

        # Should NOT raise — fail open
        await _check_rate_limit(mock_request, "queries", max_requests=30)


# ---------------------------------------------------------------------------
# Edge-case tests (Sprint 8 L4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limiter_redis_unavailable_raises():
    """When get_redis() itself raises, the rate limiter should fail open (current behavior).

    The rate limiter catches all non-HTTPException errors and allows the
    request through. This test verifies that a ConnectionError from
    get_redis() does not crash the endpoint.
    """
    mock_request = _make_mock_request()

    with patch(
        "app.common.rate_limit.get_redis",
        side_effect=ConnectionError("Cannot connect to Redis"),
    ):
        from app.common.rate_limit import _check_rate_limit

        # Should NOT raise — fail open
        await _check_rate_limit(mock_request, "queries", max_requests=30)


@pytest.mark.asyncio
async def test_rate_limiter_zero_remaining_returns_429():
    """When all tokens are consumed (count == max_requests), the next request gets HTTP 429."""
    # Set zcard_count equal to max_requests (exactly at the boundary)
    mock_redis = _make_mock_redis(zcard_count=10)
    mock_request = _make_mock_request()

    with patch("app.common.rate_limit.get_redis", return_value=mock_redis):
        from app.common.rate_limit import _check_rate_limit

        with pytest.raises(HTTPException) as exc_info:
            await _check_rate_limit(mock_request, "queries", max_requests=10)

        assert exc_info.value.status_code == 429
        assert "Retry-After" in exc_info.value.headers
