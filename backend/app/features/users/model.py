# backend/app/features/users/model.py

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.models import Entity


class User(Entity):
    __tablename__ = "users"
    # Name the unique index explicitly: users/errors.py maps it to EMAIL_TAKEN,
    # and a unique-index violation reports the index name.
    __table_args__ = (Index("ix_users_email", "email", unique=True),)

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    is_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # Null until the emailed verification code is entered; the frontend gates
    # unverified accounts. The bootstrapped admin is created already verified.
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
