# backend/app/features/cashout/models/data.py

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.models import Entity

if TYPE_CHECKING:
    from .submission import CashoutSubmission


class CashoutData(Entity):
    """The reconciled result of a completed cashout.

    Built from the submission's verified document analyses when the cashout is
    completed.
    """

    __tablename__ = "cashout_data"

    # TODO(document-ai): placeholder columns. The real reconciled fields depend
    # on the per-document extraction schemas (still dummy) — replace these once
    # those are defined, and fill them in service._reconcile.
    daily_tipout: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    net_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    cash_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    card_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cashout_submissions.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    submission: Mapped[CashoutSubmission] = relationship(back_populates="data")
