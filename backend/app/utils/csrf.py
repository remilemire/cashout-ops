# backend/app/utils/csrf.py

from __future__ import annotations

import secrets

from fastapi import Request, Response

from app.errors import ForbiddenError

from .cookies import delete_cookie, set_cookie

CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def set_csrf_cookie(response: Response) -> str:
    token = secrets.token_urlsafe(32)
    set_cookie(response, CSRF_COOKIE, token, httponly=False)
    return token


def clear_csrf_cookie(response: Response) -> None:
    delete_cookie(response, CSRF_COOKIE, httponly=False)


def verify_csrf(request: Request):
    if request.method in _SAFE_METHODS:
        return
    cookie_token = request.cookies.get(CSRF_COOKIE)
    header_token = request.headers.get(CSRF_HEADER)
    if cookie_token is None or header_token is None or cookie_token != header_token:
        raise ForbiddenError("invalid csrf-token")
