# backend/app/features/cashout/extraction/registry.py

from __future__ import annotations

from collections.abc import Mapping

from ..types import CashoutDocumentClassification
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

# A null classification (unclassifiable) or any type without a registered schema
# is not a domain error: the processor returns it with no data and the
# extraction job marks the analysis FAILED with the UNCLASSIFIED error code for
# the cashier to retry.

__all__ = ["CASHOUT_DOCUMENT_SCHEMAS"]
