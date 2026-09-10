"""Pre-session rate-limit guards for the OAuth sign-in flow.

These routes run before any session exists, so only per-IP caps apply; the
flow's own single-use consumption and state check bound per-flow abuse.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import settings
from app.infrastructure.redis import Redis
from app.infrastructure.redis.dependencies import get_redis
from app.security.rate_limit import client_ip, enforce

_HOUR = timedelta(hours=1)


async def rate_limit_oauth_start_ip(
    request: Request,
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    """Cap flow starts per client IP."""
    await enforce(
        redis,
        scope="auth_oauth_start_ip",
        identifier=client_ip(request),
        limit=settings.rate_limit.AUTH_IP_PER_HOUR,
        window=_HOUR,
    )


async def rate_limit_oauth_callback_ip(
    request: Request,
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    """Cap callback attempts per client IP."""
    await enforce(
        redis,
        scope="auth_oauth_callback_ip",
        identifier=client_ip(request),
        limit=settings.rate_limit.AUTH_IP_PER_HOUR,
        window=_HOUR,
    )


__all__ = ["rate_limit_oauth_start_ip", "rate_limit_oauth_callback_ip"]
