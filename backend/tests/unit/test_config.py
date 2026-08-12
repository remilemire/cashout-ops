# backend/tests/unit/test_config.py

"""Unit tests for settings that derive behavior rather than just holding it."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.ai_models import AI_PROVIDER_MODELS
from app.core.config import Settings
from app.core.providers import AIProvider, EmailProvider, StorageProvider

# Fields Settings will not construct without; irrelevant to what these tests
# assert. LOCAL_STORAGE_DIR and ANTHROPIC_API_KEY are required by the default
# storage provider and the default model's provider respectively, so they are
# supplied here rather than left to whatever the environment happens to carry.
_REQUIRED = {
    "DATABASE_URL": "postgresql+psycopg://postgres:dev@localhost:5432/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "LOCAL_STORAGE_DIR": "storage/documents",
    "ANTHROPIC_API_KEY": "test-anthropic-key",
}


def _settings(**overrides: str | None) -> Settings:
    # Merged rather than splatted side by side so a test can override one of
    # the required fields — notably clearing LOCAL_STORAGE_DIR.
    return Settings(**{**_REQUIRED, **overrides})  # pyright: ignore[reportArgumentType]


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
    config = _settings(AI_MODEL=model, **{f"{provider}_API_KEY": "test-key"})

    assert config.AI_PROVIDER is provider


def test_the_default_model_resolves() -> None:
    # The default has to be a listed model or every unconfigured boot fails.
    assert _settings().AI_PROVIDER in AI_PROVIDER_MODELS


def test_an_unlisted_model_is_rejected() -> None:
    with pytest.raises(ValidationError, match="AI_MODEL must be one of"):
        _settings(AI_MODEL="gpt-4o")


def test_s3_storage_requires_a_bucket() -> None:
    with pytest.raises(ValidationError, match="S3_BUCKET"):
        _settings(DOCUMENT_STORAGE_PROVIDER=StorageProvider.S3, S3_REGION="us-east-1")


def test_s3_storage_requires_a_region() -> None:
    with pytest.raises(ValidationError, match="S3_REGION"):
        _settings(DOCUMENT_STORAGE_PROVIDER=StorageProvider.S3, S3_BUCKET="documents")


def test_s3_storage_reports_every_missing_setting() -> None:
    # One boot surfaces the whole gap, rather than revealing the next missing
    # variable only after the previous one is supplied.
    with pytest.raises(ValidationError, match="S3_BUCKET, S3_REGION"):
        _settings(DOCUMENT_STORAGE_PROVIDER=StorageProvider.S3)


def test_s3_storage_does_not_require_the_local_directory() -> None:
    config = _settings(
        DOCUMENT_STORAGE_PROVIDER=StorageProvider.S3,
        S3_BUCKET="documents",
        S3_REGION="us-east-1",
        LOCAL_STORAGE_DIR=None,
    )

    assert config.S3_BUCKET == "documents"


def test_local_storage_requires_a_directory() -> None:
    with pytest.raises(ValidationError, match="LOCAL_STORAGE_DIR"):
        _settings(LOCAL_STORAGE_DIR=None)


def test_local_storage_does_not_require_the_s3_settings() -> None:
    config = _settings(DOCUMENT_STORAGE_PROVIDER=StorageProvider.LOCAL)

    assert config.S3_BUCKET is None


def test_resend_email_requires_an_api_key() -> None:
    with pytest.raises(ValidationError, match="RESEND_API_KEY"):
        _settings(EMAIL_PROVIDER=EmailProvider.RESEND, RESEND_API_KEY=None)


def test_console_email_does_not_require_an_api_key() -> None:
    config = _settings(EMAIL_PROVIDER=EmailProvider.CONSOLE, RESEND_API_KEY=None)

    assert config.EMAIL_PROVIDER is EmailProvider.CONSOLE


@pytest.mark.parametrize(
    ("provider", "model"),
    [(provider, models[0]) for provider, models in AI_PROVIDER_MODELS.items()],
)
def test_the_serving_providers_api_key_is_required(
    provider: AIProvider, model: str
) -> None:
    # _REQUIRED carries an Anthropic key, so clear it to cover that provider
    # too rather than passing only because the default happens to be set.
    with pytest.raises(ValidationError, match=f"{provider}_API_KEY"):
        _settings(AI_MODEL=model, **{f"{provider}_API_KEY": None})


def test_an_unrelated_providers_api_key_may_be_missing() -> None:
    # Only the model's own provider needs a key; a deployment does not carry
    # credentials for the two it never calls.
    config = _settings(
        AI_MODEL="gpt-5.6-terra",
        OPENAI_API_KEY="test-openai-key",
        ANTHROPIC_API_KEY=None,
        GEMINI_API_KEY=None,
    )

    assert config.AI_PROVIDER is AIProvider.OPENAI
