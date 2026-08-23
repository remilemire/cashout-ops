# backend/app/features/cashout/extraction/registry.py

from __future__ import annotations

from collections.abc import Mapping

from app.document_ai import ClassificationHint

from .schemas import (
    CashoutDocumentSchema,
    DailyCashSummaryData,
    DailyTipOutSheetData,
    ManualNoteData,
    PaymentReceiptData,
    PaystoneTerminalReportData,
    TouchBistroServerShiftReportData,
)
from .types import CashoutDocumentClassification

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

# Keys must match CASHOUT_DOCUMENT_SCHEMAS (unit-test-enforced). UNKNOWN again
# has no entry — markers can't describe "none of the above"; its guidance stays
# in the processor's free-form classify instructions.
CASHOUT_CLASSIFICATION_HINTS: Mapping[
    CashoutDocumentClassification, ClassificationHint
] = {
    CashoutDocumentClassification.TOUCHBISTRO_SERVER_SHIFT_REPORT: ClassificationHint(
        markers=(
            "TouchBistro branding at the top",
            "sales broken into menu categories (food, liquor, ...)",
            "tender totals, tips, and voids/discounts",
            "titled a shift, server, or sales report",
        ),
        anti_markers=(
            "per-card-brand settlement totals",
            "batch or terminal identifiers",
        ),
    ),
    CashoutDocumentClassification.PAYSTONE_TERMINAL_REPORT: ClassificationHint(
        markers=(
            "a Paystone batch, settlement, or day-close report",
            "card transaction counts and totals per card brand",
            "terminal or batch identifiers",
        ),
        anti_markers=("a menu or sales-category breakdown",),
    ),
    CashoutDocumentClassification.PAYMENT_RECEIPT: ClassificationHint(
        markers=(
            "a single card transaction amount",
            '"Debit Terminal" or a terminal identifier near the bottom',
            "an authorization code and card details",
            "possibly tip and total lines",
        ),
        anti_markers=("multiple transactions or batch totals",),
    ),
    CashoutDocumentClassification.DAILY_TIP_OUT_SHEET: ClassificationHint(
        markers=(
            "rows of tip-out recipients or categories (kitchen, bar, ...)",
            "amounts often handwritten onto a printed template",
        ),
    ),
    CashoutDocumentClassification.DAILY_CASH_SUMMARY: ClassificationHint(
        markers=(
            "expected cash, counted or submitted cash",
            "floats and shortage/overage amounts",
        ),
    ),
    CashoutDocumentClassification.MANUAL_NOTE: ClassificationHint(
        markers=("free-form handwritten notes or calculations",),
        anti_markers=("an underlying printed template or form",),
    ),
}

__all__ = ["CASHOUT_CLASSIFICATION_HINTS", "CASHOUT_DOCUMENT_SCHEMAS"]
