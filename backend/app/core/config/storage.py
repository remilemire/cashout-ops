from __future__ import annotations

from pathlib import Path

from pydantic import Field, computed_field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

from app.core.providers import StorageProvider

from .base import SettingsGroup


class StorageSettings(SettingsGroup):
    """Document storage.

    PROVIDER selects the client: LOCAL writes under LOCAL_DIR, S3 stores
    objects in S3_BUCKET, GCS stores objects in GCS_BUCKET. Each provider's
    own settings are required when it is selected and ignored otherwise, so
    every group defaults to None and _validate_storage_config enforces the
    selected one. Provider credentials are not modeled here: AWS credentials
    come from the standard AWS chain (env vars, profile, instance role) and
    Google credentials from Application Default Credentials.
    """

    model_config = SettingsConfigDict(env_prefix="STORAGE_")

    PROVIDER: StorageProvider = StorageProvider.LOCAL
    LOCAL_DIR: Path | None = None
    # Unprefixed: these sit alongside the AWS chain's own variables.
    S3_BUCKET: str | None = Field(default=None, validation_alias="S3_BUCKET")
    S3_REGION: str | None = Field(default=None, validation_alias="S3_REGION")
    # Optional even under S3, so it stays out of _validate_storage_config:
    # unset leaves boto3 on AWS's own regional endpoint, and a value points the
    # client at an S3-compatible store such as MinIO or Cloudflare R2.
    S3_ENDPOINT_URL: str | None = Field(
        default=None, validation_alias="S3_ENDPOINT_URL"
    )
    # Unprefixed: sits alongside the ADC chain's own variables
    # (GOOGLE_APPLICATION_CREDENTIALS), as the S3 settings sit beside AWS's.
    GCS_BUCKET: str | None = Field(default=None, validation_alias="GCS_BUCKET")

    # Accepted file size in megabytes. The handler reads at most the limit
    # plus one byte from the parsed upload, then rejects an oversized file.
    # This does not limit multipart ingestion by the server or proxy.
    MAX_DOCUMENT_SIZE_MB: int = 20

    @field_validator("LOCAL_DIR", mode="before")
    @classmethod
    def _blank_dir_is_unset(cls, value: object) -> object:
        # A bare `STORAGE_LOCAL_DIR=` would otherwise parse to Path("."), which
        # silently writes documents into the working directory. Treat it as
        # unset so the check below rejects it, matching how the S3 settings
        # already treat their empty strings.
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("S3_ENDPOINT_URL", mode="before")
    @classmethod
    def _blank_endpoint_is_unset(cls, value: object) -> object:
        # Nothing requires this field, so a bare `S3_ENDPOINT_URL=` would reach
        # boto3 as an empty endpoint instead of falling back to AWS's own.
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _validate_storage_config(self) -> StorageSettings:
        """Require the selected storage provider's own settings.

        A misconfigured provider is caught here rather than at first upload,
        so an incomplete deployment fails to boot instead of accepting
        documents it cannot store.
        """
        if self.PROVIDER is StorageProvider.S3:
            missing = [
                name
                for name, value in (
                    ("S3_BUCKET", self.S3_BUCKET),
                    ("S3_REGION", self.S3_REGION),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    f"{', '.join(missing)} required when "
                    f"STORAGE_PROVIDER is {StorageProvider.S3}."
                )
        elif self.PROVIDER is StorageProvider.GCS:
            if not self.GCS_BUCKET:
                raise ValueError(
                    f"GCS_BUCKET required when "
                    f"STORAGE_PROVIDER is {StorageProvider.GCS}."
                )
        elif self.LOCAL_DIR is None:
            raise ValueError(
                f"STORAGE_LOCAL_DIR required when "
                f"STORAGE_PROVIDER is {StorageProvider.LOCAL}."
            )
        return self

    @computed_field
    @property
    def MAX_DOCUMENT_SIZE_BYTES(self) -> int:
        return self.MAX_DOCUMENT_SIZE_MB * 1024 * 1024


__all__ = ["StorageSettings"]
