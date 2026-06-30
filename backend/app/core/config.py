# backend/app/core/config.py

from __future__ import annotations

from typing import Literal

from pydantic import EmailStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    ENVIRONMENT: Literal["prod", "dev"] = "prod"
    SECRET_KEY: str
    DATABASE_URL: str
    SESSION_TTL_DAYS: int = 7
    ADMIN_EMAIL: EmailStr = "admin@test.com"

    @computed_field
    @property
    def DEBUG(self) -> bool:
        return self.ENVIRONMENT == "dev"


settings = Settings()  # pyright: ignore[reportCallIssue]
