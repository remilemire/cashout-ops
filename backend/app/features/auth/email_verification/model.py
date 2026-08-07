# backend/app/features/auth/email_verification/model.py

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.models import Entity


class EmailVerification(Entity):
    __tablename__ = "email_verifications"
    # One verification row per user: send_new_code replaces the existing one.
    __table_args__ = (Index("ix_email_verifications_user_id", "user_id", unique=True),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Only the SHA-256 hash of the numeric code is stored; compare by hashing.
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
