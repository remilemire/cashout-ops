# backend/app/security/cookies.py

from __future__ import annotations

from datetime import timedelta

from fastapi import Request, Response

from app.core.config import settings
from app.core.cookies import delete_cookie, set_cookie

SESSION_COOKIE = "session_token"
SESSION_TTL = timedelta(days=settings.SESSION_TTL_DAYS)

CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "x-csrf-token"


# ================================
# ----------- Sessions -----------
# ================================


def set_session_cookie(response: Response, token: str) -> None:
    set_cookie(response, key=SESSION_COOKIE, value=token, max_age=SESSION_TTL)


def get_session_cookie(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE)


def clear_session_cookie(response: Response) -> None:
    delete_cookie(response, key=SESSION_COOKIE)


# ================================
# ------------- CSRF -------------
# ================================


# The CSRF cookie is readable by JS for the double-submit header check.
def set_csrf_cookie(response: Response, token: str) -> None:
    set_cookie(response, key=CSRF_COOKIE, value=token, httponly=False)


def clear_csrf_cookie(response: Response) -> None:
    delete_cookie(response, key=CSRF_COOKIE, httponly=False)


def get_csrf_cookie(request: Request) -> str | None:
    return request.cookies.get(CSRF_COOKIE)


def get_csrf_header(request: Request) -> str | None:
    return request.headers.get(CSRF_HEADER)
