# backend/app/infrastructure/outbox/messages/model.py

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.models import Base


class OutboxMessage(Base):
    """A deferred job persisted inside the transaction that requested it.

    Dispatcher workers claim rows under a lease (`claim_id` +
    `lease_expires_at`); a crashed worker's lease simply expires and the row
    becomes claimable again, so delivery is at-least-once and handlers must
    tolerate replays. A row is terminal once `completed_at` (handled) or
    `dead_lettered_at` (attempts exhausted, or the message is undeliverable)
    is set.
    """

    __tablename__ = "outbox_messages"
    # The dispatcher's claim query scans pending rows by eligibility time;
    # terminal rows are excluded so the index stays small.
    __table_args__ = (
        Index(
            "ix_outbox_messages_pending",
            "available_at",
            "created_at",
            postgresql_where=text("completed_at IS NULL AND dead_lettered_at IS NULL"),
        ),
    )

    type: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Earliest next attempt; pushed forward by the retry backoff on failure.
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    claim_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    # Null means the dispatcher's configured default applies.
    max_attempts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dead_lettered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Last to match the other models' column order.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


__all__ = ["OutboxMessage"]
