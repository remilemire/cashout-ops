# backend/app/features/cashout/extraction/registry.py

from __future__ import annotations

from collections.abc import Mapping

from app.features.cashout.types import CashoutDocumentClassification

from .schemas import (
    CashoutDocumentSchema,
    DailyCashSummaryData,
    DailyTipOutSheetData,
    ManualNoteData,
    PaymentReceiptData,
    PaystoneTerminalReportData,
    TouchBistroServerShiftReportData,
)

CASHOUT_DOCUMENT_SCHEMAS: Mapping[
    CashoutDocumentClassification, type[CashoutDocumentSchema]
] = {
    CashoutDocumentClassification.TOUCHBISTRO_SERVER_SHIFT_REPORT: (
        TouchBistroServerShiftReportData
    ),
    CashoutDocumentClassification.PAYSTONE_TERMINAL_REPORT: PaystoneTerminalReportData,
    CashoutDocumentClassification.PAYMENT_RECEIPT: PaymentReceiptData,
    CashoutDocumentClassification.DAILY_TIP_OUT_SHEET: DailyTipOutSheetData,
    CashoutDocumentClassification.DAILY_CASH_SUMMARY: DailyCashSummaryData,
    CashoutDocumentClassification.MANUAL_NOTE: ManualNoteData,
}

# UNKNOWN deliberately has no entry: a document the model can't place has
# nothing to extract, so the processor returns it with no data and the analysis
# completes as NEEDS_VERIFICATION with an UNKNOWN classification.

__all__ = ["CASHOUT_DOCUMENT_SCHEMAS"]
