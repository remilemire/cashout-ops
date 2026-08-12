# backend/app/core/config/storage.py

from __future__ import annotations

from pathlib import Path

from pydantic import Field, computed_field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

from app.core.providers import StorageProvider

from .base import SettingsGroup


class StorageSettings(SettingsGroup):
    """Document storage.

    PROVIDER selects the client: LOCAL writes under LOCAL_DIR, S3 stores
    objects in S3_BUCKET. Each provider's own settings are required when it is
    selected and ignored otherwise, so both groups default to None and
    _validate_storage_config enforces the selected one. AWS credentials are not
    modeled here; they come from the standard AWS chain (env vars, profile,
    instance role).
    """

    model_config = SettingsConfigDict(env_prefix="STORAGE_")

    PROVIDER: StorageProvider = StorageProvider.LOCAL
    LOCAL_DIR: Path | None = None
    # Unprefixed: these sit alongside the AWS chain's own variables.
    S3_BUCKET: str | None = Field(default=None, validation_alias="S3_BUCKET")
    S3_REGION: str | None = Field(default=None, validation_alias="S3_REGION")

    # Upload ceiling for a single document, in megabytes. The upload endpoint
    # stops reading a request body once it passes this, and the service rejects
    # the upload (DOCUMENT_TOO_LARGE). Configured in MB because that is how the
    # limit is communicated to users; code reads MAX_DOCUMENT_SIZE_BYTES.
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
