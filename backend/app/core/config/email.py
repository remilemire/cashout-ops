# backend/app/core/config/email.py

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import SettingsConfigDict

from app.core.providers import EmailProvider

from .base import SettingsGroup


class EmailSettings(SettingsGroup):
    """Email delivery.

    PROVIDER selects the client: CONSOLE logs the message (dev default; boots
    without a key), RESEND sends for real and requires RESEND_API_KEY
    (validated here). FROM is the sender.
    """

    model_config = SettingsConfigDict(env_prefix="EMAIL_")

    PROVIDER: EmailProvider = EmailProvider.CONSOLE
    # Unprefixed: the vendor's own conventional variable name.
    RESEND_API_KEY: str | None = Field(default=None, validation_alias="RESEND_API_KEY")
    FROM: str = "Whiskey District <onboarding@resend.dev>"

    @model_validator(mode="after")
    def _validate_email_config(self) -> EmailSettings:
        """Require the selected email provider's own settings."""
        if self.PROVIDER is EmailProvider.RESEND and not self.RESEND_API_KEY:
            raise ValueError(
                f"RESEND_API_KEY required when EMAIL_PROVIDER is {EmailProvider.RESEND}."
            )
        return self


__all__ = ["EmailSettings"]
