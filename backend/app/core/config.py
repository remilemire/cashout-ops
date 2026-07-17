# backend/app/core/config.py

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import EmailStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.integrations.ai import AIProvider


class Settings(BaseSettings):
    # extra="ignore": a .env may carry variables not modeled here (or no longer
    # modeled); they must not prevent boot.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: Literal["prod", "dev"] = "prod"
    DATABASE_URL: str
    SESSION_TTL_DAYS: int = 7
    ADMIN_EMAIL: EmailStr = "admin@test.com"

    # Document-AI provider selection. Only the selected provider's API key is
    # required; the lifespan validates it at startup.
    AI_PROVIDER: AIProvider = AIProvider.ANTHROPIC
    AI_MODEL: str = "claude-opus-4-8"
    AI_MAX_TOKENS: int = 16000
    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None
    DOCUMENT_STORAGE_DIR: Path = Path("storage/documents")

    @computed_field
    @property
    def DEBUG(self) -> bool:
        return self.ENVIRONMENT == "dev"


settings = Settings()  # pyright: ignore[reportCallIssue]
