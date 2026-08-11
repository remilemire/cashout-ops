# backend/app/security/csrf.py

from __future__ import annotations

from fastapi import Request, Response

from app.core.cookies import delete_cookie, set_cookie

CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "x-csrf-token"


# The CSRF cookie is readable by JS for the double-submit header check.
def set_csrf_cookie(response: Response, token: str) -> None:
    set_cookie(response, key=CSRF_COOKIE, value=token, httponly=False)


def clear_csrf_cookie(response: Response) -> None:
    delete_cookie(response, key=CSRF_COOKIE, httponly=False)


def get_csrf_cookie(request: Request) -> str | None:
    return request.cookies.get(CSRF_COOKIE)


def get_csrf_header(request: Request) -> str | None:
    return request.headers.get(CSRF_HEADER)
