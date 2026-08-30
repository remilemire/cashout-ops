# backend/app/features/cashout/extraction/registry.py

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

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

# Every classification has an entry: a document the model can't place is not a
# classification but a failed extraction (DocumentUnclassifiedError), so there
# is no schema-less type to guard against here or downstream.

# Keys must match CASHOUT_DOCUMENT_SCHEMAS (unit-test-enforced). "None of the
# above" has no entry — markers can't describe the absence of a type; that
# guidance stays in the processor's free-form classify instructions.
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


def parse_manual_document_data(
    classification: CashoutDocumentClassification, data: Mapping[str, Any]
) -> CashoutDocumentSchema:
    """Validate manually entered document data against its registered schema.

    The classification itself is already validated by the request schema (an
    unrecognized value is an INVALID_OPTION issue on the field), and every
    classification has a schema, so only the field values remain to check.
    Field-level problems raise pydantic's ValidationError, which propagates to
    the app-wide handler for translation into the shared validation contract.
    """
    return CASHOUT_DOCUMENT_SCHEMAS[classification].model_validate(data)


__all__ = [
    "CASHOUT_CLASSIFICATION_HINTS",
    "CASHOUT_DOCUMENT_SCHEMAS",
    "parse_manual_document_data",
]
