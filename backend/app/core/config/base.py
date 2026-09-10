from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsGroup(BaseSettings):
    """Shared loading rules for every settings group.

    Each group reads the environment itself under its own `env_prefix`, so it
    also sees every other group's variables and must ignore them. extra="ignore"
    covers that, and with it the original reason for the setting: a .env may
    carry variables not modeled here (or no longer modeled), and they must not
    prevent boot.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


__all__ = ["SettingsGroup"]
