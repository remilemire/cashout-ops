# backend/app/features/cashout/data/model.py

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ARRAY, Computed, DateTime, ForeignKey, Numeric, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.models import Base, enum_column

from .types import TipoutDepartment

if TYPE_CHECKING:
    from app.features.cashout.submissions.model import CashoutSubmission


class CashoutData(Base):
    """The reconciled result of a completed cashout.

    Built from the submission's verified document analyses when the cashout is
    completed.
    """

    __tablename__ = "cashout_data"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

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

    # Extracted / source values, reconciled off the verified analyses (see
    # data/reconciliation.py). NOT NULL: a cashout that cannot be reconciled
    # fails to complete, so a row exists only once all six are known.
    food_net_sales: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    drink_net_sales: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_net_sales: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    card_payment_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cash_payment_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    card_tip_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # User-selected business inputs: which departments this cashout tips
    # out to. A department left out keeps its tipout column null, so this
    # list and those columns say the same thing two ways.
    tipout_departments: Mapped[list[TipoutDepartment]] = mapped_column(
        ARRAY(enum_column(TipoutDepartment, "tipout_department")),
        nullable=False,
        default=list,
    )

    # Calculated values
    bar_tipout: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        Computed("""
            CASE
                WHEN 'bar'::tipout_department = ANY(tipout_departments)
                THEN drink_net_sales * bar_tipout_rate
                ELSE NULL
            END
        """),
        nullable=True,
    )
    kitchen_tipout: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        Computed("""
            CASE
                WHEN 'kitchen'::tipout_department = ANY(tipout_departments)
                THEN food_net_sales * kitchen_tipout_rate
                ELSE NULL
            END
        """),
        nullable=True,
    )
    expo_tipout: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        Computed("""
            CASE
                WHEN 'expo'::tipout_department = ANY(tipout_departments)
                THEN total_net_sales * expo_tipout_rate
                ELSE NULL
            END
        """),
        nullable=True,
    )
    host_tipout: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        Computed("""
            CASE
                WHEN 'host'::tipout_department = ANY(tipout_departments)
                THEN total_net_sales * host_tipout_rate
                ELSE NULL
            END
        """),
        nullable=True,
    )

    cash_owed_to_house: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        Computed("""
            CASE
                WHEN cash_payment_total > card_tip_total
                THEN cash_payment_total - card_tip_total
                ELSE NULL
            END
        """),
        nullable=True,
    )

    cash_owed_to_employee: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        Computed("""
            CASE
                WHEN card_tip_total > cash_payment_total
                THEN card_tip_total - cash_payment_total
                ELSE NULL
            END
        """),
        nullable=True,
    )

    # Tipout-rate snapshots: the rates in force when this cashout closed,
    # copied off settings.tipout so a later rate change cannot restate it.
    #
    # Numeric(6, 4), not (12, 2): these are fractions of sales, not amounts, so
    # cent precision would round a 3.5% rate (0.0350) to 4%.
    bar_tipout_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    kitchen_tipout_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    expo_tipout_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    host_tipout_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)

    submission: Mapped[CashoutSubmission] = relationship(back_populates="data")
