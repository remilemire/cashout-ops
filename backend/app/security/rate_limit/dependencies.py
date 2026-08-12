# backend/app/security/rate_limit/dependencies.py

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request

from app.errors import RateLimitedError
from app.infrastructure.redis import Redis
from app.infrastructure.redis.dependencies import get_redis

from . import store


async def enforce(
    redis: Redis, *, scope: str, identifier: str, limit: int, window: timedelta
) -> None:
    """Count one hit against ``{scope}:{identifier}``; raise once over limit."""
    hit = await store.count_hit(
        redis, scope=scope, identifier=identifier, window=window
    )

    if hit.count > limit:
        raise RateLimitedError(hit.retry_after_seconds)


def _client_ip(request: Request) -> str:
    # In production the service runs behind Render's proxy and gunicorn passes
    # --forwarded-allow-ips, so uvicorn has already rewritten request.client
    # from X-Forwarded-For to the real client (see scripts/start.bash).
    # Requests with no client scope share one "unknown" bucket, which is
    # acceptable.
    return "unknown" if request.client is None else request.client.host


def rate_limit_ip(
    scope: str, *, limit: int, window: timedelta
) -> Callable[[Request, Redis], Awaitable[None]]:
    """A FastAPI dependency enforcing a per-client-IP limit on ``scope``.

    The limit is captured when the router module imports — env-configured
    like every other setting, not monkeypatch-able in tests.
    """

    async def dependency(
        request: Request, redis: Annotated[Redis, Depends(get_redis)]
    ) -> None:
        await enforce(
            redis,
            scope=scope,
            identifier=_client_ip(request),
            limit=limit,
            window=window,
        )

    return dependency


__all__ = ["enforce", "rate_limit_ip"]
