# backend/app/features/users/model.py

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.models import Entity, enum_column

from .types import UserRole

if TYPE_CHECKING:
    from app.features.sessions.model import Session


class User(Entity):
    __tablename__ = "users"
    # Name the unique index explicitly: users/errors.py maps it to EMAIL_TAKEN,
    # and a unique-index violation reports the index name.
    __table_args__ = (Index("ix_users_email", "email", unique=True),)

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[UserRole] = mapped_column(
        enum_column(UserRole, "user_role"),
        nullable=False,
        default=UserRole.CASHIER,
        server_default=UserRole.CASHIER.value,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # Null until the emailed verification code is entered; the frontend gates
    # unverified accounts. The bootstrapped admin is created already verified.
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sessions: Mapped[list[Session]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
