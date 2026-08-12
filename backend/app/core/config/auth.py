# backend/app/core/config/auth.py

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from .base import SettingsGroup


class AuthSettings(SettingsGroup):
    model_config = SettingsConfigDict(env_prefix="AUTH_")

    SESSION_TTL_DAYS: int = 7
    # Email challenges. A sign-in link is emailed on login; the challenge (and
    # with it the link and its one-time code) expires this long after initiation.
    CHALLENGE_TTL_MINUTES: int = 15


__all__ = ["AuthSettings"]
