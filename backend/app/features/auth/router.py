# backend/app/features/auth/router.py

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors.openapi import error_responses
from app.features.users.schemas import UserOut
from app.infrastructure.db.dependencies import get_db
from app.infrastructure.redis import Redis
from app.infrastructure.redis.dependencies import get_redis
from app.security.cookies import (
    clear_csrf_cookie,
    clear_session_cookie,
    get_session_cookie,
    set_csrf_cookie,
    set_session_cookie,
)
from app.security.crypto import generate_secret_token

from . import service as auth_service
from .email_verification.router import router as email_verification_router
from .schemas import AuthLogin, AuthRegister
from .types import UserWithSessionToken

router = APIRouter(prefix="/auth", tags=["auth"])

# Email verification lives under /auth (e.g. /auth/email-verification/verify).
router.include_router(email_verification_router)


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(
        "EMAIL_TAKEN", "INVITATION_REQUIRED", "VALIDATION_FAILED"
    ),
)
async def register(
    response: Response,
    payload: AuthRegister,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> UserOut:
    """Create an account and start a session.

    Sets the `session_token` (HttpOnly) and `csrf_token` (JS-readable) cookies.
    Registration requires a pending invitation for the email; the invitation is
    marked accepted. The email matching `ADMIN_EMAIL` is exempt and is created
    as an admin. A verification code is emailed once the request commits (via
    the transactional outbox); the account stays unverified until it's
    confirmed.
    """
    result = await auth_service.register(db, redis, payload=payload)
    return _authenticated_response(response, result)


@router.post(
    "/login",
    response_model=UserOut,
    responses=error_responses("INVALID_CREDENTIALS", "VALIDATION_FAILED"),
)
async def login(
    response: Response,
    payload: AuthLogin,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> UserOut:
    """Authenticate with email and password.

    Sets the `session_token` (HttpOnly) and `csrf_token` (JS-readable) cookies.
    """
    result = await auth_service.login(db, redis, payload=payload)
    return _authenticated_response(response, result)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    """End the current session and clear the auth cookies.

    Best-effort and unauthenticated: a missing or already-invalid session still
    clears the cookies and returns 204 rather than erroring.
    """
    session_token = get_session_cookie(request)
    if session_token is not None:
        await auth_service.logout(redis, session_token=session_token)

    clear_session_cookie(response)
    clear_csrf_cookie(response)


def _authenticated_response(
    response: Response, result: UserWithSessionToken
) -> UserOut:
    set_session_cookie(response, result.session_token)
    set_csrf_cookie(response, generate_secret_token())
    return UserOut.model_validate(result.user)
