"""Reconciliation's version-aware read of stored analysis payloads, and the
deposit adjustment's exact effect on the cross-check.

The cross-check rules themselves are covered end-to-end in
tests/integration/test_cashout_data.py; these tests cover what only the pure
layer shows — verified data written under an older schema version is lifted
through the registered upcasts before validation, a version this build
cannot read surfaces as the completion conflict, not a crash, and a deposit
moves the comparison without moving the figures.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

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


@pytest.mark.parametrize(
    ("classification", "field", "omit"),
    [
        (kind, field, omit)
        for kind, fields in [
            (
                CashoutDocumentClassification.TOUCHBISTRO_REPORT,
                TouchBistroReportData.model_fields,
            ),
            (
                CashoutDocumentClassification.SERVER_SUMMARY_REPORT,
                ServerSummaryReportData.model_fields,
            ),
            (CashoutDocumentClassification.GIFT_CERTIFICATE, {"amount": None}),
        ]
        for field in fields
        for omit in [False, True]
        if not (omit and field.startswith("integrated_gift_card_"))
    ],
)
def test_reconciliation_requires_document_values(
    classification: CashoutDocumentClassification, field: str, omit: bool
) -> None:
    # Missing integrated-gift fields retain the existing absent-tender zero
    # default. Explicit null means unknown and must never become zero.
    report = {
        **_TOUCHBISTRO_VERIFIED,
        "integrated_gift_card_transaction_count": 1,
        "integrated_gift_card_payment_total": "25.00",
    }
    payloads: dict[CashoutDocumentClassification, dict[str, Any]] = {
        CashoutDocumentClassification.TOUCHBISTRO_REPORT: report,
        CashoutDocumentClassification.SERVER_SUMMARY_REPORT: dict(_SUMMARY_VERIFIED),
        CashoutDocumentClassification.GIFT_CERTIFICATE: {"amount": "25.00"},
    }
    if omit:
        del payloads[classification][field]
    else:
        payloads[classification][field] = None
    analyses = [
        _analysis(
            kind,
            payload,
            schema_version=2
            if kind is CashoutDocumentClassification.TOUCHBISTRO_REPORT
            else 1,
        )
        for kind, payload in payloads.items()
    ]
    with pytest.raises(AppError) as exc_info:
        reconcile_figures(analyses)
    assert exc_info.value.code == "RECONCILE_DOCUMENT_DATA_INVALID"


def test_older_version_verified_data_is_lifted_before_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simulate the next TouchBistro shape: version 3 renames version 2's
    # "tips_on_card" to "card_tip_total". A cashout analyzed (and verified)
    # before the change still reconciles, through the registered step.
    def _rename_tips(data: dict[str, Any]) -> dict[str, Any]:
        lifted = dict(data)
        lifted["card_tip_total"] = lifted.pop("tips_on_card")
        return lifted

    monkeypatch.setattr(TouchBistroReportData, "SCHEMA_VERSION", 3)
    monkeypatch.setattr(
        extraction_registry,
        "CASHOUT_SCHEMA_UPCASTS",
        {
            **extraction_registry.CASHOUT_SCHEMA_UPCASTS,
            TouchBistroReportData: {
                **extraction_registry.CASHOUT_SCHEMA_UPCASTS[TouchBistroReportData],
                2: _rename_tips,
            },
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


# ================================
# ----- Deposit adjustment -------
# ================================


def _pair_short_by_234_56() -> list[CashoutDocumentAnalysis]:
    """The report's 1234.56 of card payments against a summary of 1000.00:
    the count still matches, so only the amount check is at stake."""
    return [
        _analysis(
            CashoutDocumentClassification.TOUCHBISTRO_REPORT,
            _TOUCHBISTRO_VERIFIED,
            schema_version=TouchBistroReportData.SCHEMA_VERSION,
        ),
        _analysis(
            CashoutDocumentClassification.SERVER_SUMMARY_REPORT,
            {**_SUMMARY_VERIFIED, "grand_total": "1000.00"},
            schema_version=ServerSummaryReportData.SCHEMA_VERSION,
        ),
    ]


def test_a_deposit_that_closes_the_gap_reconciles() -> None:
    # The report counts a 234.56 deposit among its card payments that no
    # terminal summary shows. Subtracting it makes the summaries add up —
    # and the stored card payments stay the report's own figure, deposit
    # included; the adjustment only changed the comparison.
    figures = reconcile_figures(
        _pair_short_by_234_56(), deposit_total=Decimal("234.56")
    )

    assert figures.card_payment_total == Decimal("1234.56")


def test_a_deposit_that_does_not_close_the_gap_still_conflicts() -> None:
    with pytest.raises(AppError) as exc_info:
        reconcile_figures(_pair_short_by_234_56(), deposit_total=Decimal("100.00"))

    exc = exc_info.value
    assert exc.code == "RECONCILE_CARD_PAYMENT_MISMATCH"
    # Every side of the comparison is public, as strings so the cents survive
    # JSON exactly — the admin deciding on a deposit needs to see them.
    assert exc.ctx == {
        "cardPaymentTotal": "1234.56",
        "serverSummaryTotal": "1000.00",
        "depositTotal": "100.00",
    }


def test_a_mismatch_without_a_deposit_reports_no_deposit() -> None:
    with pytest.raises(AppError) as exc_info:
        reconcile_figures(_pair_short_by_234_56())

    exc = exc_info.value
    assert exc.code == "RECONCILE_CARD_PAYMENT_MISMATCH"
    assert exc.ctx == {
        "cardPaymentTotal": "1234.56",
        "serverSummaryTotal": "1000.00",
    }


@pytest.mark.parametrize(
    ("report_fields", "amounts", "error_code"),
    [
        ({}, [], None),
        (
            {
                "integrated_gift_card_transaction_count": 0,
                "integrated_gift_card_payment_total": "0.00",
            },
            [],
            None,
        ),
        (
            {
                "integrated_gift_card_transaction_count": 2,
                "integrated_gift_card_payment_total": "0.30",
            },
            ["0.10", "0.20"],
            None,
        ),
        (
            {
                "integrated_gift_card_transaction_count": 1,
                "integrated_gift_card_payment_total": "50.00",
            },
            [],
            "RECONCILE_GIFT_CARD_TRANSACTION_MISMATCH",
        ),
        ({}, ["25.00"], "RECONCILE_GIFT_CARD_TRANSACTION_MISMATCH"),
        (
            {
                "integrated_gift_card_transaction_count": 1,
                "integrated_gift_card_payment_total": "50.00",
            },
            ["25.00", "25.00"],
            "RECONCILE_GIFT_CARD_TRANSACTION_MISMATCH",
        ),
        (
            {
                "integrated_gift_card_transaction_count": 2,
                "integrated_gift_card_payment_total": "50.01",
            },
            ["25.00", "25.00"],
            "RECONCILE_GIFT_CARD_PAYMENT_MISMATCH",
        ),
        (
            {"integrated_gift_card_payment_total": "25.00"},
            [],
            "RECONCILE_GIFT_CARD_PAYMENT_MISMATCH",
        ),
        (
            {"integrated_gift_card_transaction_count": 1},
            ["25.00"],
            "RECONCILE_GIFT_CARD_PAYMENT_MISMATCH",
        ),
        (
            {
                "integrated_gift_card_transaction_count": 1,
                "integrated_gift_card_payment_total": "25.00",
            },
            ["unreadable"],
            "RECONCILE_DOCUMENT_DATA_INVALID",
        ),
    ],
    ids=[
        "absent",
        "explicit_zero",
        "exact_decimal_sum",
        "missing",
        "unexpected",
        "extra_same_sum",
        "one_cent",
        "zero_count_nonzero_total",
        "missing_total",
        "invalid_amount",
    ],
)
def test_gift_certificate_reconciliation(
    report_fields: dict[str, Any], amounts: list[str], error_code: str | None
) -> None:
    # A deposit closes the card-payment gap only. It must never excuse a
    # gift certificate mismatch or change the source figures.
    analyses = _pair_short_by_234_56()
    analyses[0].verified_data_json = {**_TOUCHBISTRO_VERIFIED, **report_fields}
    upload_id = uuid4()
    for position, amount in enumerate(amounts, 1):
        certificate = _analysis(
            CashoutDocumentClassification.GIFT_CERTIFICATE,
            {"amount": amount},
            schema_version=1,
        )
        # Multiple documents from the same upload each count once.
        certificate.cashout_upload_id = upload_id
        certificate.position = position
        analyses.append(certificate)
    if error_code is not None:
        with pytest.raises(AppError) as exc_info:
            reconcile_figures(analyses, deposit_total=Decimal("234.56"))
        assert exc_info.value.code == error_code
    else:
        figures = reconcile_figures(analyses, deposit_total=Decimal("234.56"))
        assert figures.card_payment_total == Decimal("1234.56")
        assert figures.cash_payment_total == Decimal("150.00")
