from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, PlainSerializer

from app.lib.casing import snake_to_camel


# Database timezone is UTC; serialize as ISO-8601 with a trailing Z.
def _serialize_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


UtcDateTime = Annotated[
    datetime, PlainSerializer(_serialize_utc, return_type=str, when_used="json")
]


def normalize_email(email: str) -> str:
    """Lowercase an email address for this application's account matching policy.

    The application intentionally treats both local part and domain as
    case-insensitive. Apply this at input boundaries so storage and lookups
    use the same form.
    """
    return email.lower()


# Use in place of EmailStr on anything that accepts an address from outside.
NormalizedEmail = Annotated[EmailStr, AfterValidator(normalize_email)]


class BaseOut(BaseModel):
    # validate_by_name lets model_validate() read snake_case ORM attributes;
    # serialization still emits camelCase via by_alias (FastAPI's default).
    model_config = ConfigDict(
        alias_generator=snake_to_camel,
        from_attributes=True,
        validate_by_name=True,
    )


class BaseIn(BaseModel):
    model_config = ConfigDict(
        alias_generator=snake_to_camel, validate_by_name=True, extra="forbid"
    )


__all__ = ["NormalizedEmail", "UtcDateTime", "BaseOut", "BaseIn", "normalize_email"]
