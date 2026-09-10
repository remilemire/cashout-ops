from __future__ import annotations

from datetime import timedelta

from fastapi import Response

from .config import settings


def set_cookie(
    response: Response,
    *,
    key: str,
    value: str,
    httponly: bool = True,
    max_age: timedelta | None = None,
) -> None:
    response.set_cookie(
        key=key,
        value=value,
        httponly=httponly,
        max_age=int(max_age.total_seconds()) if max_age is not None else None,
        secure=not settings.app.DEBUG,
        samesite="lax",
        path="/",
    )


def delete_cookie(response: Response, *, key: str, httponly: bool = True) -> None:
    response.delete_cookie(
        key=key,
        httponly=httponly,
        samesite="lax",
        secure=not settings.app.DEBUG,
        path="/",
    )
