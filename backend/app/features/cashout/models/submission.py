# backend/app/features/cashout/models/submission.py

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.features.cashout.types import CashoutSubmissionStatus
from app.infrastructure.db.models import Base, enum_column

if TYPE_CHECKING:
    from app.features.users.model import User

    from .data import CashoutData
    from .document import CashoutDocument


class CashoutSubmission(Base):
    __tablename__ = "cashout_submissions"

    status: Mapped[CashoutSubmissionStatus] = mapped_column(
        enum_column(CashoutSubmissionStatus, "cashout_submission_status"),
        nullable=False,
        default=CashoutSubmissionStatus.PROCESSING,
        server_default=CashoutSubmissionStatus.PROCESSING.value,
    )

    employee_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Last to match the migrations' column order (metadata orders columns by
    # declaration, and the inherited Entity columns used to land last).
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Who performed the most recent completion (an admin can complete another
    # user's cashout), and who completed it first — set once, never
    # overwritten. Bookkeeping only: no relationships until a consumer needs
    # them.
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    first_completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Three FKs point at users; the relationship must name the employee's.
    employee: Mapped[User] = relationship(
        foreign_keys="CashoutSubmission.employee_user_id"
    )

    documents: Mapped[list[CashoutDocument]] = relationship(
        back_populates="cashout_submission", cascade="all, delete-orphan"
    )
    data: Mapped[CashoutData | None] = relationship(
        back_populates="submission", passive_deletes="all"
    )
