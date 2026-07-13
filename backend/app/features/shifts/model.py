# backend/app/features/shifts/model.py

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.models import Entity, enum_column

from .types import ShiftStatus

if TYPE_CHECKING:
    from app.features.cashout.models import CashoutSubmission
    from app.features.users.model import User


class Shift(Entity):
    __tablename__ = "shifts"

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    status: Mapped[ShiftStatus] = mapped_column(
        enum_column(ShiftStatus, "shift_status"),
        nullable=False,
        default=ShiftStatus.ACTIVE,
        server_default=ShiftStatus.ACTIVE.value,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user: Mapped[User] = relationship(back_populates="shifts")

    cashout_submission: Mapped[CashoutSubmission | None] = relationship(
        back_populates="shift"
    )
