# backend/app/features/cashout/submissions/model.py

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.models import Base, enum_column

from .types import CashoutSubmissionStatus

if TYPE_CHECKING:
    from app.features.cashout.data.model import CashoutData
    from app.features.cashout.documents.model import CashoutDocument
    from app.features.users.model import User


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
    # user's cashout). Bookkeeping only: no relationship until a consumer
    # needs it.
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Soft-delete marker: a submission with traces (documents, data, or a
    # completion on record) is stamped rather than removed, so its history —
    # and every user FK on it — stays intact. NULL means the row is live.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # When the cashout was completed for the first time — set once, never
    # overwritten (unlike completed_by_user_id it survives unsubmit), and the
    # marker that blocks hard deletion. Last to match the migrations' physical
    # column order.
    first_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Two FKs point at users; the relationship must name the employee's.
    employee: Mapped[User] = relationship(
        foreign_keys="CashoutSubmission.employee_user_id"
    )

    documents: Mapped[list[CashoutDocument]] = relationship(
        back_populates="cashout_submission", cascade="all, delete-orphan"
    )
    data: Mapped[CashoutData | None] = relationship(
        back_populates="submission", passive_deletes="all"
    )
