# backend/app/features/cashout/extraction/schemas.py

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CashoutDocumentSchema(BaseModel):
    """Base for AI-extracted cashout document data, not an HTTP schema."""

    model_config = ConfigDict(extra="forbid")


# TODO(document-ai): Every field below is a placeholder so the pipeline runs
# end to end. The real observable fields and monetary conventions per document
# type have NOT been implemented yet — replace them before trusting extracted
# data.


class TouchBistroServerShiftReportData(CashoutDocumentSchema):
    net_sales: float | None = None
    total_tips: float | None = None
    cash_owed: float | None = None


class PaystoneTerminalReportData(CashoutDocumentSchema):
    card_total: float | None = None
    tip_total: float | None = None
    transaction_count: int | None = None


class PaymentReceiptData(CashoutDocumentSchema):
    amount: float | None = None
    tip_amount: float | None = None
    payment_method: str | None = None


class DailyTipOutSheetData(CashoutDocumentSchema):
    tip_out_total: float | None = None
    support_staff_share: float | None = None


class DailyCashSummaryData(CashoutDocumentSchema):
    opening_float: float | None = None
    cash_deposits: float | None = None
    closing_float: float | None = None


class ManualNoteData(CashoutDocumentSchema):
    note: str | None = None


__all__ = [
    "CashoutDocumentSchema",
    "DailyCashSummaryData",
    "DailyTipOutSheetData",
    "ManualNoteData",
    "PaymentReceiptData",
    "PaystoneTerminalReportData",
    "TouchBistroServerShiftReportData",
]
