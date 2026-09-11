from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.document_ai import ClassificationHint

from .schemas import (
    CashoutDocumentSchema,
    GiftCertificateData,
    ServerSummaryReportData,
    TouchBistroReportData,
)
from .types import CashoutDocumentClassification

CASHOUT_DOCUMENT_SCHEMAS: Mapping[
    CashoutDocumentClassification, type[CashoutDocumentSchema]
] = {
    CashoutDocumentClassification.TOUCHBISTRO_REPORT: TouchBistroReportData,
    CashoutDocumentClassification.SERVER_SUMMARY_REPORT: ServerSummaryReportData,
    CashoutDocumentClassification.GIFT_CERTIFICATE: GiftCertificateData,
}

# Every classification has an entry: a document the model can't place is not a
# classification but a failed extraction (DocumentUnclassifiableError), so there
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
    CashoutDocumentClassification.GIFT_CERTIFICATE: ClassificationHint(
        markers=(
            "titled Gift Certificate",
            "black background",
            "WHISKEY DISTRICT on right",
        ),
    ),
}


# One step of a schema's stored-data history: a payload as written under
# `from_version`, returned in the shape of `from_version + 1`. Pure dict → dict;
# validation stays with the reader.
type DocumentDataUpcast = Callable[[dict[str, Any]], dict[str, Any]]


def _touchbistro_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Supply the gift card fields older extractions did not collect.

    Preserve any values already entered during the unversioned rollout.
    """
    return {
        "integrated_gift_card_transaction_count": 0,
        "integrated_gift_card_payment_total": "0",
        **data,
    }


# {schema: {from_version: upcast}} — how a stored payload written under an
# older SCHEMA_VERSION is lifted, one step at a time, to the shape the current
# schema validates. Bumping a schema's SCHEMA_VERSION means adding the step
# for the version it replaces here; a unit test enforces that every chain is
# contiguous from 1 to the current version.
CASHOUT_SCHEMA_UPCASTS: Mapping[
    type[CashoutDocumentSchema], Mapping[int, DocumentDataUpcast]
] = {
    TouchBistroReportData: {1: _touchbistro_v1_to_v2},
    ServerSummaryReportData: {},
    GiftCertificateData: {},
}


class UnknownSchemaVersionError(Exception):
    """Stored document data carries a version this build cannot read: ahead of
    the current schema (a rollback reading newer rows) or missing its upcast
    step. Readers translate it into their own vocabulary."""


def upcast_stored_document_data(
    schema: type[CashoutDocumentSchema],
    data: Mapping[str, Any],
    *,
    schema_version: int | None,
) -> dict[str, Any]:
    """Lift stored document data to the shape `schema` currently validates.

    `schema_version` is the SCHEMA_VERSION the payload was written under; rows
    from before versions were recorded carry null, which means 1 — the only
    version that existed. Data already at the current version passes through
    unchanged. Raises UnknownSchemaVersionError when no upcast path exists.
    """
    version = 1 if schema_version is None else schema_version
    current = schema.SCHEMA_VERSION
    if version > current:
        raise UnknownSchemaVersionError(
            f"{schema.__name__} data is at version {version}, ahead of the"
            f" current version {current}."
        )
    upcasts = CASHOUT_SCHEMA_UPCASTS.get(schema, {})
    payload = dict(data)
    while version < current:
        step = upcasts.get(version)
        if step is None:
            raise UnknownSchemaVersionError(
                f"{schema.__name__} has no upcast from version {version}."
            )
        payload = step(payload)
        version += 1
    return payload


def parse_manual_document_data(
    classification: CashoutDocumentClassification, data: Mapping[str, Any]
) -> CashoutDocumentSchema:
    """Validate manually entered document data against its registered schema.

    The classification itself is already validated by the request schema (an
    unrecognized value is an enum issue on the field), and every
    classification has a schema, so only the field values remain to check.
    Field-level problems raise pydantic's ValidationError, which propagates to
    the app-wide handler for translation into the shared validation contract.
    """
    return CASHOUT_DOCUMENT_SCHEMAS[classification].model_validate(data)


__all__ = [
    "CASHOUT_CLASSIFICATION_HINTS",
    "CASHOUT_DOCUMENT_SCHEMAS",
    "CASHOUT_SCHEMA_UPCASTS",
    "DocumentDataUpcast",
    "UnknownSchemaVersionError",
    "parse_manual_document_data",
    "upcast_stored_document_data",
]
