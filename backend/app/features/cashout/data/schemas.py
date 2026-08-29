# backend/app/features/cashout/data/schemas.py

from __future__ import annotations

import uuid
from decimal import Decimal

from app.core.schemas import BaseOut, UtcDateTime

from .types import TipoutDepartment


class CashoutDataOut(BaseOut):
    id: uuid.UUID
    created_at: UtcDateTime

    # Reconciled off the verified analyses. Null on a cashout completed before
    # reconciliation was implemented — see service.reconcile.
    food_net_sales: Decimal | None = None
    drink_net_sales: Decimal | None = None
    total_net_sales: Decimal | None = None
    card_payment_total: Decimal | None = None
    cash_payment_total: Decimal | None = None
    card_tip_total: Decimal | None = None

    # Which departments this cashout tipped out to, and the rates it closed
    # against — kept so the figures below can be explained after the fact,
    # even once the configured rates have moved on.
    tipout_departments: list[TipoutDepartment]
    bar_tipout_rate: Decimal
    kitchen_tipout_rate: Decimal
    expo_tipout_rate: Decimal
    host_tipout_rate: Decimal

    # Database-generated. Null for a department that was not tipped out, and
    # for every department while the source figures above are null.
    bar_tipout: Decimal | None = None
    kitchen_tipout: Decimal | None = None
    expo_tipout: Decimal | None = None
    host_tipout: Decimal | None = None

    # Exactly one side is set: whichever way the cash/card-tip balance fell.
    cash_owed_to_house: Decimal | None = None
    cash_owed_to_employee: Decimal | None = None

    submission_id: uuid.UUID


__all__ = ["CashoutDataOut"]
