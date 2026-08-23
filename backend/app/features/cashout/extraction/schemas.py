# backend/app/features/cashout/extraction/schemas.py

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict

from app.document_ai import FieldHint


class CashoutDocumentSchema(BaseModel):
    """Base for AI-extracted cashout document data, not an HTTP schema."""

    model_config = ConfigDict(extra="forbid")


# TODO(document-ai): Every field below is a placeholder so the pipeline runs
# end to end. The real observable fields and monetary conventions per document
# type have NOT been implemented yet — replace them before trusting extracted
# data.


class TouchBistroServerShiftReportData(CashoutDocumentSchema):
    net_sales: Annotated[
        float | None,
        FieldHint(
            labels=("Net Sales",),
            anti_anchors=("Gross Sales", "category subtotals"),
        ),
    ] = None
    total_tips: Annotated[
        float | None,
        FieldHint(
            labels=("Total Tips", "Tips"),
            anti_anchors=("Declared Tips", "tip-out amounts"),
        ),
    ] = None
    cash_owed: Annotated[
        float | None,
        FieldHint(
            labels=("Cash Owed", "Cash Due"),
            anti_anchors=("Expected Cash", "Cash Submitted"),
        ),
    ] = None


class PaystoneTerminalReportData(CashoutDocumentSchema):
    card_total: Annotated[
        float | None,
        FieldHint(
            labels=("Total", "Settlement Total"),
            sections=("batch or settlement totals",),
            anti_anchors=("per-card-brand subtotals",),
        ),
    ] = None
    tip_total: Annotated[
        float | None,
        FieldHint(
            labels=("Tip", "Tips"),
            sections=("batch or settlement totals",),
            anti_anchors=("per-transaction tip lines",),
        ),
    ] = None
    transaction_count: Annotated[
        int | None,
        FieldHint(
            labels=("Count", "Transactions"),
            anchors=("beside the batch or settlement totals",),
        ),
    ] = None


class PaymentReceiptData(CashoutDocumentSchema):
    amount: Annotated[
        float | None,
        FieldHint(
            labels=("Amount", "Purchase"),
            anti_anchors=("Tip", "Total"),
        ),
    ] = None
    tip_amount: Annotated[
        float | None,
        FieldHint(
            labels=("Tip", "Gratuity"),
            anchors=("often handwritten below the printed amount",),
        ),
    ] = None
    payment_method: Annotated[
        str | None,
        FieldHint(labels=("Card Type", "Account Type"), sections=("card details",)),
    ] = None


class DailyTipOutSheetData(CashoutDocumentSchema):
    tip_out_total: Annotated[
        float | None,
        FieldHint(
            labels=("Total",),
            anchors=("grand total row, often handwritten at the bottom",),
        ),
    ] = None
    support_staff_share: Annotated[
        float | None,
        FieldHint(
            labels=("Support", "Kitchen"),
            anchors=("the recipient or category rows",),
        ),
    ] = None


class DailyCashSummaryData(CashoutDocumentSchema):
    opening_float: Annotated[
        float | None,
        FieldHint(
            labels=("Opening Float", "Float"),
            anti_anchors=("Closing Float",),
        ),
    ] = None
    cash_deposits: Annotated[
        float | None,
        FieldHint(
            labels=("Cash Deposit", "Deposits"),
            anti_anchors=("Expected Cash",),
        ),
    ] = None
    closing_float: Annotated[
        float | None,
        FieldHint(
            labels=("Closing Float",),
            anti_anchors=("Opening Float",),
        ),
    ] = None


class ManualNoteData(CashoutDocumentSchema):
    note: Annotated[
        str | None,
        FieldHint(anchors=("the main handwritten text, including any arithmetic",)),
    ] = None


__all__ = [
    "CashoutDocumentSchema",
    "DailyCashSummaryData",
    "DailyTipOutSheetData",
    "ManualNoteData",
    "PaymentReceiptData",
    "PaystoneTerminalReportData",
    "TouchBistroServerShiftReportData",
]
