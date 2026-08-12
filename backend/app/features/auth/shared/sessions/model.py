# backend/app/features/auth/shared/sessions/model.py

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from pydantic import BaseModel

from app.core.config import settings

# Single source for the session lifetime: the store's Redis TTL, the cookie
# max-age, and `expires_at` all derive from it.
SESSION_TTL = timedelta(days=settings.auth.SESSION_TTL_DAYS)


class Session(BaseModel):
    """A live session as persisted in Redis, keyed by its token hash.

    Expiry is enforced by the Redis TTL; `expires_at` mirrors it for
    introspection rather than acting as the source of truth.
    """

    user_id: UUID
    issued_at: datetime
    expires_at: datetime


__all__ = ["SESSION_TTL", "Session"]
