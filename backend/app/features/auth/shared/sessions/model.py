# backend/app/features/auth/shared/sessions/model.py

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class Session(BaseModel):
    """A live session as persisted in Redis, keyed by its token hash.

    Expiry is enforced by the Redis TTL; `expires_at` mirrors it for
    introspection rather than acting as the source of truth.
    """

    user_id: UUID
    issued_at: datetime
    expires_at: datetime


__all__ = ["Session"]
