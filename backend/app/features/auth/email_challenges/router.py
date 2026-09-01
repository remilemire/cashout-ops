# backend/app/features/auth/email_challenges/router.py

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.errors import error_responses
from app.features.auth.shared import access
from app.features.users.schemas import UserOut
from app.infrastructure.db.dependencies import DbSession
from app.infrastructure.redis import Redis
from app.infrastructure.redis.dependencies import get_redis

from . import service as email_challenges_service
from .dependencies import (
    challenge_time_floor,
    rate_limit_initiate_email,
    rate_limit_initiate_ip,
    rate_limit_verify_code_ip,
)
from .schemas import (
    EmailChallengeStart,
    EmailChallengeStartOut,
    EmailChallengeVerifyCode,
)

# No auth or CSRF dependencies: these routes run before any session exists.
# Rate limits are attached per route via the feature's guard dependencies;
# see .dependencies for how the per-email and per-IP caps divide the work.
#
# Every response is padded to CHALLENGE_TIME_FLOOR_MS by the router-wide
# `challenge_time_floor` dependency, so response timing cannot reveal whether
# an address has an account or a challenge id is real (the decoy path does
# far less work than the real one). Function-scoped and solved first, the
# floor brackets everything account-dependent: rate limiting, body-field
# validation, the handler, response serialization, and — because teardown is
# LIFO and the session is `DbSession` — the pre-response commit, whose cost
# differs between the real and decoy paths. Error responses (429, field
# 422s, rejected challenges) unwind through the floor and are padded too.
# The one unpadded path is a malformed-JSON body, rejected before
# dependencies run — identical for real and decoy input, since nothing
# account-dependent has executed by then.
#
# Committing before the response also means a commit failure surfaces as an
# error instead of hiding behind an already-sent 202/200: the outbox insert
# and the owner bootstrap flush in-request, but the COMMIT itself only
# happens in the session teardown. The floor must therefore exceed the real
# path's tail including the commit; see CHALLENGE_TIME_FLOOR_MS.
router = APIRouter(
    prefix="/email-challenges",
    tags=["auth"],
    dependencies=[Depends(challenge_time_floor, scope="function")],
)


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
    db: DbSession,
    redis: Annotated[Redis, Depends(get_redis)],
) -> EmailChallengeStartOut:
    """Start a passwordless login by emailing a 6-digit sign-in code.

    Always returns 202 with a challengeId; whether an email was actually sent
    is never revealed (an unknown address gets an indistinguishable decoy).
    For a real account the code is emailed once the request commits, via the
    transactional outbox.
    """
    challenge_id = await email_challenges_service.initiate(
        db, redis, email=payload.email
    )
    return EmailChallengeStartOut(challenge_id=challenge_id)


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
    db: DbSession,
    redis: Annotated[Redis, Depends(get_redis)],
) -> UserOut:
    """Complete login in the tab that initiated the challenge.

    Sets the `session_token` (HttpOnly) and `csrf_token` (JS-readable)
    cookies. Consumes the challenge — it is single use.
    """
    # The router-wide floor covers the session grant too, so a successful
    # sign-in and a rejected one are padded to the same shared minimum.
    user = await email_challenges_service.consume_code(
        db, redis, challenge_id=payload.challenge_id, code=payload.code
    )
    await access.grant(redis, response, user_id=user.id)
    return UserOut.model_validate(user)
