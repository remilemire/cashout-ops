# backend/app/features/auth/email_challenges/router.py

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors.openapi import error_responses
from app.features.auth.shared.sessions.cookies import set_session_cookie
from app.features.auth.types import UserWithSessionToken
from app.features.users.schemas import UserOut
from app.infrastructure.db.dependencies import get_db
from app.infrastructure.redis import Redis
from app.infrastructure.redis.dependencies import get_redis
from app.security.crypto import generate_secret_token
from app.security.csrf import set_csrf_cookie

from . import service as email_challenges_service
from .schemas import (
    EmailChallengeStart,
    EmailChallengeStartOut,
    EmailChallengeVerifyCode,
    EmailChallengeVerifyLink,
    EmailChallengeVerifyLinkOut,
)

# No auth or CSRF dependencies: these routes run before any session exists.
router = APIRouter(prefix="/email-challenges", tags=["auth"])


@router.post(
    "",
    response_model=EmailChallengeStartOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses=error_responses("VALIDATION_FAILED"),
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
    challenge_id = await email_challenges_service.initiate(
        db, redis, email=payload.email
    )
    return EmailChallengeStartOut(challenge_id=challenge_id)


@router.post(
    "/verify-link",
    response_model=EmailChallengeVerifyLinkOut,
    responses=error_responses("EMAIL_CHALLENGE_INVALID", "VALIDATION_FAILED"),
)
async def verify_link(
    payload: EmailChallengeVerifyLink,
    redis: Annotated[Redis, Depends(get_redis)],
) -> EmailChallengeVerifyLinkOut:
    """Verify the emailed link and return the one-time code to display.

    Repeatable — each call supersedes the previous code — and does not
    consume the challenge; sign-in completes via `/email-challenges/verify-code`.
    """
    code = await email_challenges_service.verify_link(
        redis, challenge_id=payload.challenge_id, token=payload.token
    )
    return EmailChallengeVerifyLinkOut(code=code)


@router.post(
    "/verify-code",
    response_model=UserOut,
    responses=error_responses("EMAIL_CHALLENGE_INVALID", "VALIDATION_FAILED"),
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
    result = await email_challenges_service.verify_code(
        db, redis, challenge_id=payload.challenge_id, code=payload.code
    )
    return _authenticated_response(response, result)


def _authenticated_response(
    response: Response, result: UserWithSessionToken
) -> UserOut:
    # Completes sign-in at the HTTP boundary: sets the session and CSRF
    # cookies alongside the authenticated user payload.
    set_session_cookie(response, result.session_token)
    set_csrf_cookie(response, generate_secret_token())
    return UserOut.model_validate(result.user)
