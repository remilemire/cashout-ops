# backend/app/features/users/model.py

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.models import Base


class User(Base):
    __tablename__ = "users"
    # Name the unique index explicitly: users/errors.py maps it to EMAIL_TAKEN,
    # and a unique-index violation reports the index name.
    __table_args__ = (Index("ix_users_email", "email", unique=True),)

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)

    email: Mapped[str] = mapped_column(String(255), nullable=False)

    is_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    # Last to match the migrations' column order (metadata orders columns by
    # declaration, and the inherited Entity columns used to land last).
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
