# backend/tests/unit/test_config.py

"""Unit tests for settings that derive behavior rather than just holding it."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.ai_models import AI_PROVIDER_MODELS
from app.core.config import Settings
from app.core.providers import AIProvider, StorageProvider

# Required fields with no default; irrelevant to what these tests assert, but
# Settings will not construct without them. LOCAL_STORAGE_DIR is required by
# the default LOCAL storage provider, so it is supplied here rather than left
# to whatever the environment happens to carry.
_REQUIRED = {
    "DATABASE_URL": "postgresql+psycopg://postgres:dev@localhost:5432/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "LOCAL_STORAGE_DIR": "storage/documents",
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
    assert _settings(AI_MODEL=model).AI_PROVIDER is provider


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
