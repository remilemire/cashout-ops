# backend/app/features/cashout/extraction/processor.py

from __future__ import annotations

from dataclasses import dataclass

from app.document_ai import (
    DocumentAIClient,
    DocumentRef,
    FieldIssue,
)
from app.features.cashout.types import CashoutDocumentClassification
from app.integrations.ai import AIProvider

from .registry import CASHOUT_DOCUMENT_SCHEMAS
from .schemas import CashoutDocumentSchema

_CLASSIFY_INSTRUCTIONS = """
The document is one end-of-shift record from a restaurant cashout. Differentiate the permitted types as follows:

* TOUCHBISTRO_SERVER_SHIFT_REPORT — a printed TouchBistro point-of-sale report for a server's shift: sales broken into menu categories (food, liquor, ...), tender totals, tips, and voids/discounts, typically titled a shift, server, or sales report.
* PAYSTONE_TERMINAL_REPORT — a Paystone payment-terminal batch, settlement, or day-close report: card transaction counts and totals per card brand, terminal or batch identifiers, and no menu or sales-category breakdown.
* PAYMENT_RECEIPT — a single card transaction receipt (merchant or customer copy): one transaction amount, possibly tip and total lines, card details, and an authorization code.
* DAILY_TIP_OUT_SHEET — a sheet recording the day's tip-outs: rows of recipients or categories (kitchen, bar, ...) with amounts, often handwritten onto a printed template.
* DAILY_CASH_SUMMARY — a sheet summarizing the day's cash position: expected cash, counted or submitted cash, floats, and shortage/overage amounts.
* MANUAL_NOTE — a free-form handwritten note or calculation that does not follow any printed template.
* UNKNOWN — anything else, including unrelated photos and documents too degraded to identify.

Distinguish carefully:

* A terminal report aggregates many transactions or batch totals; a payment receipt shows exactly one transaction.
* A TouchBistro report is organized around sales and menu categories; a Paystone report is organized around card transactions and settlement.
* Handwriting alone does not make a document a MANUAL_NOTE: tip-out sheets and cash summaries are often filled in by hand on printed templates. Use MANUAL_NOTE only when there is no underlying form.
"""

_EXTRACT_INSTRUCTIONS = """
The supplied documents relate to restaurant cashout and end-of-shift reconciliation workflows.

Documents may include:

* point-of-sale shift or sales reports;
* payment-terminal transaction reports;
* debit and credit card receipts;
* merchant and customer receipts;
* server cashout sheets;
* handwritten cashout calculations;
* tip and tip-out records;
* daily cash sheets;
* discount, void, refund, or correction records;
* TouchBistro reports;
* Paystone reports.

Documents may be photographed, scanned, cropped, rotated, handwritten, faded, or partially obscured. Several values may appear similar or may be repeated in different sections.

Interpret fields according to their accounting meaning. Keep these concepts distinct:

* gross sales, net sales, and total sales;
* food, liquor, and other sales categories;
* cash, debit, credit, gift card, cheque, and other tenders;
* collected tips and declared tips;
* tip-outs and tip-out categories;
* refunds, voids, discounts, and corrections;
* expected cash, cash submitted, cash owed, and cash due;
* shortages, overages, and reconciliation differences;
* transaction totals and settlement totals;
* employee names, server numbers, terminal numbers, shift dates, and report dates.

Do not combine values from different documents or sections unless explicitly requested. Do not assume two similarly named totals represent the same accounting value.

When extracting monetary values:

* Preserve negative signs and explicit credits.
* Do not include currency symbols in numeric fields unless the schema expects strings.
* Treat values as Canadian dollars when the document clearly belongs to this cashout workflow and does not specify another currency.
* Do not convert currencies.
* Do not recompute printed totals unless explicitly requested.
* Flag apparent inconsistencies rather than correcting them silently.

Handwritten values may represent corrections or final accepted amounts. Prefer them over printed values only when the document clearly indicates that they replace or amend the printed value.

Receipts may contain both transaction amounts and gratuities. Do not treat the final charged amount, subtotal, tax, and tip as interchangeable.
"""


@dataclass(frozen=True)
class CashoutDocumentProcessingResult:
    # Never null: an unclassifiable document is UNKNOWN.
    classification: CashoutDocumentClassification
    classification_confidence: float
    # data/confidence/issues are None/empty when the classification has no
    # registered schema (UNKNOWN).
    data: CashoutDocumentSchema | None
    confidence: float | None
    issues: list[FieldIssue]
    schema_name: str | None


class CashoutDocumentProcessor:
    """Maps generic document analysis onto the cashout domain."""

    def __init__(self, documents: DocumentAIClient) -> None:
        self._documents = documents

    @property
    def provider(self) -> AIProvider:
        return self._documents.ai.provider

    @property
    def model(self) -> str:
        return self._documents.ai.model

    async def process(
        self,
        document: DocumentRef,
    ) -> CashoutDocumentProcessingResult:
        classification = await self._documents.classify(
            document, CashoutDocumentClassification, instructions=_CLASSIFY_INSTRUCTIONS
        )
        # The generic layer expresses "can't classify" as a null value; the
        # domain folds it into the explicit UNKNOWN member.
        value = classification.value or CashoutDocumentClassification.UNKNOWN

        # UNKNOWN (and any type without a registered schema) has nothing to
        # extract.
        schema = CASHOUT_DOCUMENT_SCHEMAS.get(value)
        if schema is None:
            return CashoutDocumentProcessingResult(
                classification=value,
                classification_confidence=classification.confidence,
                data=None,
                confidence=None,
                issues=[],
                schema_name=None,
            )

        # TODO(document-ai): Add deterministic validation once the schemas
        # define real fields (totals reconcile, amounts non-negative, ...).
        analysis = await self._documents.process(
            document, schema, instructions=_EXTRACT_INSTRUCTIONS
        )
        return CashoutDocumentProcessingResult(
            classification=value,
            classification_confidence=classification.confidence,
            data=analysis.data,
            confidence=analysis.confidence,
            issues=analysis.issues,
            schema_name=schema.__name__,
        )


__all__ = ["CashoutDocumentProcessingResult", "CashoutDocumentProcessor"]
