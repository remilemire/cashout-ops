# backend/app/core/config/outbox.py

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from .base import SettingsGroup


class OutboxSettings(SettingsGroup):
    """Outbox dispatch.

    Workers poll outbox_messages every POLL_INTERVAL; a claim is protected for
    CLAIM_TTL before a crashed worker's row becomes claimable again. Failed
    attempts retry with exponential backoff (BACKOFF_BASE * 2^(attempt-1),
    capped at BACKOFF_CAP) until MAX_ATTEMPTS runs out and the message
    dead-letters.
    """

    model_config = SettingsConfigDict(env_prefix="OUTBOX_")

    MAX_ATTEMPTS: int = 10
    BATCH_SIZE: int = 1
    POLL_INTERVAL_SECONDS: float = 1.0
    CLAIM_TTL_SECONDS: float = 30.0
    BACKOFF_BASE_SECONDS: float = 5.0
    BACKOFF_CAP_SECONDS: float = 900.0


__all__ = ["OutboxSettings"]
