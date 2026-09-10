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

# Sign-in needs no existing session. Per-route guards enforce rate limits.
# The function-scoped timing floor must run first so it unwinds after the
# database commit and before the response is sent (see .dependencies).
# Padding mitigates timing differences only below the configured floor;
# malformed JSON is rejected before dependencies run.
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
    """Start sign-in by queuing delivery of a six-digit code to an eligible address.

    Successful requests return 202 with a challengeId for both real and unknown
    addresses. Unknown addresses receive a decoy id and no email. Validation,
    rate-limit, and infrastructure failures can still return errors.
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
    """Consume a challenge id and code, then set the authentication cookies.

    Sets `session_token` (HttpOnly) and `csrf_token` (JS-readable). The
    challenge is single use; verification does not require the initiating tab.
    """
    # The router-wide floor covers the session grant too, so a successful
    # sign-in and a rejected one are padded to the same shared minimum.
    user = await email_challenges_service.consume_code(
        db, redis, challenge_id=payload.challenge_id, code=payload.code
    )
    await access.grant(redis, response, user_id=user.id)
    return UserOut.model_validate(user)
