# backend/app/features/auth/email_challenges/model.py

from __future__ import annotations

from pydantic import BaseModel, EmailStr


class StoredEmailChallenge(BaseModel):
    """A pending email challenge as persisted in Redis.

    A challenge belongs to an address, not to a user row: the bootstrapped
    owner has no account until its challenge is consumed, and the address is
    what the link is emailed to. `service.consume_code` resolves the account.

    Code attempts are not tracked here: the guess cap lives in a separate
    atomic Redis counter (see ``store.count_code_attempt``), because a
    counter inside this JSON would be a racy read-modify-write.
    """

    email: EmailStr
    token_hash: str | None = None
    code_hash: str | None = None


__all__ = ["StoredEmailChallenge"]
