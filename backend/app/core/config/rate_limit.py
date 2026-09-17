from __future__ import annotations

from typing import Literal

from pydantic_settings import SettingsConfigDict

from .base import SettingsGroup


class RateLimitSettings(SettingsGroup):
    """Rate limits (fixed 1-hour windows; counters live in Redis under
    rate_limit:*).

    AUTH_IP caps each anonymous auth endpoint per client IP; INITIATE_EMAIL
    caps sign-in emails per address, real or decoy; UPLOADS and EXTRACTS cap
    each user's cashout document uploads and AI re-extractions.
    """

    model_config = SettingsConfigDict(env_prefix="RATE_LIMIT_")

    # Cloudflare mode requires an edge that overwrites CF-Connecting-IP and
    # no untrusted paths around that edge. request_client uses ASGI's address,
    # which may already have been rewritten by the server's proxy middleware.
    CLIENT_IP_SOURCE: Literal["request_client", "cloudflare"] = "request_client"

    AUTH_IP_PER_HOUR: int = 20
    INITIATE_EMAIL_PER_HOUR: int = 5
    UPLOADS_PER_USER_PER_HOUR: int = 30
    EXTRACTS_PER_USER_PER_HOUR: int = 15


__all__ = ["RateLimitSettings"]
