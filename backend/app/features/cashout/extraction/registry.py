from __future__ import annotations

from collections.abc import Mapping

from ..types import CashoutDocumentType
from .schemas import (
    CashoutDocumentSchema,
    DailyCashSummaryData,
    DailyTipOutSheetData,
    ManualNoteData,
    PaymentReceiptData,
    PaystoneTerminalReportData,
    TouchBistroServerShiftReportData,
)

CASHOUT_DOCUMENT_SCHEMAS: Mapping[CashoutDocumentType, type[CashoutDocumentSchema]] = {
    CashoutDocumentType.TOUCHBISTRO_SERVER_SHIFT_REPORT: (
        TouchBistroServerShiftReportData
    ),
    CashoutDocumentType.PAYSTONE_TERMINAL_REPORT: PaystoneTerminalReportData,
    CashoutDocumentType.PAYMENT_RECEIPT: PaymentReceiptData,
    CashoutDocumentType.DAILY_TIP_OUT_SHEET: DailyTipOutSheetData,
    CashoutDocumentType.DAILY_CASH_SUMMARY: DailyCashSummaryData,
    CashoutDocumentType.MANUAL_NOTE: ManualNoteData,
}

# TODO(document-ai): Decide whether UNKNOWN and low-confidence classifications
# are persisted as reviewable results or raised as domain errors.

__all__ = ["CASHOUT_DOCUMENT_SCHEMAS"]
