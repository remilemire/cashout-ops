# backend/app/features/cashout/extraction/types.py

from __future__ import annotations

from enum import StrEnum


# The document types the AI can classify a cashout document as. UNKNOWN is the
# explicit "none of the above": the model may pick it directly, and the
# processor folds a null classification into it — so a completed analysis
# always has a classification.
class CashoutDocumentClassification(StrEnum):
    TOUCHBISTRO_SERVER_SHIFT_REPORT = "touchbistro_server_shift_report"
    PAYSTONE_TERMINAL_REPORT = "paystone_terminal_report"
    PAYMENT_RECEIPT = "payment_receipt"
    DAILY_TIP_OUT_SHEET = "daily_tip_out_sheet"
    DAILY_CASH_SUMMARY = "daily_cash_summary"
    MANUAL_NOTE = "manual_note"
    UNKNOWN = "unknown"


__all__ = ["CashoutDocumentClassification"]
