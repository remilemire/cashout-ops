# backend/app/features/auth/email_challenges/dependencies.py

"""Pre-session rate-limit guards for the passwordless sign-in flow.

These routes run before any session exists, so the usual authenticated
per-user limits do not apply. The per-identifier guards key the fixed-window
counter on the identifier the request itself supplies (email address or
challenge id), throttling targeted abuse of a single account or challenge;
the per-IP guards bound total volume from a single source.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import settings
from app.infrastructure.redis import Redis
from app.infrastructure.redis.dependencies import get_redis
from app.security.crypto import hash_secret_token
from app.security.rate_limit import client_ip, enforce

from .schemas import EmailChallengeStart, EmailChallengeVerifyLink

_HOUR = timedelta(hours=1)

# Link verifications allowed per challenge before 429 (window = challenge
# TTL). An invariant of the protocol shape, like MAX_CODE_ATTEMPTS — not a
# tuning knob.
MAX_LINK_ATTEMPTS = 10


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


async def rate_limit_verify_link_challenge(
    # `payload` naming is load-bearing — see rate_limit_initiate_email.
    payload: EmailChallengeVerifyLink,
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    """Cap link verifications per challenge for the challenge's lifetime."""
    await enforce(
        redis,
        scope="auth_verify_link_challenge",
        identifier=payload.challenge_id,
        limit=MAX_LINK_ATTEMPTS,
        window=timedelta(minutes=settings.auth.CHALLENGE_TTL_MINUTES),
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


async def rate_limit_verify_link_ip(
    request: Request,
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    """Cap link verifications per client IP."""
    await enforce(
        redis,
        scope="auth_verify_link_ip",
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
    "MAX_LINK_ATTEMPTS",
    "rate_limit_initiate_email",
    "rate_limit_initiate_ip",
    "rate_limit_verify_code_ip",
    "rate_limit_verify_link_challenge",
    "rate_limit_verify_link_ip",
]
