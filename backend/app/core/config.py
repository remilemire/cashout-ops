# backend/app/core/config.py

from __future__ import annotations

import secrets
from typing import Literal

from pydantic import EmailStr, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    APP_ENV: Literal["production", "development"] = "development"
    APP_PORT: int = Field(default=5001, ge=1, le=65535)
    APP_HOST: str = "127.0.0.1"

    SECRET_KEY: str = secrets.token_urlsafe(32)
    DATABASE_URL: str = "postgresql+psycopg://postgres:dev@localhost:5432/cashout"

    ADMIN_EMAIL: EmailStr = "admin@test.com"

    @computed_field
    @property
    def DEBUG(self) -> bool:
        return self.APP_ENV == "development"


settings = Settings()
