"""The rules that turn a cashout's verified analyses into its source figures.

A cashout closes against exactly one TouchBistro end-of-day report: the
point-of-sale record every source figure below is taken from. The
payment-terminal server summaries filed alongside it are the cross-check —
their grand totals must add up to the report's card payments, and their
transaction counts to its card orders. A cashout whose documents disagree is
not reconciled at all: completion fails with what does not add up rather than
storing figures no document supports. Gift certificates must also match the
report's Integrated Gift Cards tender: one document per transaction, with
their amounts summing exactly to its payment total. An absent tender is zero.

The one allowance is a deposit: an amount the report counts among its card
payments that no terminal summary shows, because it was never rung through a
terminal that day. An admin may subtract it from the report's card payments
before the amounts are compared — the summaries then have to add up to what
remains. The count check stays as it is, and so do the figures returned: the
report's card payments are stored as the report states them.

Pure: no session and no I/O, so the rules can be read (and tested) on their
own. The data service persists what this returns.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import assert_never

from pydantic import JsonValue, ValidationError

from app.errors import AppError
from app.features.cashout.analyses.model import CashoutDocumentAnalysis
from app.features.cashout.extraction.registry import (
    UnknownSchemaVersionError,
    upcast_stored_document_data,
)
from app.features.cashout.extraction.schemas import (
    CashoutDocumentSchema,
    GiftCertificateData,
    ServerSummaryReportData,
    TouchBistroReportData,
)
from app.features.cashout.extraction.types import CashoutDocumentClassification


@dataclass(frozen=True)
class ReconciledFigures:
    """The source figures behind a reconciled cashout.

    One per source column on `CashoutData`; the tipouts and the cash balance
    are generated from them by the database.
    """

    food_net_sales: Decimal
    drink_net_sales: Decimal
    total_net_sales: Decimal
    card_payment_total: Decimal
    cash_payment_total: Decimal
    card_tip_total: Decimal


def reconcile_figures(
    analyses: Sequence[CashoutDocumentAnalysis],
    *,
    deposit_total: Decimal = Decimal(0),
) -> ReconciledFigures:
    """Cross-check a submission's verified analyses and return its figures.

    Callers pass verified analyses only (completion refuses the submission
    otherwise). `deposit_total` is an admin's adjustment: subtracted from the
    report's card payments before they are compared to the summaries, and
    nothing else. Raises an `AppError` from the data error codes for the
    first rule the cashout breaks.
    """
    touchbistro_analyses: list[CashoutDocumentAnalysis] = []
    summary_analyses: list[CashoutDocumentAnalysis] = []
    certificate_analyses: list[CashoutDocumentAnalysis] = []

    for analysis in analyses:
        classification = analysis.classification
        if classification is CashoutDocumentClassification.TOUCHBISTRO_REPORT:
            touchbistro_analyses.append(analysis)
        elif classification is CashoutDocumentClassification.SERVER_SUMMARY_REPORT:
            summary_analyses.append(analysis)
        elif classification is CashoutDocumentClassification.GIFT_CERTIFICATE:
            certificate_analyses.append(analysis)
        elif classification is None:
            # Only a failed analysis is unclassified, and a failed one cannot
            # be verified — so this is unreachable from completion, and there
            # is nothing to reconcile if it is ever reached anyway.
            raise AppError(
                "RECONCILE_DOCUMENT_DATA_INVALID",
                f"Analysis {analysis.id} is verified with no classification.",
            )
        else:
            # A new document type has to state its part in reconciliation.
            assert_never(classification)

    if not touchbistro_analyses:
        raise AppError(
            "RECONCILE_TOUCHBISTRO_MISSING",
            "The submission has no TouchBistro report to reconcile against.",
        )
    if len(touchbistro_analyses) > 1:
        raise AppError(
            "RECONCILE_TOUCHBISTRO_DUPLICATE",
            f"The submission has {len(touchbistro_analyses)} TouchBistro reports.",
        )

    report = _verified_data(touchbistro_analyses[0], TouchBistroReportData)
    summaries = [
        _verified_data(analysis, ServerSummaryReportData)
        for analysis in summary_analyses
    ]

    # No server summaries makes both sums zero, which reconciles only against
    # a shift that took no card payments at all — the same rule, not an
    # exemption from it.
    card_payments = sum((summary.grand_total for summary in summaries), Decimal(0))
    if card_payments != report.card_payment_total - deposit_total:
        # Both sides are public: the admin deciding whether a deposit
        # explains the gap needs to see it. Decimals go out as strings so
        # the cents survive JSON exactly.
        ctx: dict[str, JsonValue] = {
            "cardPaymentTotal": str(report.card_payment_total),
            "serverSummaryTotal": str(card_payments),
        }
        applied = ""
        if deposit_total:
            ctx["depositTotal"] = str(deposit_total)
            applied = f" less a {deposit_total} deposit"
        raise AppError(
            "RECONCILE_CARD_PAYMENT_MISMATCH",
            f"Server summary grand totals {card_payments} do not match"
            f" TouchBistro card payments {report.card_payment_total}{applied}.",
            ctx=ctx,
        )

    transactions = sum(summary.grand_total_transaction_count for summary in summaries)
    if transactions != report.card_transaction_count:
        raise AppError(
            "RECONCILE_CARD_TRANSACTION_MISMATCH",
            f"Server summary transaction counts {transactions} do not match"
            f" TouchBistro card orders {report.card_transaction_count}.",
        )

    certificates = [
        _verified_data(analysis, GiftCertificateData)
        for analysis in certificate_analyses
    ]
    if len(certificates) != report.integrated_gift_card_transaction_count:
        raise AppError(
            "RECONCILE_GIFT_CARD_TRANSACTION_MISMATCH",
            f"Gift certificate count {len(certificates)} does not match"
            f" TouchBistro integrated gift card orders"
            f" {report.integrated_gift_card_transaction_count}.",
            ctx={
                "integratedGiftCardTransactionCount": report.integrated_gift_card_transaction_count,
                "giftCertificateCount": len(certificates),
            },
        )

    certificate_total = sum(
        (certificate.amount for certificate in certificates), Decimal(0)
    )
    if certificate_total != report.integrated_gift_card_payment_total:
        raise AppError(
            "RECONCILE_GIFT_CARD_PAYMENT_MISMATCH",
            f"Gift certificate amounts {certificate_total} do not match"
            f" TouchBistro integrated gift card payments"
            f" {report.integrated_gift_card_payment_total}.",
            ctx={
                "integratedGiftCardPaymentTotal": str(
                    report.integrated_gift_card_payment_total
                ),
                "giftCertificateTotal": str(certificate_total),
            },
        )

    # The cross-check passed, so the TouchBistro report stands for the whole
    # cashout: its fields are the source columns, one for one — the card
    # payments included, deposit and all, as the report states them.
    return ReconciledFigures(
        food_net_sales=report.food_net_sales,
        drink_net_sales=report.drink_net_sales,
        total_net_sales=report.total_net_sales,
        card_payment_total=report.card_payment_total,
        cash_payment_total=report.cash_payment_total,
        card_tip_total=report.card_tip_total,
    )


def _verified_data[SchemaT: CashoutDocumentSchema](
    analysis: CashoutDocumentAnalysis, schema: type[SchemaT]
) -> SchemaT:
    """Read an analysis's verified data as its document type's schema.

    The stored payload keeps the shape of the schema version it was extracted
    (or entered) under; the registry's upcasts lift an older shape to what the
    current schema validates, so a cashout analyzed before a schema change
    still reconciles. Verification stores the cashier's corrections as typed,
    without checking them against the schema, so this is where an unreadable
    correction (or a field dropped from the payload) surfaces: as a completion
    conflict naming the document, rather than a field-level 422 on a request
    that changed nothing.
    """
    data = analysis.verified_data_json
    try:
        if data is not None:
            data = upcast_stored_document_data(
                schema, data, schema_version=analysis.schema_version
            )
        return schema.model_validate(data)
    except UnknownSchemaVersionError as exc:
        raise AppError(
            "RECONCILE_DOCUMENT_DATA_INVALID",
            f"Verified data for analysis {analysis.id} cannot be read: {exc}",
        ) from exc
    except ValidationError as exc:
        raise AppError(
            "RECONCILE_DOCUMENT_DATA_INVALID",
            f"Verified data for analysis {analysis.id} is not a valid"
            f" {schema.__name__}: {exc}",
        ) from exc


__all__ = ["ReconciledFigures", "reconcile_figures"]
