from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CashoutDocumentSchema(BaseModel):
    """Base for AI-extracted cashout document data, not an HTTP schema."""

    model_config = ConfigDict(extra="forbid")


class TouchBistroServerShiftReportData(CashoutDocumentSchema):
    # TODO(document-ai): Define the observable fields and monetary conventions.
    pass


class PaystoneTerminalReportData(CashoutDocumentSchema):
    # TODO(document-ai): Define the observable fields and monetary conventions.
    pass


class PaymentReceiptData(CashoutDocumentSchema):
    # TODO(document-ai): Define the observable fields and monetary conventions.
    pass


class DailyTipOutSheetData(CashoutDocumentSchema):
    # TODO(document-ai): Define the observable fields and monetary conventions.
    pass


class DailyCashSummaryData(CashoutDocumentSchema):
    # TODO(document-ai): Define the observable fields and monetary conventions.
    pass


class ManualNoteData(CashoutDocumentSchema):
    # TODO(document-ai): Define the supported note fields without accepting
    # unconstrained arbitrary JSON.
    pass


__all__ = [
    "CashoutDocumentSchema",
    "DailyCashSummaryData",
    "DailyTipOutSheetData",
    "ManualNoteData",
    "PaymentReceiptData",
    "PaystoneTerminalReportData",
    "TouchBistroServerShiftReportData",
]
