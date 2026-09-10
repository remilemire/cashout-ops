from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .ai import AISettings
from .app import AppSettings
from .auth import AuthSettings
from .base import SettingsGroup
from .bootstrap import BootstrapSettings
from .db import DbSettings
from .email import EmailSettings
from .ocr import OCRSettings
from .outbox import OutboxSettings
from .rate_limit import RateLimitSettings
from .redis import RedisSettings
from .storage import StorageSettings
from .tipout import TipoutSettings


class Settings(BaseSettings):
    """Application configuration, one nested group per concern.

    Every group is a settings model in its own right: `default_factory` builds
    it, and it reads the environment itself under its own `env_prefix`. A group
    whose configuration is incomplete therefore fails while this object is
    being constructed — at import, not at first use.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ai: AISettings = Field(default_factory=AISettings)
    app: AppSettings = Field(default_factory=AppSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    bootstrap: BootstrapSettings = Field(default_factory=BootstrapSettings)
    # DbSettings and RedisSettings each have a required URL, so the type
    # checker cannot see the class itself as a zero-argument factory; the
    # environment supplies the value.
    db: DbSettings = Field(default_factory=lambda: DbSettings())  # pyright: ignore[reportCallIssue]
    email: EmailSettings = Field(default_factory=EmailSettings)
    ocr: OCRSettings = Field(default_factory=OCRSettings)
    outbox: OutboxSettings = Field(default_factory=OutboxSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    redis: RedisSettings = Field(default_factory=lambda: RedisSettings())  # pyright: ignore[reportCallIssue]
    storage: StorageSettings = Field(default_factory=StorageSettings)
    tipout: TipoutSettings = Field(default_factory=TipoutSettings)


settings = Settings()

__all__ = [
    "AISettings",
    "AppSettings",
    "AuthSettings",
    "BootstrapSettings",
    "DbSettings",
    "EmailSettings",
    "OCRSettings",
    "OutboxSettings",
    "RateLimitSettings",
    "RedisSettings",
    "Settings",
    "SettingsGroup",
    "StorageSettings",
    "settings",
]
