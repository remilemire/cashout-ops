# backend/app/features/auth/oauth/cookies.py

from __future__ import annotations

from datetime import timedelta

from fastapi import Request, Response

from app.core.config import settings
from app.core.cookies import delete_cookie, set_cookie

# Holds only the flow id. The cookie is the browser binding: the callback
# honors a flow only when it arrives from the user agent that started it —
# `state` alone cannot prove that. Same TTL as the Redis flow, which stays
# authoritative; a stale cookie just fails the Redis lookup.
OAUTH_FLOW_COOKIE = "oauth_flow"


def set_oauth_flow_cookie(response: Response, flow_id: str) -> None:
    set_cookie(
        response,
        key=OAUTH_FLOW_COOKIE,
        value=flow_id,
        max_age=timedelta(minutes=settings.auth.OAUTH_FLOW_TTL_MINUTES),
    )


def get_oauth_flow_cookie(request: Request) -> str | None:
    return request.cookies.get(OAUTH_FLOW_COOKIE)


def clear_oauth_flow_cookie(response: Response) -> None:
    delete_cookie(response, key=OAUTH_FLOW_COOKIE)


__all__ = [
    "OAUTH_FLOW_COOKIE",
    "set_oauth_flow_cookie",
    "get_oauth_flow_cookie",
    "clear_oauth_flow_cookie",
]
