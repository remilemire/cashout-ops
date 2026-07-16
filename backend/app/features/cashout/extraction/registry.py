# backend/app/features/cashout/extraction/registry.py

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

# Classifications without a schema (UNKNOWN) are not domain errors: the
# processor returns them with no data and the cashout service persists a
# failed, reviewable analysis instead.

__all__ = ["CASHOUT_DOCUMENT_SCHEMAS"]
