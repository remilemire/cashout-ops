# backend/app/features/cashout/data/schemas.py

from __future__ import annotations

import uuid
from decimal import Decimal

from app.core.schemas import BaseOut, UtcDateTime


class CashoutDataOut(BaseOut):
    id: uuid.UUID
    created_at: UtcDateTime
    # TODO(document-ai): placeholder reconciled fields; see model.py.
    daily_tipout: Decimal | None = None
    net_total: Decimal | None = None
    cash_total: Decimal | None = None
    card_total: Decimal | None = None
    submission_id: uuid.UUID


__all__ = ["CashoutDataOut"]
