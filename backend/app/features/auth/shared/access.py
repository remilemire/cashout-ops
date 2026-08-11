# backend/app/features/auth/shared/access.py

"""Session access at the HTTP boundary: granting and revoking sign-in.

These helpers deliberately touch the FastAPI response — issuing or ending a
session is inseparable from setting or clearing its cookies, so both halves
live here rather than being split across routers.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Response

from app.features.auth.shared.sessions import service as sessions_service
from app.features.auth.shared.sessions.cookies import (
    clear_session_cookie,
    set_session_cookie,
)
from app.features.auth.shared.sessions.model import Session
from app.infrastructure.redis import Redis
from app.security.crypto import generate_secret_token
from app.security.csrf import clear_csrf_cookie, set_csrf_cookie


async def grant(redis: Redis, response: Response, *, user_id: UUID) -> Session:
    """Complete authentication: issue a session and set the auth cookies."""
    issued = await sessions_service.create(redis, user_id=user_id)

    set_session_cookie(response, issued.token)
    set_csrf_cookie(response, generate_secret_token())

    return issued.session


async def revoke(
    redis: Redis, response: Response, *, session_token: str | None
) -> None:
    """End the session (if any) and clear the auth cookies.

    Best-effort: a missing or already-dead token still clears the cookies.
    """
    if session_token is not None:
        await sessions_service.delete_by_token(redis, token=session_token)

    clear_session_cookie(response)
    clear_csrf_cookie(response)


__all__ = ["grant", "revoke"]
