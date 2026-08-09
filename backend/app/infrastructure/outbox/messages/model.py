# backend/app/infrastructure/outbox/messages/model.py

from __future__ import annotations

from app.infrastructure.db.models import Base


class OutboxMessage(Base):
    pass

    # AGENT:
    # id
    # created_at
    # claim_id
    # lease_expires_at
    # completed_at
    # is_locked
    # attempts
    # max_attempts
    # last_error


__all__ = ["OutboxMessage"]
