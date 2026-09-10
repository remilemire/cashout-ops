from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.errors import AppError
from app.features.auth.sessions import service as sessions_service
from app.features.auth.sessions.cookies import get_session_cookie
from app.features.auth.sessions.model import Session
from app.infrastructure.redis import Redis
from app.infrastructure.redis.dependencies import get_redis


async def get_current_session(
    request: Request,
    redis: Annotated[Redis, Depends(get_redis)],
) -> Session:
    """The live session for the request's cookie, or the matching auth error."""
    session_token = get_session_cookie(request)
    if session_token is None:
        raise AppError("UNAUTHENTICATED")

    session = await sessions_service.resolve_session(redis, token=session_token)
    if session is None:
        raise AppError("INVALID_SESSION")

    return session


__all__ = ["get_current_session"]
