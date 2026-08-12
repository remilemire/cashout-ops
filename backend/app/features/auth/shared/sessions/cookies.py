# backend/app/features/auth/shared/sessions/cookies.py

from __future__ import annotations

from datetime import timedelta

from fastapi import Request, Response

from app.core.config import settings
from app.core.cookies import delete_cookie, set_cookie

SESSION_COOKIE = "session_token"


def set_session_cookie(response: Response, token: str) -> None:
    set_cookie(
        response,
        key=SESSION_COOKIE,
        value=token,
        max_age=timedelta(days=settings.auth.SESSION_TTL_DAYS),
    )


def get_session_cookie(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE)


def clear_session_cookie(response: Response) -> None:
    delete_cookie(response, key=SESSION_COOKIE)


__all__ = [
    "SESSION_COOKIE",
    "set_session_cookie",
    "get_session_cookie",
    "clear_session_cookie",
]
