# backend/app/core/config/redis.py

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from .base import SettingsGroup


class RedisSettings(SettingsGroup):
    # The prefix already produces the conventional REDIS_URL, so this group
    # needs no alias to keep its name.
    model_config = SettingsConfigDict(env_prefix="REDIS_")

    URL: str


__all__ = ["RedisSettings"]
