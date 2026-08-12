# backend/app/core/config/db.py

from __future__ import annotations

from pydantic import Field

from .base import SettingsGroup


class DbSettings(SettingsGroup):
    # No env_prefix: DATABASE_URL keeps its conventional name because hosting
    # platforms inject it under that name and migrations/env.py reads it
    # straight from the environment, outside Settings.
    URL: str = Field(validation_alias="DATABASE_URL")


__all__ = ["DbSettings"]
