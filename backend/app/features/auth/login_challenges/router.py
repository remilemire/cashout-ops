# backend/app/features/auth/login_challenges/router.py

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors.openapi import error_responses
from app.features.users.schemas import UserOut
from app.infrastructure.db.dependencies import get_db
from app.infrastructure.redis import Redis
from app.infrastructure.redis.dependencies import get_redis
from app.security.cookies import set_csrf_cookie, set_session_cookie
from app.security.crypto import generate_secret_token

from ..types import UserWithSessionToken
from . import service as login_challenges_service
from .schemas import (
    LoginChallengeStart,
    LoginChallengeStartOut,
    LoginChallengeVerifyCode,
    LoginChallengeVerifyLink,
    LoginChallengeVerifyLinkOut,
)

# No auth or CSRF dependencies: these routes run before any session exists,
# like the password login they replace.
router = APIRouter(tags=["auth"])


@router.post(
    "/login",
    response_model=LoginChallengeStartOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses=error_responses("VALIDATION_FAILED"),
)
async def start_login(
    payload: LoginChallengeStart,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> LoginChallengeStartOut:
    """Start a passwordless login by emailing a sign-in link.

    Always returns 202 with a challengeId; whether an email was actually sent
    is never revealed (an unknown address gets an indistinguishable decoy).
    For a real account the link is emailed once the request commits, via the
    transactional outbox.
    """
    challenge_id = await login_challenges_service.initiate(
        db, redis, email=payload.email
    )
    return LoginChallengeStartOut(challenge_id=challenge_id)


@router.post(
    "/login/verify-link",
    response_model=LoginChallengeVerifyLinkOut,
    responses=error_responses("LOGIN_CHALLENGE_INVALID", "VALIDATION_FAILED"),
)
async def verify_link(
    payload: LoginChallengeVerifyLink,
    redis: Annotated[Redis, Depends(get_redis)],
) -> LoginChallengeVerifyLinkOut:
    """Verify the emailed link and return the one-time code to display.

    Repeatable — each call supersedes the previous code — and does not
    consume the challenge; sign-in completes via `/login/verify-code`.
    """
    code = await login_challenges_service.verify_link(
        redis, challenge_id=payload.challenge_id, token=payload.token
    )
    return LoginChallengeVerifyLinkOut(code=code)


@router.post(
    "/login/verify-code",
    response_model=UserOut,
    responses=error_responses("LOGIN_CHALLENGE_INVALID", "VALIDATION_FAILED"),
)
async def verify_code(
    response: Response,
    payload: LoginChallengeVerifyCode,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> UserOut:
    """Complete login in the tab that initiated the challenge.

    Sets the `session_token` (HttpOnly) and `csrf_token` (JS-readable)
    cookies. Consumes the challenge — it is single use.
    """
    result = await login_challenges_service.verify_code(
        db, redis, challenge_id=payload.challenge_id, code=payload.code
    )
    return _authenticated_response(response, result)


def _authenticated_response(
    response: Response, result: UserWithSessionToken
) -> UserOut:
    # Private copy of auth.router's helper: importing it from there would be
    # circular (auth.router includes this router).
    set_session_cookie(response, result.session_token)
    set_csrf_cookie(response, generate_secret_token())
    return UserOut.model_validate(result.user)
