# backend/app/core/config.py

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import EmailStr, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.ai import AI_PROVIDER_MODELS, AIProvider
from app.core.storage import StorageProvider
from app.integrations.email import EmailProvider

# AI_PROVIDER_MODELS inverted: the catalog reads naturally grouped by provider,
# but every lookup here goes the other way — AI_MODEL is the configured value
# and the provider is derived from it.
_MODEL_PROVIDERS: Mapping[str, AIProvider] = {
    model: provider
    for provider, models in AI_PROVIDER_MODELS.items()
    for model in models
}


class Settings(BaseSettings):
    # extra="ignore": a .env may carry variables not modeled here (or no longer
    # modeled); they must not prevent boot.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: Literal["prod", "dev"] = "prod"
    DATABASE_URL: str
    REDIS_URL: str
    SESSION_TTL_DAYS: int = 7
    OWNER_EMAIL: EmailStr = "owner@test.com"
    # Full name given to the OWNER_EMAIL account when a first passwordless
    # sign-in bootstraps it as the owner (no registration form supplies one).
    OWNER_FULL_NAME: str = "Owner"

    # Email delivery. EMAIL_PROVIDER selects the client: CONSOLE logs the
    # message (dev default; boots without a key), RESEND sends for real and
    # requires RESEND_API_KEY (validated at startup). EMAIL_FROM is the sender.
    EMAIL_PROVIDER: EmailProvider = EmailProvider.CONSOLE
    RESEND_API_KEY: str | None = None
    EMAIL_FROM: str = "Whiskey District <onboarding@resend.dev>"
    # Public base URL of the SPA, used to build emailed sign-in links. The dev
    # default targets the Vite server; production must set its real origin.
    APP_BASE_URL: str = "http://localhost:5173"

    # Email challenges. A sign-in link is emailed on login; the challenge (and
    # with it the link and its one-time code) expires this long after initiation.
    EMAIL_CHALLENGE_TTL_MINUTES: int = 15

    # Rate limits (fixed 1-hour windows; counters live in Redis under
    # rate_limit:*). AUTH_IP caps each anonymous auth endpoint per client IP;
    # INITIATE_EMAIL caps sign-in emails per address, real or decoy; UPLOADS
    # and EXTRACTS cap each user's cashout document uploads and AI
    # re-extractions.
    RATE_LIMIT_AUTH_IP_PER_HOUR: int = 20
    RATE_LIMIT_INITIATE_EMAIL_PER_HOUR: int = 5
    RATE_LIMIT_UPLOADS_PER_USER_PER_HOUR: int = 30
    RATE_LIMIT_EXTRACTS_PER_USER_PER_HOUR: int = 15

    # Outbox dispatch. Workers poll outbox_messages every POLL_INTERVAL; a
    # claim is protected for CLAIM_TTL before a crashed worker's row becomes
    # claimable again. Failed attempts retry with exponential backoff
    # (BACKOFF_BASE * 2^(attempt-1), capped at BACKOFF_CAP) until MAX_ATTEMPTS
    # runs out and the message dead-letters.
    OUTBOX_MAX_ATTEMPTS: int = 10
    OUTBOX_BATCH_SIZE: int = 1
    OUTBOX_POLL_INTERVAL_SECONDS: float = 1.0
    OUTBOX_CLAIM_TTL_SECONDS: float = 30.0
    OUTBOX_BACKOFF_BASE_SECONDS: float = 5.0
    OUTBOX_BACKOFF_CAP_SECONDS: float = 900.0

    # Document-AI model selection. AI_MODEL must be one of the models listed in
    # core/ai.py; AI_PROVIDER below is derived from it, and only that provider's
    # API key is required (the lifespan validates it at startup).
    AI_MODEL: str = "claude-sonnet-4-6"
    # Per-operation output-token budgets, deliberately conservative: a
    # classification is a tiny fixed-shape JSON object; an extraction scales
    # with the schema. Raise via env if analyses start failing OUTPUT_LIMIT_REACHED.
    AI_CLASSIFICATION_MAX_TOKENS: int = 512
    AI_EXTRACTION_MAX_TOKENS: int = 2048

    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None

    # Document storage. DOCUMENT_STORAGE_PROVIDER selects the client: LOCAL
    # writes under DOCUMENT_STORAGE_DIR (dev default; boots without AWS
    # config), S3 stores objects in S3_BUCKET (required, validated at
    # startup). AWS credentials come from the standard AWS chain (env vars,
    # profile, instance role), not from here; S3_ENDPOINT_URL targets
    # S3-compatible stores such as MinIO or R2.
    DOCUMENT_STORAGE_PROVIDER: StorageProvider = StorageProvider.LOCAL
    DOCUMENT_STORAGE_DIR: Path = Path("storage/documents")
    S3_BUCKET: str | None = None
    S3_REGION: str | None = None
    S3_ENDPOINT_URL: str | None = None

    # Upload ceiling for a single document, in megabytes. The upload endpoint
    # stops reading a request body once it passes this, and the service rejects
    # the upload (DOCUMENT_TOO_LARGE). Configured in MB because that is how the
    # limit is communicated to users; code reads MAX_DOCUMENT_SIZE_BYTES.
    MAX_DOCUMENT_SIZE_MB: int = 20

    @field_validator("AI_MODEL")
    @classmethod
    def _validate_ai_model(cls, value: str) -> str:
        if value not in _MODEL_PROVIDERS:
            supported = ", ".join(_MODEL_PROVIDERS)
            raise ValueError(f"AI_MODEL must be one of: {supported}.")
        return value

    @computed_field
    @property
    def DEBUG(self) -> bool:
        return self.ENVIRONMENT == "dev"

    @computed_field
    @property
    def MAX_DOCUMENT_SIZE_BYTES(self) -> int:
        return self.MAX_DOCUMENT_SIZE_MB * 1024 * 1024

    @computed_field
    @property
    def AI_PROVIDER(self) -> AIProvider:
        return _MODEL_PROVIDERS[self.AI_MODEL]


settings = Settings()  # pyright: ignore[reportCallIssue]

__all__ = ["settings"]
