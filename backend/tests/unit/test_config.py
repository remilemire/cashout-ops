# backend/tests/unit/test_config.py

"""Unit tests for settings that derive behavior rather than just holding it."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.ai import AI_PROVIDER_MODELS, AIProvider
from app.core.config import Settings

# Required fields with no default; irrelevant to what these tests assert, but
# Settings will not construct without them.
_REQUIRED = {
    "DATABASE_URL": "postgresql+psycopg://postgres:dev@localhost:5432/test",
    "REDIS_URL": "redis://localhost:6379/0",
}


def _settings(**overrides: str) -> Settings:
    return Settings(**_REQUIRED, **overrides)  # pyright: ignore[reportArgumentType]


def test_a_model_belongs_to_exactly_one_provider() -> None:
    # config.py inverts AI_PROVIDER_MODELS into a model-keyed map, so a model
    # listed twice would silently resolve to whichever provider came last.
    listed = [model for models in AI_PROVIDER_MODELS.values() for model in models]

    assert len(listed) == len(set(listed))


@pytest.mark.parametrize(
    ("provider", "model"),
    [(provider, models[0]) for provider, models in AI_PROVIDER_MODELS.items()],
)
def test_ai_provider_is_derived_from_the_model(
    provider: AIProvider, model: str
) -> None:
    assert _settings(AI_MODEL=model).AI_PROVIDER is provider


def test_the_default_model_resolves() -> None:
    # The default has to be a listed model or every unconfigured boot fails.
    assert _settings().AI_PROVIDER in AI_PROVIDER_MODELS


def test_an_unlisted_model_is_rejected() -> None:
    with pytest.raises(ValidationError, match="AI_MODEL must be one of"):
        _settings(AI_MODEL="gpt-4o")
