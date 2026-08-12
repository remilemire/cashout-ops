# backend/app/core/config/bootstrap.py

from __future__ import annotations

from pydantic import EmailStr
from pydantic_settings import SettingsConfigDict

from .base import SettingsGroup


class BootstrapSettings(SettingsGroup):
    """Identity of the owner account a fresh deployment creates for itself."""

    model_config = SettingsConfigDict(env_prefix="BOOTSTRAP_")

    OWNER_EMAIL: EmailStr = "owner@test.com"
    # Full name given to the OWNER_EMAIL account when a first passwordless
    # sign-in bootstraps it as the owner (no registration form supplies one).
    OWNER_FULL_NAME: str = "Owner"


__all__ = ["BootstrapSettings"]
