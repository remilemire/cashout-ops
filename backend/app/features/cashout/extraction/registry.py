# backend/app/features/cashout/extraction/registry.py

from __future__ import annotations

from collections.abc import Mapping

from app.document_ai import ClassificationHint

from .schemas import (
    CashoutDocumentSchema,
    ServerSummaryReportData,
    TouchBistroReportData,
)
from .types import CashoutDocumentClassification

CASHOUT_DOCUMENT_SCHEMAS: Mapping[
    CashoutDocumentClassification, type[CashoutDocumentSchema]
] = {
    CashoutDocumentClassification.TOUCHBISTRO_REPORT: TouchBistroReportData,
    CashoutDocumentClassification.SERVER_SUMMARY_REPORT: ServerSummaryReportData,
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
    CashoutDocumentClassification.TOUCHBISTRO_REPORT: ClassificationHint(
        markers=(
            "titled Whiskey District / End of Day",
            "Sales Totals, Payment and Refund Totals, and Credit Card Tips Report sections",
            "Created on an iPad using TouchBistro Pro near the bottom",
        ),
    ),
    CashoutDocumentClassification.SERVER_SUMMARY_REPORT: ClassificationHint(
        markers=(
            "titled SERVER SUMMARY REPORT",
            "END OF REPORT at the bottom",
            "CREDIT, DEBIT, and GRAND TOTALS sections",
            "uppercase headers",
        ),
    ),
}

__all__ = ["CASHOUT_CLASSIFICATION_HINTS", "CASHOUT_DOCUMENT_SCHEMAS"]
