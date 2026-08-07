# backend/app/features/cashout/models/submission.py

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.features.cashout.types import CashoutSubmissionStatus
from app.infrastructure.db.models import Entity, enum_column

if TYPE_CHECKING:
    from app.features.users.model import User

    from .data import CashoutData
    from .document import CashoutDocument


class CashoutSubmission(Entity):
    __tablename__ = "cashout_submissions"

    status: Mapped[CashoutSubmissionStatus] = mapped_column(
        enum_column(CashoutSubmissionStatus, "cashout_submission_status"),
        nullable=False,
        default=CashoutSubmissionStatus.PROCESSING,
        server_default=CashoutSubmissionStatus.PROCESSING.value,
    )

    submitted_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    submitted_by: Mapped[User] = relationship()

    documents: Mapped[list[CashoutDocument]] = relationship(
        back_populates="cashout_submission", cascade="all, delete-orphan"
    )
    data: Mapped[CashoutData | None] = relationship(
        back_populates="submission", passive_deletes="all"
    )
