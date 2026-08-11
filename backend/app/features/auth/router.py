# backend/app/features/auth/router.py

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.infrastructure.redis import Redis
from app.infrastructure.redis.dependencies import get_redis
from app.security.cookies import (
    clear_csrf_cookie,
    clear_session_cookie,
    get_session_cookie,
)

from . import service as auth_service
from .email_challenges.router import router as email_challenges_router

router = APIRouter(prefix="/auth", tags=["auth"])

# Passwordless login lives under /auth (e.g. /auth/email-challenges/verify-code).
router.include_router(email_challenges_router)


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
