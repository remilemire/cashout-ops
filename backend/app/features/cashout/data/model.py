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


def _round_for_house_sql(expression: str) -> str:
    """Round a signed dollar expression to cents in the house's favour."""
    return f"(ceil(({expression}) * 100) / 100)"


_BAR_TIPOUT_SQL = _round_for_house_sql("drink_net_sales * bar_tipout_rate")
_KITCHEN_TIPOUT_SQL = _round_for_house_sql("food_net_sales * kitchen_tipout_rate")
_EXPO_TIPOUT_SQL = _round_for_house_sql("food_net_sales * expo_tipout_rate")
_HOST_TIPOUT_SQL = _round_for_house_sql("total_net_sales * host_tipout_rate")
_MANAGER_TIPOUT_SQL = _round_for_house_sql("total_net_sales * manager_tipout_rate")

_TOTAL_TIPOUT_SQL = """
    (
        CASE
            WHEN 'bar'::tipout_department = ANY(tipout_departments)
            THEN {bar_tipout}
            ELSE 0
        END
        + CASE
            WHEN 'kitchen'::tipout_department = ANY(tipout_departments)
            THEN {kitchen_tipout}
            ELSE 0
        END
        + CASE
            WHEN 'expo'::tipout_department = ANY(tipout_departments)
            THEN {expo_tipout}
            ELSE 0
        END
        + CASE
            WHEN 'host'::tipout_department = ANY(tipout_departments)
            THEN {host_tipout}
            ELSE 0
        END
        + CASE
            WHEN 'manager'::tipout_department = ANY(tipout_departments)
            THEN {manager_tipout}
            ELSE 0
        END
    )
""".format(
    bar_tipout=_BAR_TIPOUT_SQL,
    kitchen_tipout=_KITCHEN_TIPOUT_SQL,
    expo_tipout=_EXPO_TIPOUT_SQL,
    host_tipout=_HOST_TIPOUT_SQL,
    manager_tipout=_MANAGER_TIPOUT_SQL,
)

_UNROUNDED_CASH_DUE_TO_HOUSE_SQL = f"""
    (cash_payment_total - card_tip_total + {_TOTAL_TIPOUT_SQL})
"""
_CASH_DUE_TO_HOUSE_SQL = _round_for_house_sql(_UNROUNDED_CASH_DUE_TO_HOUSE_SQL)


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

    # Which departments this cashout tips out to: the cashier's selection
    # plus the manager, which service.reconcile adds to every cashout. A
    # department left out keeps its tipout column null, so this list and
    # those columns say the same thing two ways.
    tipout_departments: Mapped[list[TipoutDepartment]] = mapped_column(
        ARRAY(enum_column(TipoutDepartment, "tipout_department")),
        nullable=False,
        default=list,
    )

    # Calculated values
    bar_tipout: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        Computed(f"""
            CASE
                WHEN 'bar'::tipout_department = ANY(tipout_departments)
                THEN {_BAR_TIPOUT_SQL}
                ELSE NULL
            END
        """),
        nullable=True,
    )
    kitchen_tipout: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        Computed(f"""
            CASE
                WHEN 'kitchen'::tipout_department = ANY(tipout_departments)
                THEN {_KITCHEN_TIPOUT_SQL}
                ELSE NULL
            END
        """),
        nullable=True,
    )
    expo_tipout: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        Computed(f"""
            CASE
                WHEN 'expo'::tipout_department = ANY(tipout_departments)
                THEN {_EXPO_TIPOUT_SQL}
                ELSE NULL
            END
        """),
        nullable=True,
    )
    host_tipout: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        Computed(f"""
            CASE
                WHEN 'host'::tipout_department = ANY(tipout_departments)
                THEN {_HOST_TIPOUT_SQL}
                ELSE NULL
            END
        """),
        nullable=True,
    )
    manager_tipout: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        Computed(f"""
            CASE
                WHEN 'manager'::tipout_department = ANY(tipout_departments)
                THEN {_MANAGER_TIPOUT_SQL}
                ELSE NULL
            END
        """),
        nullable=True,
    )

    cash_owed_to_house: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        Computed(f"""
            CASE
                WHEN {_CASH_DUE_TO_HOUSE_SQL} > 0
                THEN {_CASH_DUE_TO_HOUSE_SQL}
                ELSE NULL
            END
        """),
        nullable=True,
    )

    cash_owed_to_employee: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        Computed(f"""
            CASE
                WHEN {_CASH_DUE_TO_HOUSE_SQL} < 0
                THEN -{_CASH_DUE_TO_HOUSE_SQL}
                ELSE NULL
            END
        """),
        nullable=True,
    )

    # Tipout-rate snapshots: the five rates in force when this cashout closed,
    # copied off settings.tipout so a later rate change cannot restate it.
    #
    # Numeric(6, 4), not (12, 2): these are fractions of sales, not amounts, so
    # cent precision would round a 3.5% rate (0.0350) to 4%.
    bar_tipout_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    kitchen_tipout_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    expo_tipout_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    host_tipout_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    manager_tipout_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)

    submission: Mapped[CashoutSubmission] = relationship(back_populates="data")
