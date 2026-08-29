# backend/app/core/config/auth.py

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import SettingsConfigDict

from .base import SettingsGroup


class AuthSettings(SettingsGroup):
    model_config = SettingsConfigDict(env_prefix="AUTH_")

    SESSION_TTL_DAYS: int = 7
    # Email challenges. A sign-in link is emailed on login; the challenge (and
    # with it the link and its one-time code) expires this long after initiation.
    CHALLENGE_TTL_MINUTES: int = 15
    # Minimum duration of every email-challenge response. Real and decoy flows
    # do different amounts of work; padding both to a shared floor keeps
    # response timing from revealing whether an account exists. Must exceed the
    # real path's tail latency (not its average) — including the request's
    # database commit, which runs inside the floor — or the tail still leaks.
    # 0 disables the floor.
    CHALLENGE_TIME_FLOOR_MS: int = Field(default=100, ge=0)
    # OAuth sign-in. A flow — its Redis state and the `oauth_flow` cookie —
    # expires this long after /start; a user who parks on the issuer's
    # consent screen longer simply retries.
    OAUTH_FLOW_TTL_MINUTES: int = 10

    # Google OAuth sign-in credentials. There is no issuer-selection setting:
    # enablement is derived, so Google sign-in is on exactly when both are set
    # (integrations/oauth's `enabled_issuers`). Unprefixed: Google's own
    # conventional variable names.
    GOOGLE_CLIENT_ID: str | None = Field(
        default=None, validation_alias="GOOGLE_CLIENT_ID"
    )
    GOOGLE_CLIENT_SECRET: str | None = Field(
        default=None, validation_alias="GOOGLE_CLIENT_SECRET"
    )

    @model_validator(mode="after")
    def _validate_google_oauth(self) -> AuthSettings:
        """Reject a half-configured Google credential pair.

        Enablement derives from the pair being present, so one variable
        without the other is always a deployment mistake — fail at boot
        rather than silently leaving Google sign-in off.
        """
        pair = {
            "GOOGLE_CLIENT_ID": self.GOOGLE_CLIENT_ID,
            "GOOGLE_CLIENT_SECRET": self.GOOGLE_CLIENT_SECRET,
        }
        missing = [name for name, value in pair.items() if not value]
        if len(missing) == 1:
            [present] = (name for name, value in pair.items() if value)
            raise ValueError(f"{missing[0]} required when {present} is set.")
        return self


__all__ = ["AuthSettings"]
