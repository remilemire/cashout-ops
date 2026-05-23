# backend/app/utils/cookies.py

from __future__ import annotations

from fastapi import Response

from app.core.config import settings


def set_cookie(
    response: Response, key: str, value: str, *, httponly: bool = True
) -> None:
    response.set_cookie(
        key=key,
        value=value,
        httponly=httponly,
        secure=not settings.DEBUG,
        samesite="lax",
        path="/",
    )


def delete_cookie(response: Response, key: str, *, httponly: bool = True) -> None:
    response.delete_cookie(
        key=key,
        httponly=httponly,
        samesite="lax",
        secure=not settings.DEBUG,
        path="/",
    )
