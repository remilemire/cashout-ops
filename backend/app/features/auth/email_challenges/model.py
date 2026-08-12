# backend/app/features/auth/email_challenges/model.py

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class StoredEmailChallenge(BaseModel):
    """A pending email challenge as persisted in Redis.

    Code attempts are not tracked here: the guess cap lives in a separate
    atomic Redis counter (see ``store.count_code_attempt``), because a
    counter inside this JSON would be a racy read-modify-write.
    """

    user_id: UUID
    token_hash: str | None = None
    code_hash: str | None = None


__all__ = ["StoredEmailChallenge"]
