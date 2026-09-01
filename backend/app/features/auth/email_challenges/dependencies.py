# backend/app/features/auth/email_challenges/dependencies.py

"""Pre-session guards for the passwordless sign-in flow: rate limits and the
timing floor.

These routes run before any session exists, so the usual authenticated
per-user limits do not apply. The per-email guard keys the fixed-window
counter on the address the request itself supplies, throttling targeted
abuse of a single account; the per-IP guards bound total volume from a
single source. The timing floor
(`challenge_time_floor`) pads every response so its timing cannot reveal
whether an address or challenge is real; see the router comment for the
full defense.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import settings
from app.infrastructure.redis import Redis
from app.infrastructure.redis.dependencies import get_redis
from app.security.crypto import hash_secret_token
from app.security.rate_limit import client_ip, enforce
from app.security.time_floor import time_floor

from .schemas import EmailChallengeStart

_HOUR = timedelta(hours=1)


async def challenge_time_floor() -> AsyncIterator[None]:
    """Pad every email-challenge response to CHALLENGE_TIME_FLOOR_MS.

    Declared router-wide with scope="function": router-level dependencies are
    solved before endpoint parameters, so this is entered before every other
    dependency and — teardown being LIFO within the function stack — pads
    after the DbSession commit but before the response is sent. The commit's
    cost therefore lands inside the padded window, and the pad completes
    before any byte leaves. The floor is read at request time so tests can
    patch it.
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
    # Keyed on the hashed, lowercased address BEFORE any user lookup, so real
    # and unknown emails 429 identically (no enumeration signal) and no PII
    # reaches Redis keys.
    await enforce(
        redis,
        scope="auth_initiate_email",
        identifier=hash_secret_token(payload.email.lower()),
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
