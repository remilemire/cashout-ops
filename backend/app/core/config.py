# backend/app/core/config.py

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import EmailStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.integrations.ai import AIProvider
from app.integrations.email import EmailProvider


class Settings(BaseSettings):
    # extra="ignore": a .env may carry variables not modeled here (or no longer
    # modeled); they must not prevent boot.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: Literal["prod", "dev"] = "prod"
    DATABASE_URL: str
    SESSION_TTL_DAYS: int = 7
    INVITATION_TTL_DAYS: int = 7
    ADMIN_EMAIL: EmailStr = "admin@test.com"

    # Email delivery. EMAIL_PROVIDER selects the client: CONSOLE logs the
    # message (dev default; boots without a key), RESEND sends for real and
    # requires RESEND_API_KEY (validated at startup). EMAIL_FROM is the sender.
    EMAIL_PROVIDER: EmailProvider = EmailProvider.CONSOLE
    RESEND_API_KEY: str | None = None
    EMAIL_FROM: str = "Whiskey District <onboarding@resend.dev>"

    # Email verification. A short-lived numeric code is emailed on registration;
    # the account stays unverified until the code is entered before it expires.
    EMAIL_VERIFICATION_CODE_TTL_MINUTES: int = 15

    # Document-AI provider selection. Only the selected provider's API key is
    # required; the lifespan validates it at startup.
    AI_PROVIDER: AIProvider = AIProvider.ANTHROPIC
    # Per-operation output-token budgets, deliberately conservative: a
    # classification is a tiny fixed-shape JSON object; an extraction scales
    # with the schema. Raise via env if analyses start failing TRUNCATED.
    AI_CLASSIFICATION_MAX_TOKENS: int = 512
    AI_EXTRACTION_MAX_TOKENS: int = 2048

    # Model per provider, resolved for the selected provider by AI_MODEL below.
    # The model is not env-configurable — edit a value here to change it.
    AI_MODELS: ClassVar[Mapping[AIProvider, str]] = {
        AIProvider.ANTHROPIC: "claude-sonnet-4-6",
        AIProvider.OPENAI: "gpt-5.6-terra",
        AIProvider.GEMINI: "gemini-3.5-flash",
    }
    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None
    DOCUMENT_STORAGE_DIR: Path = Path("storage/documents")

    @computed_field
    @property
    def DEBUG(self) -> bool:
        return self.ENVIRONMENT == "dev"

    @computed_field
    @property
    def AI_MODEL(self) -> str:
        return self.AI_MODELS[self.AI_PROVIDER]


settings = Settings()  # pyright: ignore[reportCallIssue]
