# backend/app/features/cashout/data/errors.py

from __future__ import annotations

from typing import Literal

from app.core.errors import ErrorDefinition, ErrorDefinitionList

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

# The messages are the whole explanation the cashier gets: AppError messages
# stay internal, so each one has to say what does not add up and what to look
# at, without the figures themselves.
error_definition_list: ErrorDefinitionList[ErrorCode] = [
    ErrorDefinition(
        code="RECONCILE_TOUCHBISTRO_MISSING",
        kind="CONFLICT",
        message="Add the TouchBistro end-of-day report before completing.",
    ),
    ErrorDefinition(
        code="RECONCILE_TOUCHBISTRO_DUPLICATE",
        kind="CONFLICT",
        message="A cashout takes exactly one TouchBistro end-of-day report.",
    ),
    ErrorDefinition(
        code="RECONCILE_CARD_PAYMENT_MISMATCH",
        kind="CONFLICT",
        message=(
            "The TouchBistro card payments do not match the server summary"
            " grand totals. Re-check both before completing."
        ),
    ),
    ErrorDefinition(
        code="RECONCILE_CARD_TRANSACTION_MISMATCH",
        kind="CONFLICT",
        message=(
            "The TouchBistro card orders do not match the server summary"
            " transaction counts. Re-check both before completing."
        ),
    ),
    ErrorDefinition(
        code="RECONCILE_DOCUMENT_DATA_INVALID",
        kind="CONFLICT",
        message=(
            "A document's verified details cannot be read. Re-verify it and try again."
        ),
    ),
]

__all__ = ["ErrorCode", "error_definition_list"]
