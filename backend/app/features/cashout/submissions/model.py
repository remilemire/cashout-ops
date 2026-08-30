# backend/app/features/cashout/submissions/model.py

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import ARRAY, Date, DateTime, ForeignKey, Index, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.features.cashout.data.types import TipoutDepartment
from app.infrastructure.db.models import Base, enum_column

from .types import CashoutSubmissionStatus

if TYPE_CHECKING:
    from app.features.cashout.data.model import CashoutData
    from app.features.cashout.documents.model import CashoutDocument
    from app.features.users.model import User


class CashoutSubmission(Base):
    __tablename__ = "cashout_submissions"
    # Name the unique index explicitly: cashout/errors.py maps it to
    # SUBMISSION_DUPLICATE_DAY, and a unique-index violation reports the index
    # name. Partial — live rows only — so a cancelled (soft-deleted) cashout
    # doesn't block opening a new one for the same day.
    __table_args__ = (
        Index(
            "ix_cashout_submissions_employee_business_date",
            "employee_user_id",
            "business_date",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

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

    # The day the cashout is for — distinct from submitted_at (when it was
    # opened): a cashier closing out after midnight or catching up a missed
    # day picks yesterday. Indexed: reporting filters on it.
    business_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Who performed the most recent completion (an admin can complete another
    # user's cashout). Bookkeeping only: no relationship until a consumer
    # needs it.
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )

    # When the cashout was completed for the first time — set once, never
    # overwritten (unlike completed_by_user_id it survives unsubmit), and the
    # marker that blocks hard deletion.
    first_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # The departments chosen at the most recent completion — written on
    # complete and deliberately kept through unsubmit, so re-completion starts
    # from the previous choice. NULL means never completed. The authoritative
    # copy for a completed cashout stays on its CashoutData row.
    tipout_departments: Mapped[list[TipoutDepartment] | None] = mapped_column(
        ARRAY(enum_column(TipoutDepartment, "tipout_department")), nullable=True
    )

    # Soft-delete marker: a submission with traces (documents, data, or a
    # completion on record) is stamped rather than removed, so its history —
    # and every user FK on it — stays intact. NULL means the row is live.
    deleted_at: Mapped[datetime | None] = mapped_column(
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
