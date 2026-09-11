from __future__ import annotations

from decimal import Decimal
from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from app.document_ai import FieldHint, Money


class CashoutDocumentSchema(BaseModel):
    """Base for AI-extracted cashout document data, not an HTTP schema."""

    model_config = ConfigDict(extra="forbid")

    # The version of the shape this schema currently declares. Stored beside
    # every extraction (and manual entry), so data written by an older shape
    # stays readable after the schema changes. Changing a schema's fields or
    # their meaning means bumping its override of this and registering an
    # upcast for the previous version in the registry (unit-test-enforced);
    # loosening a constraint the old data already satisfies needs neither.
    SCHEMA_VERSION: ClassVar[int] = 1


class ServerSummaryReportData(CashoutDocumentSchema):
    grand_total: Annotated[
        Money,
        FieldHint(
            sections=("GRAND TOTALS",),
            anchors=("beside Grand Total", "last row", "last column"),
            anti_anchors=("CREDIT", "DEBIT", "TOTAL CREDIT"),
        ),
    ]
    grand_total_transaction_count: Annotated[
        int,
        Field(ge=0),
        FieldHint(
            sections=("GRAND TOTALS",),
            anchors=("beside Grand Total", "last row", "middle column"),
            anti_anchors=("CREDIT", "DEBIT", "TOTAL CREDIT"),
        ),
    ]


class TouchBistroReportData(CashoutDocumentSchema):
    SCHEMA_VERSION: ClassVar[int] = 2

    drink_net_sales: Annotated[
        Money,
        FieldHint(
            labels=("Net Sales:",),
            sections=("Sales Totals", "Total Drinks"),
            anchors=("below Gross Sales", "second row", "right side"),
            anti_anchors=(
                "Total Gift Cards",
                "Total Food",
                "Subtotal",
                "Food and Drink Tax Collected",
                "Total",
            ),
        ),
    ]
    food_net_sales: Annotated[
        Money,
        FieldHint(
            labels=("Net Sales:",),
            sections=("Sales Totals", "Total Food"),
            anchors=("below Gross Sales", "second row", "right side"),
            anti_anchors=(
                "Total Gift Cards",
                "Total Drinks",
                "Subtotal",
                "Food and Drink Tax Collected",
                "Total",
            ),
        ),
    ]
    total_net_sales: Annotated[
        Money,
        FieldHint(
            labels=("Net Sales (incl tax):",),
            sections=("Sales Totals", "Total"),
            anchors=("right side",),
            anti_anchors=(
                "Total Gift Cards",
                "Total Drinks",
                "Total Food",
                "Subtotal",
                "Food and Drink Tax Collected",
            ),
        ),
    ]

    card_transaction_count: Annotated[
        int,
        Field(ge=0),
        FieldHint(
            labels=("Orders:",),
            sections=("Payment and Refund Totals", "Card"),
            anchors=("below Cash transaction count",),
            anti_anchors=("Total Payments", "Total Refunds"),
        ),
    ]
    integrated_gift_card_transaction_count: Annotated[
        int,
        Field(ge=0),
        FieldHint(
            labels=("Orders:",),
            sections=("Payment and Refund Totals", "Integrated Gift Cards"),
            anchors=("above Total Payments",),
            anti_anchors=("Gift Card (eCard)",),
        ),
    ] = 0

    cash_payment_total: Annotated[
        Money,
        FieldHint(
            labels=("Total:",),
            sections=("Payment and Refund Totals", "Cash"),
            anchors=("one row", "right side"),
            anti_anchors=("Card", "Total Payments"),
        ),
    ]
    card_payment_total: Annotated[
        Money,
        FieldHint(
            labels=("Total:",),
            sections=("Payment and Refund Totals", "Card"),
            anchors=("below Subtotal:", "below Tips:", "third row", "right side"),
            anti_anchors=("Cash", "Total Payments"),
        ),
    ]
    integrated_gift_card_payment_total: Annotated[
        Money,
        FieldHint(
            labels=("Total",),
            sections=("Payment and Refund Totals", "Integrated Gift Cards"),
            anchors=("one row", "right side"),
            anti_anchors=("Gift Card (eCard)",),
        ),
    ] = Decimal(0)

    card_tip_total: Annotated[
        Money,
        FieldHint(
            labels=("Total:",),
            sections=("Credit Card Tips Report", "Total Credit Card Tips"),
            anchors=("right side",),
            anti_anchors=("Tips (Card)", "Tips (Gift Card)"),
        ),
    ]


class GiftCertificateData(CashoutDocumentSchema):
    amount: Annotated[Money, FieldHint(labels=("Amount:",), anchors=("middle row",))]


__all__ = [
    "CashoutDocumentSchema",
    "ServerSummaryReportData",
    "TouchBistroReportData",
    "GiftCertificateData",
]
