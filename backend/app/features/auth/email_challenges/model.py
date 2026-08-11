# backend/app/features/auth/email_challenges/model.py

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class StoredEmailChallenge(BaseModel):
    """A pending email challenge as persisted in Redis.

    ``code_attempts`` counts wrong-code guesses from the initiating tab;
    reaching the cap destroys the challenge outright.
    """

    user_id: UUID
    token_hash: str | None = None
    code_hash: str | None = None
    code_attempts: int = 0


__all__ = ["StoredEmailChallenge"]
