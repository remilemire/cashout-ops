from __future__ import annotations

from enum import StrEnum
from typing import Any


class _ProviderEnum(StrEnum):
    """Base for the provider selectors read from the environment.

    Lookup is case-insensitive so a deployment configured the historical way
    (`STORAGE_PROVIDER=S3`) still boots after the values became snake_case;
    `_missing_` covers pydantic's parse and every other by-value lookup.
    """

    @classmethod
    def _missing_(cls, value: object) -> Any:
        if isinstance(value, str):
            return cls.__members__.get(value.upper().replace("-", "_"))
        return None


class AIProvider(_ProviderEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"


class EmailProvider(_ProviderEnum):
    CONSOLE = "console"
    RESEND = "resend"


class StorageProvider(_ProviderEnum):
    LOCAL = "local"
    S3 = "s3"


__all__ = ["AIProvider", "EmailProvider", "StorageProvider"]
