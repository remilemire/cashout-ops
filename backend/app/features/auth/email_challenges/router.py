# backend/app/features/auth/email_challenges/router.py

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.errors import error_responses
from app.features.auth.shared import access
from app.features.users.schemas import UserOut
from app.infrastructure.db.dependencies import get_db
from app.infrastructure.redis import Redis
from app.infrastructure.redis.dependencies import get_redis
from app.security.time_floor import time_floor

from . import service as email_challenges_service
from .dependencies import (
    rate_limit_initiate_email,
    rate_limit_initiate_ip,
    rate_limit_verify_code_ip,
    rate_limit_verify_link_challenge,
    rate_limit_verify_link_ip,
)
from .schemas import (
    EmailChallengeStart,
    EmailChallengeStartOut,
    EmailChallengeVerifyCode,
    EmailChallengeVerifyLink,
    EmailChallengeVerifyLinkOut,
)

# No auth or CSRF dependencies: these routes run before any session exists.
# Rate limits are attached per route via the feature's guard dependencies;
# see .dependencies for why each flow pairs per-identifier and per-IP caps.
#
# Every handler pads its work to CHALLENGE_TIME_FLOOR_MS via `time_floor`, so
# response timing cannot reveal whether an address has an account or a
# challenge id is real (the decoy path does far less work than the real one).
# What runs outside the floor cannot leak around it: the rate-limit
# dependencies hash the address before any lookup, so their cost is identical
# either way, and the get_db commit runs in dependency teardown after the
# response is sent.
router = APIRouter(prefix="/email-challenges", tags=["auth"])


@router.post(
    "",
    response_model=EmailChallengeStartOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses=error_responses("VALIDATION_FAILED", "RATE_LIMITED"),
    dependencies=[
        Depends(rate_limit_initiate_email),
        Depends(rate_limit_initiate_ip),
    ],
)
async def start_login(
    payload: EmailChallengeStart,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> EmailChallengeStartOut:
    """Start a passwordless login by emailing a sign-in link.

    Always returns 202 with a challengeId; whether an email was actually sent
    is never revealed (an unknown address gets an indistinguishable decoy).
    For a real account the link is emailed once the request commits, via the
    transactional outbox.
    """
    async with time_floor(settings.auth.CHALLENGE_TIME_FLOOR_MS):
        challenge_id = await email_challenges_service.initiate(
            db, redis, email=payload.email
        )
    return EmailChallengeStartOut(challenge_id=challenge_id)


@router.post(
    "/verify-link",
    response_model=EmailChallengeVerifyLinkOut,
    responses=error_responses(
        "EMAIL_CHALLENGE_INVALID", "VALIDATION_FAILED", "RATE_LIMITED"
    ),
    dependencies=[
        Depends(rate_limit_verify_link_challenge),
        Depends(rate_limit_verify_link_ip),
    ],
)
async def verify_link(
    payload: EmailChallengeVerifyLink,
    redis: Annotated[Redis, Depends(get_redis)],
) -> EmailChallengeVerifyLinkOut:
    """Verify the emailed link and return the one-time code to display.

    Single-use — a second click of the emailed link fails — while the
    challenge survives; sign-in completes via `/email-challenges/verify-code`.
    """
    async with time_floor(settings.auth.CHALLENGE_TIME_FLOOR_MS):
        code = await email_challenges_service.consume_link(
            redis, challenge_id=payload.challenge_id, token=payload.token
        )
    return EmailChallengeVerifyLinkOut(code=code)


# No per-challenge dependency here: the per-challenge budget is the atomic
# MAX_CODE_ATTEMPTS counter in the service.
@router.post(
    "/verify-code",
    response_model=UserOut,
    responses=error_responses(
        "EMAIL_CHALLENGE_INVALID", "VALIDATION_FAILED", "RATE_LIMITED"
    ),
    dependencies=[Depends(rate_limit_verify_code_ip)],
)
async def verify_code(
    response: Response,
    payload: EmailChallengeVerifyCode,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> UserOut:
    """Complete login in the tab that initiated the challenge.

    Sets the `session_token` (HttpOnly) and `csrf_token` (JS-readable)
    cookies. Consumes the challenge — it is single use.
    """
    # The session grant sits inside the floor too, so a successful sign-in
    # and a rejected one are padded to the same shared minimum.
    async with time_floor(settings.auth.CHALLENGE_TIME_FLOOR_MS):
        user = await email_challenges_service.consume_code(
            db, redis, challenge_id=payload.challenge_id, code=payload.code
        )
        await access.grant(redis, response, user_id=user.id)
    return UserOut.model_validate(user)
