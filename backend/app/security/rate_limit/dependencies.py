from __future__ import annotations

from datetime import timedelta

from fastapi import Request

from app.errors import RateLimitedError
from app.infrastructure.redis import Redis

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


def client_ip(request: Request) -> str:
    """The client IP to key per-IP rate limits on."""
    # In production the service runs behind Render's proxy and gunicorn passes
    # --forwarded-allow-ips, so uvicorn has already rewritten request.client
    # from X-Forwarded-For to the real client (see scripts/start.bash).
    # Requests with no client scope share one "unknown" bucket, which is
    # acceptable.
    return "unknown" if request.client is None else request.client.host


__all__ = ["client_ip", "enforce"]
