from __future__ import annotations

from typing import Literal

from app.core.errors import ErrorKindMap

# Raised while reconciling a submission's verified analyses into its data row
# — every one of them at completion time, where the cashier can still fix the
# documents behind them.
type ErrorCode = Literal[
    "RECONCILE_TOUCHBISTRO_MISSING",
    "RECONCILE_TOUCHBISTRO_DUPLICATE",
    "RECONCILE_CARD_PAYMENT_MISMATCH",
    "RECONCILE_CARD_TRANSACTION_MISMATCH",
    "RECONCILE_DOCUMENT_DATA_INVALID",
]

error_kind_map: ErrorKindMap[ErrorCode] = {
    "RECONCILE_TOUCHBISTRO_MISSING": "CONFLICT",
    "RECONCILE_TOUCHBISTRO_DUPLICATE": "CONFLICT",
    "RECONCILE_CARD_PAYMENT_MISMATCH": "CONFLICT",
    "RECONCILE_CARD_TRANSACTION_MISMATCH": "CONFLICT",
    "RECONCILE_DOCUMENT_DATA_INVALID": "CONFLICT",
}

__all__ = ["ErrorCode", "error_kind_map"]
