# backend/app/core/config/bootstrap.py

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from app.core.schemas import NormalizedEmail

from .base import SettingsGroup


class BootstrapSettings(SettingsGroup):
    """Identity of the owner account a fresh deployment creates for itself."""

    model_config = SettingsConfigDict(env_prefix="BOOTSTRAP_")

    # Normalized like every other address, so a deployment that configures
    # Owner@Example.com still matches the owner's sign-in.
    OWNER_EMAIL: NormalizedEmail = "owner@test.com"
    # Full name given to the OWNER_EMAIL account when its first proven
    # sign-in bootstraps it as the owner. No registration form supplies one,
    # and an issuer-supplied profile name is deliberately not used, so the
    # owner's name never depends on which sign-in flow it arrived through.
    OWNER_FULL_NAME: str = "Owner"


__all__ = ["BootstrapSettings"]
