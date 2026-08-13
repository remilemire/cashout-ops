# backend/app/core/config/ai.py

from __future__ import annotations

from collections.abc import Mapping

from pydantic import Field, computed_field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

from app.core.ai_models import AI_PROVIDER_MODELS
from app.core.providers import AIProvider

from .base import SettingsGroup

# AI_PROVIDER_MODELS inverted: the catalog reads naturally grouped by provider,
# but every lookup here goes the other way — MODEL is the configured value and
# the provider is derived from it.
_MODEL_PROVIDERS: Mapping[str, AIProvider] = {
    model: provider
    for provider, models in AI_PROVIDER_MODELS.items()
    for model in models
}


class AISettings(SettingsGroup):
    """Document-AI model selection.

    MODEL must be one of the models listed in core/ai_models.py; PROVIDER below
    is derived from it, and only that provider's API key is required.
    """

    model_config = SettingsConfigDict(env_prefix="AI_")

    MODEL: str = "claude-sonnet-5"
    # Per-operation output-token budgets, deliberately conservative: a
    # classification is a tiny fixed-shape JSON object; an extraction scales
    # with the schema. Raise via env if analyses start failing OUTPUT_LIMIT_REACHED.
    CLASSIFICATION_MAX_TOKENS: int = 512
    EXTRACTION_MAX_TOKENS: int = 2048

    # Unprefixed: each vendor's own conventional variable name.
    ANTHROPIC_API_KEY: str | None = Field(
        default=None, validation_alias="ANTHROPIC_API_KEY"
    )
    OPENAI_API_KEY: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    GEMINI_API_KEY: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")

    @field_validator("MODEL")
    @classmethod
    def _validate_ai_model(cls, value: str) -> str:
        if value not in _MODEL_PROVIDERS:
            supported = ", ".join(_MODEL_PROVIDERS)
            raise ValueError(f"AI_MODEL must be one of: {supported}.")
        return value

    @model_validator(mode="after")
    def _validate_ai_credentials(self) -> AISettings:
        """Require the API key of the provider serving MODEL.

        Only the selected provider's key is needed; the other two stay unset
        in a normal deployment. This map must cover every AIProvider.
        """
        keys = {
            AIProvider.ANTHROPIC: self.ANTHROPIC_API_KEY,
            AIProvider.OPENAI: self.OPENAI_API_KEY,
            AIProvider.GEMINI: self.GEMINI_API_KEY,
        }
        if not keys[self.PROVIDER]:
            # .name, not the member itself: the message names the environment
            # variable, which keeps the provider's uppercase spelling.
            raise ValueError(
                f"{self.PROVIDER.name}_API_KEY required when "
                f"AI_MODEL is served by {self.PROVIDER.name}."
            )
        return self

    @computed_field
    @property
    def PROVIDER(self) -> AIProvider:
        return _MODEL_PROVIDERS[self.MODEL]


__all__ = ["AISettings"]
