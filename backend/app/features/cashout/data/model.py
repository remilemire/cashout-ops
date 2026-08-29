# backend/app/features/cashout/data/model.py

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.models import Base

if TYPE_CHECKING:
    from app.features.cashout.submissions.model import CashoutSubmission


class CashoutData(Base):
    """The reconciled result of a completed cashout.

    Built from the submission's verified document analyses when the cashout is
    completed.
    """

    __tablename__ = "cashout_data"

    # TODO(document-ai): placeholder columns. The real reconciled fields follow
    # from the per-document extraction schemas — replace these to match, and
    # fill them in this sub-feature's service.reconcile.
    daily_tipout: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    net_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    cash_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    card_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    submission_id: Mapped[uuid.UUID] = mapped_column(
        # Name the FK explicitly: cashout/errors.py maps it to SUBMISSION_HAS_DATA,
        # and the ON DELETE RESTRICT violation reports the constraint name.
        ForeignKey(
            "cashout_submissions.id",
            ondelete="RESTRICT",
            name="cashout_data_submission_id_fkey",
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    # Last to match the migrations' column order (metadata orders columns by
    # declaration, and the inherited Entity columns used to land last).
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    submission: Mapped[CashoutSubmission] = relationship(back_populates="data")
