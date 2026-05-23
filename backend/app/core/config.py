# backend/app/core/config.py

from __future__ import annotations

import secrets
from typing import Literal

from pydantic import EmailStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    ENVIRONMENT: Literal["production", "development"] = "development"

    SECRET_KEY: str = secrets.token_urlsafe(32)
    DATABASE_URL: str = "postgresql+psycopg://postgres:dev@localhost:5432/cashout_ops"

    ADMIN_EMAIL: EmailStr = "admin@test.com"

    @computed_field
    @property
    def DEBUG(self) -> bool:
        return self.ENVIRONMENT == "production"


settings = Settings()
