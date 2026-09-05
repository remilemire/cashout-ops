# backend/app/features/cashout/data/schemas.py

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.core.schemas import BaseOut, UtcDateTime
from app.features.users.schemas import UserOut

from .types import TipoutDepartment


class CashoutDataOut(BaseOut):
    id: uuid.UUID
    created_at: UtcDateTime

    # Reconciled off the verified analyses; always present, since a cashout
    # that cannot be reconciled never completes — see service.reconcile.
    food_net_sales: Decimal
    drink_net_sales: Decimal
    total_net_sales: Decimal
    card_payment_total: Decimal
    cash_payment_total: Decimal
    card_tip_total: Decimal

    # Which departments this cashout tipped out to (the selection plus the
    # manager, who tips out on every cashout), and the rates it closed
    # against — kept so the figures below can be explained after the fact,
    # even once the configured rates have moved on.
    tipout_departments: list[TipoutDepartment]
    bar_tipout_rate: Decimal
    kitchen_tipout_rate: Decimal
    expo_tipout_rate: Decimal
    host_tipout_rate: Decimal
    manager_tipout_rate: Decimal

    # Database-generated. Null for a department that was not tipped out.
    bar_tipout: Decimal | None = None
    kitchen_tipout: Decimal | None = None
    expo_tipout: Decimal | None = None
    host_tipout: Decimal | None = None
    manager_tipout: Decimal | None = None

    # At most one side is set: whichever way the cash/card-tip balance falls
    # after adding the tipouts (neither, on the exact tie).
    cash_owed_to_house: Decimal | None = None
    cash_owed_to_employee: Decimal | None = None

    submission_id: uuid.UUID


class CashoutDataSubmissionOut(BaseOut):
    """The identity half of a data row — who the cashout was for and its day."""

    id: uuid.UUID
    business_date: date
    employee: UserOut


class CashoutDataListOut(CashoutDataOut):
    """The list endpoint's shape. Not part of CashoutDataOut itself: that is
    embedded inside the submission detail, where nesting the submission back
    in would be circular."""

    submission: CashoutDataSubmissionOut


__all__ = [
    "CashoutDataListOut",
    "CashoutDataOut",
    "CashoutDataSubmissionOut",
]
