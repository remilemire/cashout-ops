# backend/app/dependencies/csrf.py

from __future__ import annotations

import secrets

from fastapi import Request

from app.errors import AppError
from app.security.cookies import get_csrf_cookie, get_csrf_header

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def require_csrf(request: Request) -> None:
    """Double-submit check: the csrf cookie must match the x-csrf-token header."""
    if request.method in SAFE_METHODS:
        return

    cookie_token = get_csrf_cookie(request)
    header_token = get_csrf_header(request)
    if (
        cookie_token is None
        or header_token is None
        or not secrets.compare_digest(cookie_token, header_token)
    ):
        raise AppError("INVALID_CSRF_TOKEN")


__all__ = ["require_csrf"]
