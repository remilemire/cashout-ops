# backend/app/features/cashout/extraction/registry.py

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.document_ai import ClassificationHint
from app.errors import ValidationError

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


def parse_manual_document_data(
    classification: CashoutDocumentClassification, data: Mapping[str, Any]
) -> CashoutDocumentSchema:
    """Validate manually entered document data against its registered schema.

    A manual entry asserts a concrete document type, so there must be a schema
    to validate against: UNKNOWN (and any classification without a registered
    schema) is rejected as an invalid option. Field-level problems raise
    pydantic's ValidationError, which propagates to the app-wide handler for
    translation into the shared validation contract.
    """
    schema = CASHOUT_DOCUMENT_SCHEMAS.get(classification)
    if schema is None:
        raise ValidationError(
            [
                {
                    "code": "INVALID_OPTION",
                    "path": ["classification"],
                    "ctx": {
                        "allowed_options": [
                            option.value for option in CASHOUT_DOCUMENT_SCHEMAS
                        ]
                    },
                }
            ]
        )
    return schema.model_validate(data)


__all__ = [
    "CASHOUT_CLASSIFICATION_HINTS",
    "CASHOUT_DOCUMENT_SCHEMAS",
    "parse_manual_document_data",
]
