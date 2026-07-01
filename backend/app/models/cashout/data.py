# backend/app/models/cashout/data.py

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Entity

if TYPE_CHECKING:
    from app.models.user import User

    from .submission import CashoutSubmission


class CashoutData(Entity):
    __tablename__ = "cashout_data"

    extracted_data_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    reviewed_data_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )

    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    submission_id: Mapped[int] = mapped_column(
        ForeignKey("cashout_submissions.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    submission: Mapped[CashoutSubmission] = relationship(back_populates="data")

    reviewed_by: Mapped[User | None] = relationship()
