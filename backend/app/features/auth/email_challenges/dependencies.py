"""Pre-session rate limits and response timing mitigation for email sign-in.

Per-email limits bound requests targeting an address; per-IP limits bound
requests from a source. The timing floor reduces differences between real
and decoy paths when their work finishes below the configured minimum.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import settings
from app.infrastructure.redis import Redis
from app.infrastructure.redis.dependencies import get_redis
from app.security.rate_limit import client_ip, enforce
from app.security.time_floor import time_floor

from .schemas import EmailChallengeStart
from .service import email_key

_HOUR = timedelta(hours=1)


async def challenge_time_floor() -> AsyncIterator[None]:
    """Pad the request's work to CHALLENGE_TIME_FLOOR_MS before sending a response.

    Declare this first on the router with function scope, like `DbSession`.
    Dependencies unwind in reverse order, so the database commit is included
    in the padded interval. Requests exceeding the floor receive no padding;
    malformed JSON is rejected before dependencies run.
    """
    async with time_floor(settings.auth.CHALLENGE_TIME_FLOOR_MS):
        yield


async def rate_limit_initiate_email(
    # The parameter MUST stay named `payload`: FastAPI merges body params
    # across the dependency tree by name, so this shares one parse with the
    # route handler; renaming it would embed the body under a sub-key and
    # 422 every request.
    payload: EmailChallengeStart,
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    """Cap challenge initiations per email address."""
    # Keyed BEFORE any user lookup, so real and unknown emails 429 identically
    # (no enumeration signal). `email_key` is shared with the challenge
    # pointer so one address cannot end up spread over two buckets by a
    # normalization difference.
    await enforce(
        redis,
        scope="auth_initiate_email",
        identifier=email_key(payload.email),
        limit=settings.rate_limit.INITIATE_EMAIL_PER_HOUR,
        window=_HOUR,
    )


async def rate_limit_initiate_ip(
    request: Request,
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    """Cap challenge initiations per client IP."""
    await enforce(
        redis,
        scope="auth_initiate_ip",
        identifier=client_ip(request),
        limit=settings.rate_limit.AUTH_IP_PER_HOUR,
        window=_HOUR,
    )


async def rate_limit_verify_code_ip(
    request: Request,
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    """Cap code verifications per client IP."""
    await enforce(
        redis,
        scope="auth_verify_code_ip",
        identifier=client_ip(request),
        limit=settings.rate_limit.AUTH_IP_PER_HOUR,
        window=_HOUR,
    )


__all__ = [
    "challenge_time_floor",
    "rate_limit_initiate_email",
    "rate_limit_initiate_ip",
    "rate_limit_verify_code_ip",
]
