# backend/app/features/invitations/model.py

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.models import Entity


class Invitation(Entity):
    __tablename__ = "invitations"
    # Name the unique index explicitly: invitations/errors.py maps it to
    # INVITATION_EXISTS, and a unique-index violation reports the index name.
    __table_args__ = (Index("ix_invitations_email", "email", unique=True),)

    email: Mapped[str] = mapped_column(String(255), nullable=False)

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
