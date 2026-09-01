# backend/app/core/config/app.py

from __future__ import annotations

from typing import Literal

from pydantic import computed_field
from pydantic_settings import SettingsConfigDict

from .base import SettingsGroup


class AppSettings(SettingsGroup):
    model_config = SettingsConfigDict(env_prefix="APP_")

    ENV: Literal["prod", "dev"] = "prod"
    # Public base URL of the SPA, used to build OAuth redirect URIs. The dev
    # default targets the Vite server; production must set its real origin.
    BASE_URL: str = "http://localhost:5173"

    @computed_field
    @property
    def DEBUG(self) -> bool:
        return self.ENV == "dev"


__all__ = ["AppSettings"]
