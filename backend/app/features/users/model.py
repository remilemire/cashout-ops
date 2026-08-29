# backend/app/features/users/model.py

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.models import Base, enum_column

from .types import UserRole


class User(Base):
    __tablename__ = "users"
    # Name the unique indexes explicitly: users/errors.py maps them (email →
    # EMAIL_TAKEN, single-owner → OWNER_ALREADY_EXISTS), and a unique-index
    # violation reports the index name.
    __table_args__ = (
        Index("ix_users_email", "email", unique=True),
        Index(
            "ix_users_single_owner",
            "role",
            unique=True,
            postgresql_where=text("role = 'owner'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)

    email: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[UserRole] = mapped_column(
        enum_column(UserRole, "user_role"),
        nullable=False,
        default=UserRole.STAFF,
        server_default=UserRole.STAFF.value,
    )

    # Soft-delete marker: a user with cashout submissions is deactivated by
    # setting this instead of being removed, so their submissions keep a valid
    # author; NULL means the account is live.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
