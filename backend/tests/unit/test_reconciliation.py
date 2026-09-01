# backend/tests/unit/test_reconciliation.py

"""Reconciliation's version-aware read of stored analysis payloads.

The cross-check rules themselves are covered end-to-end in
tests/integration/test_cashout_data.py; these tests cover what only the pure
layer shows — verified data written under an older schema version is lifted
through the registered upcasts before validation, and a version this build
cannot read surfaces as the completion conflict, not a crash.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from app.errors import AppError
from app.features.cashout.analyses.model import CashoutDocumentAnalysis
from app.features.cashout.data.reconciliation import reconcile_figures
from app.features.cashout.extraction import registry as extraction_registry
from app.features.cashout.extraction.schemas import (
    ServerSummaryReportData,
    TouchBistroReportData,
)
from app.features.cashout.extraction.types import CashoutDocumentClassification

# A reconcilable pair in the current shapes: the summary's grand totals match
# the report's card payments and orders exactly.
_TOUCHBISTRO_VERIFIED: dict[str, Any] = {
    "food_net_sales": "800.00",
    "drink_net_sales": "400.00",
    "total_net_sales": "1200.00",
    "card_transaction_count": 42,
    "cash_payment_total": "150.00",
    "card_payment_total": "1234.56",
    "card_tip_total": "180.00",
}
_SUMMARY_VERIFIED: dict[str, Any] = {
    "grand_total": "1234.56",
    "grand_total_transaction_count": 42,
}


def _analysis(
    classification: CashoutDocumentClassification,
    verified: dict[str, Any],
    *,
    schema_version: int | None,
) -> CashoutDocumentAnalysis:
    # In-memory only: reconciliation is pure, so no session or ids are needed.
    return CashoutDocumentAnalysis(
        classification=classification,
        schema_version=schema_version,
        verified_data_json=verified,
    )


def test_pre_versioning_rows_reconcile_as_the_first_version() -> None:
    # Rows written before versions were recorded carry null, which reads as
    # version 1 — the only shape that existed when they were written.
    figures = reconcile_figures(
        [
            _analysis(
                CashoutDocumentClassification.TOUCHBISTRO_REPORT,
                _TOUCHBISTRO_VERIFIED,
                schema_version=None,
            ),
            _analysis(
                CashoutDocumentClassification.SERVER_SUMMARY_REPORT,
                _SUMMARY_VERIFIED,
                schema_version=None,
            ),
        ]
    )

    assert figures.card_payment_total == Decimal("1234.56")
    assert figures.card_tip_total == Decimal("180.00")


def test_older_version_verified_data_is_lifted_before_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simulate the next TouchBistro shape: version 2 renames version 1's
    # "tips_on_card" to "card_tip_total". A cashout analyzed (and verified)
    # before the change still reconciles, through the registered step.
    def _rename_tips(data: dict[str, Any]) -> dict[str, Any]:
        lifted = dict(data)
        lifted["card_tip_total"] = lifted.pop("tips_on_card")
        return lifted

    monkeypatch.setattr(TouchBistroReportData, "SCHEMA_VERSION", 2)
    monkeypatch.setattr(
        extraction_registry,
        "CASHOUT_SCHEMA_UPCASTS",
        {
            **extraction_registry.CASHOUT_SCHEMA_UPCASTS,
            TouchBistroReportData: {1: _rename_tips},
        },
    )
    old_shape = {
        key: value
        for key, value in _TOUCHBISTRO_VERIFIED.items()
        if key != "card_tip_total"
    }
    old_shape["tips_on_card"] = "180.00"

    figures = reconcile_figures(
        [
            _analysis(
                CashoutDocumentClassification.TOUCHBISTRO_REPORT,
                old_shape,
                schema_version=1,
            ),
            _analysis(
                CashoutDocumentClassification.SERVER_SUMMARY_REPORT,
                _SUMMARY_VERIFIED,
                schema_version=ServerSummaryReportData.SCHEMA_VERSION,
            ),
        ]
    )

    assert figures.card_tip_total == Decimal("180.00")


def test_unknown_version_verified_data_is_a_completion_conflict() -> None:
    # A version this build has no path from (e.g. a rollback reading rows a
    # newer build wrote) conflicts like any other unreadable verified data.
    analyses = [
        _analysis(
            CashoutDocumentClassification.TOUCHBISTRO_REPORT,
            _TOUCHBISTRO_VERIFIED,
            schema_version=99,
        ),
        _analysis(
            CashoutDocumentClassification.SERVER_SUMMARY_REPORT,
            _SUMMARY_VERIFIED,
            schema_version=None,
        ),
    ]

    with pytest.raises(AppError) as exc_info:
        reconcile_figures(analyses)
    assert exc_info.value.code == "RECONCILE_DOCUMENT_DATA_INVALID"
