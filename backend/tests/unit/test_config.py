"""Unit tests for settings that derive behavior rather than just holding it."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.ai_models import AI_PROVIDER_MODELS
from app.core.config import (
    AISettings,
    AppSettings,
    AuthSettings,
    BootstrapSettings,
    EmailSettings,
    Settings,
    StorageSettings,
    settings,
)
from app.core.providers import AIProvider, EmailProvider, StorageProvider
from tests.support.settings import make_test_settings

# Every group reads the environment itself, so a test about a *missing* setting
# has to pass it as None rather than trust whatever the host's .env carries.
# These baselines make each construction fully specified; a test overrides only
# the field it is about.
_AI = {
    "ANTHROPIC_API_KEY": "test-anthropic-key",
    "OPENAI_API_KEY": "test-openai-key",
    "GEMINI_API_KEY": "test-gemini-key",
}
_STORAGE = {
    "LOCAL_DIR": "storage/documents",
    "S3_BUCKET": None,
    "S3_REGION": None,
    "S3_ENDPOINT_URL": None,
    "GCS_BUCKET": None,
}


def _ai(**overrides: object) -> AISettings:
    return AISettings(**{**_AI, **overrides})  # pyright: ignore[reportArgumentType]


def _storage(**overrides: object) -> StorageSettings:
    return StorageSettings(**{**_STORAGE, **overrides})  # pyright: ignore[reportArgumentType]


def test_a_model_belongs_to_exactly_one_provider() -> None:
    # config/ai.py inverts AI_PROVIDER_MODELS into a model-keyed map, so a model
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
    config = _ai(MODEL=model)

    assert config.PROVIDER is provider


def test_the_default_model_resolves() -> None:
    # The default has to be a listed model or every unconfigured boot fails.
    # Every key is supplied so the assertion does not depend on which provider
    # the default currently belongs to.
    assert _ai().PROVIDER in AI_PROVIDER_MODELS


def test_an_unlisted_model_is_rejected() -> None:
    with pytest.raises(ValidationError, match="AI_MODEL must be one of"):
        _ai(MODEL="gpt-4o")


@pytest.mark.parametrize(
    ("provider", "model"),
    [(provider, models[0]) for provider, models in AI_PROVIDER_MODELS.items()],
)
def test_the_serving_providers_api_key_is_required(
    provider: AIProvider, model: str
) -> None:
    # Clear only the serving provider's key, leaving the other two set, so the
    # failure can only come from the one the model needs. The key is named by
    # the member (ANTHROPIC_API_KEY), not its snake_case value.
    with pytest.raises(ValidationError, match=f"{provider.name}_API_KEY"):
        _ai(MODEL=model, **{f"{provider.name}_API_KEY": None})


def test_an_unrelated_providers_api_key_may_be_missing() -> None:
    # Only the model's own provider needs a key; a deployment does not carry
    # credentials for the two it never calls.
    config = _ai(MODEL="gpt-5.6-terra", ANTHROPIC_API_KEY=None, GEMINI_API_KEY=None)

    assert config.PROVIDER is AIProvider.OPENAI


def test_s3_storage_requires_a_bucket() -> None:
    with pytest.raises(ValidationError, match="S3_BUCKET"):
        _storage(PROVIDER=StorageProvider.S3, S3_REGION="us-east-1")


def test_s3_storage_requires_a_region() -> None:
    with pytest.raises(ValidationError, match="S3_REGION"):
        _storage(PROVIDER=StorageProvider.S3, S3_BUCKET="documents")


def test_s3_storage_reports_every_missing_setting() -> None:
    # One boot surfaces the whole gap, rather than revealing the next missing
    # variable only after the previous one is supplied.
    with pytest.raises(ValidationError, match="S3_BUCKET, S3_REGION"):
        _storage(PROVIDER=StorageProvider.S3)


def test_s3_storage_does_not_require_the_local_directory() -> None:
    config = _storage(
        PROVIDER=StorageProvider.S3,
        S3_BUCKET="documents",
        S3_REGION="us-east-1",
        LOCAL_DIR=None,
    )

    assert config.S3_BUCKET == "documents"


def test_s3_storage_does_not_require_an_endpoint_url() -> None:
    # Unset is the AWS endpoint for S3_REGION; only an S3-compatible store
    # needs the override, so a missing value must still boot.
    config = _storage(
        PROVIDER=StorageProvider.S3, S3_BUCKET="documents", S3_REGION="us-east-1"
    )

    assert config.S3_ENDPOINT_URL is None


def test_s3_storage_keeps_a_configured_endpoint_url() -> None:
    config = _storage(
        PROVIDER=StorageProvider.S3,
        S3_BUCKET="documents",
        S3_REGION="us-east-1",
        S3_ENDPOINT_URL="http://localhost:9000",
    )

    assert config.S3_ENDPOINT_URL == "http://localhost:9000"


def test_a_blank_endpoint_url_counts_as_unset() -> None:
    # A bare `S3_ENDPOINT_URL=` would otherwise reach boto3 as an empty
    # endpoint rather than falling back to AWS's own.
    config = _storage(
        PROVIDER=StorageProvider.S3,
        S3_BUCKET="documents",
        S3_REGION="us-east-1",
        S3_ENDPOINT_URL="   ",
    )

    assert config.S3_ENDPOINT_URL is None


def test_gcs_storage_requires_a_bucket() -> None:
    with pytest.raises(ValidationError, match="GCS_BUCKET"):
        _storage(PROVIDER=StorageProvider.GCS)


def test_gcs_storage_does_not_require_the_local_directory_or_s3_settings() -> None:
    config = _storage(
        PROVIDER=StorageProvider.GCS, GCS_BUCKET="documents", LOCAL_DIR=None
    )

    assert config.GCS_BUCKET == "documents"
    assert config.S3_BUCKET is None


def test_local_storage_requires_a_directory() -> None:
    with pytest.raises(ValidationError, match="STORAGE_LOCAL_DIR"):
        _storage(LOCAL_DIR=None)


def test_a_blank_local_directory_counts_as_unset() -> None:
    # A bare `STORAGE_LOCAL_DIR=` would otherwise parse to Path(".") and write
    # documents into the working directory.
    with pytest.raises(ValidationError, match="STORAGE_LOCAL_DIR"):
        _storage(LOCAL_DIR="   ")


def test_local_storage_does_not_require_the_other_providers_settings() -> None:
    config = _storage(PROVIDER=StorageProvider.LOCAL)

    assert config.S3_BUCKET is None
    assert config.GCS_BUCKET is None


def test_the_size_limit_is_exposed_in_bytes() -> None:
    config = _storage(MAX_DOCUMENT_SIZE_MB=3)

    assert config.MAX_DOCUMENT_SIZE_BYTES == 3 * 1024 * 1024


def test_resend_email_requires_an_api_key() -> None:
    with pytest.raises(ValidationError, match="RESEND_API_KEY"):
        EmailSettings(PROVIDER=EmailProvider.RESEND, RESEND_API_KEY=None)


def test_console_email_does_not_require_an_api_key() -> None:
    config = EmailSettings(PROVIDER=EmailProvider.CONSOLE, RESEND_API_KEY=None)

    assert config.PROVIDER is EmailProvider.CONSOLE


# There is no OAuth enablement setting: Google sign-in is on exactly when both
# credentials are set, so the only invalid state is a half-configured pair.
def test_google_oauth_credentials_must_be_set_together() -> None:
    with pytest.raises(ValidationError, match="GOOGLE_CLIENT_SECRET required"):
        AuthSettings(
            GOOGLE_CLIENT_ID="test-google-client-id", GOOGLE_CLIENT_SECRET=None
        )
    with pytest.raises(ValidationError, match="GOOGLE_CLIENT_ID required"):
        AuthSettings(GOOGLE_CLIENT_ID=None, GOOGLE_CLIENT_SECRET="test-google-secret")


def test_google_oauth_credentials_may_both_be_absent() -> None:
    config = AuthSettings(GOOGLE_CLIENT_ID=None, GOOGLE_CLIENT_SECRET=None)

    assert config.GOOGLE_CLIENT_ID is None


def test_the_bootstrap_owner_address_is_normalized() -> None:
    # The owner is recognized by comparing this value against a signed-in
    # address, and stored addresses are folded — so a deployment that
    # configures mixed case must not lock itself out of its own bootstrap.
    config = BootstrapSettings(OWNER_EMAIL="Owner@Example.COM")

    assert config.OWNER_EMAIL == "owner@example.com"


def test_debug_follows_the_environment() -> None:
    assert AppSettings(ENV="dev").DEBUG is True
    assert AppSettings(ENV="prod").DEBUG is False


def test_groups_load_from_their_prefixed_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Each group reads the environment under its own prefix. Nothing else in the
    # suite would notice a prefix that stopped matching, because the defaults
    # would quietly stand in.
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("AUTH_SESSION_TTL_DAYS", "3")
    monkeypatch.setenv("BOOTSTRAP_OWNER_FULL_NAME", "Configured Owner")
    monkeypatch.setenv("STORAGE_LOCAL_DIR", "var/documents")
    monkeypatch.setenv("OCR_DETECTION_MAX_SIDE", "960")
    monkeypatch.setenv("RATE_LIMIT_UPLOADS_PER_USER_PER_HOUR", "7")

    config = Settings()

    assert config.app.ENV == "dev"
    assert config.auth.SESSION_TTL_DAYS == 3
    assert config.bootstrap.OWNER_FULL_NAME == "Configured Owner"
    assert config.storage.LOCAL_DIR == Path("var/documents")
    assert config.ocr.DETECTION_MAX_SIDE == 960
    assert config.rate_limit.UPLOADS_PER_USER_PER_HOUR == 7


def test_conventional_names_stay_unprefixed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # These five are supplied by something outside this app — a hosting
    # platform, alembic, or a vendor SDK's own convention — so they keep their
    # usual spelling despite living inside a prefixed group.
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unused/conventional")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "conventional-anthropic-key")
    monkeypatch.setenv("STORAGE_PROVIDER", "S3")
    monkeypatch.setenv("S3_BUCKET", "conventional-bucket")
    monkeypatch.setenv("S3_REGION", "us-east-1")
    monkeypatch.setenv("GCS_BUCKET", "conventional-gcs-bucket")

    config = Settings()

    assert config.db.URL == "postgresql+psycopg://unused/conventional"
    assert config.ai.ANTHROPIC_API_KEY == "conventional-anthropic-key"
    assert config.storage.S3_BUCKET == "conventional-bucket"
    assert config.storage.S3_REGION == "us-east-1"
    assert config.storage.GCS_BUCKET == "conventional-gcs-bucket"


def test_the_test_baseline_ignores_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # env_file is resolved against the working directory, so a poisoned .env
    # here is exactly what the suite must never read. delenv keeps the test
    # about dotenv, not the (intentional) os.environ override channel.
    monkeypatch.delenv("BOOTSTRAP_OWNER_FULL_NAME", raising=False)
    monkeypatch.delenv("AUTH_SESSION_TTL_DAYS", raising=False)
    (tmp_path / ".env").write_text(
        "BOOTSTRAP_OWNER_FULL_NAME=Poisoned\nAUTH_SESSION_TTL_DAYS=99\n"
    )
    monkeypatch.chdir(tmp_path)

    config = make_test_settings()

    assert config.bootstrap.OWNER_FULL_NAME == "Owner"
    assert config.auth.SESSION_TTL_DAYS == 7


def test_the_live_settings_are_the_hermetic_baseline() -> None:
    # Pydantic equality compares field values: proves the conftest swap
    # actually installed the baseline on the singleton.
    assert settings == make_test_settings()


def test_rate_limit_client_ip_source_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RATE_LIMIT_CLIENT_IP_SOURCE", "cloudflare")
    assert make_test_settings().rate_limit.CLIENT_IP_SOURCE == "cloudflare"


def test_rate_limit_rejects_unknown_client_ip_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RATE_LIMIT_CLIENT_IP_SOURCE", "x-forwarded-for")
    with pytest.raises(ValidationError):
        make_test_settings()
