# backend/tests/integration/test_cashout_data.py

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.features.cashout.data.types import TipoutDepartment
from tests.support.api import csrf_headers
from tests.support.cashout import (
    SERVER_SUMMARY_EXTRACTED,
    TOUCHBISTRO_EXTRACTED,
    complete_submission,
    completion_body,
    configure_server_summary,
    configure_touchbistro,
    create_submission,
    create_upload,
    prepare_completable_submission,
    upload_reconcilable_documents,
    verify_analysis,
)
from tests.support.documents import SAMPLE_PNG_UPLOAD
from tests.support.fakes import FakeAIClient
from tests.support.fixtures.outbox import OutboxDrain


async def _complete_a_cashout(
    client: AsyncClient,
    ai_client: FakeAIClient,
    drain: OutboxDrain,
    *,
    tipout_departments: list[TipoutDepartment],
) -> str:
    submission_id = await prepare_completable_submission(
        client, ai_client=ai_client, drain=drain
    )
    await complete_submission(
        client, submission_id, tipout_departments=tipout_departments
    )
    return submission_id


async def _try_complete(client: AsyncClient, submission_id: str) -> dict[str, Any]:
    """POST the completion and return the response body, whatever it is."""
    response = await client.post(
        f"/api/cashout/submissions/{submission_id}/complete",
        json=completion_body(),
        headers=csrf_headers(client),
    )
    body: dict[str, Any] = response.json()
    body["_status"] = response.status_code
    return body


async def _complete_with_touchbistro_overrides(
    client: AsyncClient,
    ai_client: FakeAIClient,
    drain: OutboxDrain,
    *,
    overrides: dict[str, str],
    tipout_departments: list[TipoutDepartment],
) -> str:
    submission_id = await create_submission(client)
    touchbistro, summary = await upload_reconcilable_documents(
        client,
        submission_id,
        ai_client=ai_client,
        drain=drain,
    )
    await verify_analysis(
        client,
        touchbistro["id"],
        {"verifiedData": {**TOUCHBISTRO_EXTRACTED, **overrides}},
    )
    await verify_analysis(client, summary["id"])
    await complete_submission(
        client,
        submission_id,
        tipout_departments=tipout_departments,
    )
    return submission_id


async def test_data_table_is_admin_only(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    submission_id = await prepare_completable_submission(
        cashier_client, ai_client=ai_client, drain=drain_outbox
    )
    await complete_submission(cashier_client, submission_id)

    forbidden = await cashier_client.get("/api/cashout/data")
    assert forbidden.status_code == 403

    allowed = await admin_client.get("/api/cashout/data")
    assert allowed.status_code == 200
    assert [row["submissionId"] for row in allowed.json()] == [submission_id]


async def test_completion_records_the_selected_tipout_departments(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    await _complete_a_cashout(
        cashier_client,
        ai_client,
        drain_outbox,
        tipout_departments=[TipoutDepartment.BAR, TipoutDepartment.EXPO],
    )

    (row,) = (await admin_client.get("/api/cashout/data")).json()

    # The selection, sorted, plus the manager reconciliation adds.
    assert row["tipoutDepartments"] == ["bar", "expo", "manager"]


async def test_manager_is_always_tipped_out(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # The cashier picks the other departments; the manager is not a choice.
    # With nothing selected the manager still tips out — 1% of the 1200.00
    # total — which is all that reduces the 30.00 the house owes.
    await _complete_a_cashout(
        cashier_client, ai_client, drain_outbox, tipout_departments=[]
    )

    (row,) = (await admin_client.get("/api/cashout/data")).json()

    assert row["tipoutDepartments"] == ["manager"]
    assert row["managerTipout"] == "12.00"
    assert row["barTipout"] is None
    assert row["kitchenTipout"] is None
    assert row["expoTipout"] is None
    assert row["hostTipout"] is None
    assert row["cashOwedToHouse"] is None
    assert row["cashOwedToEmployee"] == "18.00"


async def test_naming_the_manager_is_accepted_and_not_duplicated(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    await _complete_a_cashout(
        cashier_client,
        ai_client,
        drain_outbox,
        tipout_departments=[TipoutDepartment.MANAGER, TipoutDepartment.KITCHEN],
    )

    (row,) = (await admin_client.get("/api/cashout/data")).json()

    assert row["tipoutDepartments"] == ["kitchen", "manager"]


async def test_completion_snapshots_the_configured_rates(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A cashout closes against the rates in force at that moment, so the row
    # keeps its own copy rather than reading the configured value back later.
    # The manager's rate is configured and snapshotted like the others.
    monkeypatch.setattr(settings.tipout, "KITCHEN_RATE", Decimal("0.0350"))
    monkeypatch.setattr(settings.tipout, "MANAGER_RATE", Decimal("0.0150"))

    await _complete_a_cashout(
        cashier_client,
        ai_client,
        drain_outbox,
        tipout_departments=[TipoutDepartment.KITCHEN],
    )

    (row,) = (await admin_client.get("/api/cashout/data")).json()
    assert row["kitchenTipoutRate"] == "0.0350"
    assert row["managerTipoutRate"] == "0.0150"
    # 1200.00 * 0.0150
    assert row["managerTipout"] == "18.00"

    # Changing the rates afterwards must not restate the closed cashout.
    monkeypatch.setattr(settings.tipout, "KITCHEN_RATE", Decimal("0.9900"))
    monkeypatch.setattr(settings.tipout, "MANAGER_RATE", Decimal("0.9900"))

    (unchanged,) = (await admin_client.get("/api/cashout/data")).json()
    assert unchanged["kitchenTipoutRate"] == "0.0350"
    assert unchanged["managerTipoutRate"] == "0.0150"
    assert unchanged["managerTipout"] == "18.00"


async def test_data_rows_carry_their_submission_identity(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # The bare figures don't say whose cashout this was: each listed row
    # carries its submission's identity — the employee and the business day.
    submission_id = await prepare_completable_submission(
        cashier_client,
        ai_client=ai_client,
        drain=drain_outbox,
        business_date="2026-08-15",
    )
    await complete_submission(cashier_client, submission_id)

    (row,) = (await admin_client.get("/api/cashout/data")).json()

    submission = row["submission"]
    assert submission["id"] == submission_id
    assert submission["businessDate"] == "2026-08-15"

    detail = await admin_client.get(f"/api/cashout/submissions/{submission_id}")
    employee = submission["employee"]
    assert employee["id"] == detail.json()["employeeUserId"]
    assert employee["fullName"] == "Test User"
    assert employee["email"] == "cashier@test.com"


# ================================
# -------- Reconciliation --------
# ================================


async def test_completion_takes_its_figures_from_the_touchbistro_report(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # Every source column comes from the TouchBistro report; the server
    # summary is the cross-check, not a source. The tipouts and the cash
    # balance are generated from those figures at the snapshotted rates.
    await _complete_a_cashout(
        cashier_client,
        ai_client,
        drain_outbox,
        tipout_departments=[TipoutDepartment.KITCHEN, TipoutDepartment.BAR],
    )

    (row,) = (await admin_client.get("/api/cashout/data")).json()

    assert row["foodNetSales"] == "800.00"
    assert row["drinkNetSales"] == "400.00"
    assert row["totalNetSales"] == "1200.00"
    assert row["cardPaymentTotal"] == "1234.56"
    assert row["cashPaymentTotal"] == "150.00"
    assert row["cardTipTotal"] == "180.00"

    # 400.00 * 0.0500 and 800.00 * 0.0300; the manager's 1200.00 * 0.0100 is
    # on every cashout; the unselected departments stay null.
    assert row["barTipout"] == "20.00"
    assert row["kitchenTipout"] == "24.00"
    assert row["managerTipout"] == "12.00"
    assert row["expoTipout"] is None
    assert row["hostTipout"] is None

    # Before tipouts, the house would owe 30.00. The 56.00 of tipouts
    # reverses the balance, so the employee owes the remaining 26.00.
    assert row["cashOwedToHouse"] == "26.00"
    assert row["cashOwedToEmployee"] is None


async def test_expo_tips_out_on_food_sales(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # Expo and host share a 1% rate but not a base: expo takes it on the
    # 800.00 of food, host on the 1200.00 total.
    await _complete_a_cashout(
        cashier_client,
        ai_client,
        drain_outbox,
        tipout_departments=[TipoutDepartment.EXPO, TipoutDepartment.HOST],
    )

    (row,) = (await admin_client.get("/api/cashout/data")).json()

    assert row["expoTipout"] == "8.00"
    assert row["hostTipout"] == "12.00"
    assert row["managerTipout"] == "12.00"
    # 32.00 of tipouts against the 30.00 the house owed: 2.00 due to the house.
    assert row["cashOwedToHouse"] == "2.00"
    assert row["cashOwedToEmployee"] is None


async def test_fractional_tipout_and_house_balance_round_up(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 800.01 * 3.75% is 30.000375. The source figure remains exactly what the
    # report said, while the calculated tipout becomes 30.01. With the 12.00
    # manager tipout, that leaves 12.01 due to the house against the 30.00
    # card-tip deficit — the one cent of rounding included.
    monkeypatch.setattr(settings.tipout, "KITCHEN_RATE", Decimal("0.0375"))
    await _complete_with_touchbistro_overrides(
        cashier_client,
        ai_client,
        drain_outbox,
        overrides={"food_net_sales": "800.01"},
        tipout_departments=[TipoutDepartment.KITCHEN],
    )

    (row,) = (await admin_client.get("/api/cashout/data")).json()

    assert row["foodNetSales"] == "800.01"
    assert row["kitchenTipout"] == "30.01"
    assert row["cashOwedToHouse"] == "12.01"
    assert row["cashOwedToEmployee"] is None


async def test_each_department_rounds_before_the_final_balance(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # Bar is 5.0005 and kitchen is 24.0003 (the manager's 12.00 is exact).
    # Rounding each line produces 41.02 of tipouts and 11.02 due to the house;
    # rounding the unrounded 41.0008 total only once would produce 11.01.
    await _complete_with_touchbistro_overrides(
        cashier_client,
        ai_client,
        drain_outbox,
        overrides={
            "food_net_sales": "800.01",
            "drink_net_sales": "100.01",
        },
        tipout_departments=[TipoutDepartment.BAR, TipoutDepartment.KITCHEN],
    )

    (row,) = (await admin_client.get("/api/cashout/data")).json()

    assert row["barTipout"] == "5.01"
    assert row["kitchenTipout"] == "24.01"
    assert row["cashOwedToHouse"] == "11.02"
    assert row["cashOwedToEmployee"] is None


async def test_tipouts_reduce_cash_owed_to_employee(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # Card tips exceed cash by 30.00, but the 8.00 expo and 12.00 manager
    # tipouts consume 20.00 of that before the house owes the remaining 10.00.
    await _complete_a_cashout(
        cashier_client,
        ai_client,
        drain_outbox,
        tipout_departments=[TipoutDepartment.EXPO],
    )

    (row,) = (await admin_client.get("/api/cashout/data")).json()

    assert row["expoTipout"] == "8.00"
    assert row["managerTipout"] == "12.00"
    assert row["cashOwedToHouse"] is None
    assert row["cashOwedToEmployee"] == "10.00"


async def test_tipouts_increase_cash_owed_to_house(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    submission_id = await create_submission(cashier_client)
    touchbistro, summary = await upload_reconcilable_documents(
        cashier_client,
        submission_id,
        ai_client=ai_client,
        drain=drain_outbox,
    )
    await verify_analysis(
        cashier_client,
        touchbistro["id"],
        {
            "verifiedData": {
                **TOUCHBISTRO_EXTRACTED,
                "cash_payment_total": "200.00",
            }
        },
    )
    await verify_analysis(cashier_client, summary["id"])
    await complete_submission(
        cashier_client,
        submission_id,
        tipout_departments=[TipoutDepartment.KITCHEN],
    )

    (row,) = (await admin_client.get("/api/cashout/data")).json()

    # Cash exceeds card tips by 20.00; the 24.00 kitchen and 12.00 manager
    # tipouts are also due to the house, producing a 56.00 final balance.
    assert row["kitchenTipout"] == "24.00"
    assert row["managerTipout"] == "12.00"
    assert row["cashOwedToHouse"] == "56.00"
    assert row["cashOwedToEmployee"] is None


async def test_cash_balance_is_empty_when_tipouts_make_an_exact_tie(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A 2.25% kitchen rate makes that tipout exactly 18.00, which with the
    # 12.00 manager tipout cancels the 30.00 that the house would otherwise
    # owe the employee.
    monkeypatch.setattr(settings.tipout, "KITCHEN_RATE", Decimal("0.0225"))
    await _complete_a_cashout(
        cashier_client,
        ai_client,
        drain_outbox,
        tipout_departments=[TipoutDepartment.KITCHEN],
    )

    (row,) = (await admin_client.get("/api/cashout/data")).json()

    assert row["kitchenTipout"] == "18.00"
    assert row["managerTipout"] == "12.00"
    assert row["cashOwedToHouse"] is None
    assert row["cashOwedToEmployee"] is None


async def test_complete_without_a_touchbistro_report_conflicts(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # A cashout with only terminal summaries has no source for its figures.
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    summary = await create_upload(cashier_client, submission_id, drain=drain_outbox)
    await verify_analysis(cashier_client, summary["id"])

    body = await _try_complete(cashier_client, submission_id)

    assert body["_status"] == 409
    assert body["code"] == "RECONCILE_TOUCHBISTRO_MISSING"


async def test_complete_with_two_touchbistro_reports_conflicts(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # Exactly one, and there is no rule for picking between two.
    configure_touchbistro(ai_client)
    submission_id = await create_submission(cashier_client)
    first = await create_upload(cashier_client, submission_id, drain=drain_outbox)
    second = await create_upload(
        cashier_client, submission_id, drain=drain_outbox, file=SAMPLE_PNG_UPLOAD
    )
    await verify_analysis(cashier_client, first["id"])
    await verify_analysis(cashier_client, second["id"])

    body = await _try_complete(cashier_client, submission_id)

    assert body["_status"] == 409
    assert body["code"] == "RECONCILE_TOUCHBISTRO_DUPLICATE"


async def test_complete_with_mismatched_card_payments_conflicts(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    submission_id = await create_submission(cashier_client)
    touchbistro, summary = await upload_reconcilable_documents(
        cashier_client, submission_id, ai_client=ai_client, drain=drain_outbox
    )
    await verify_analysis(cashier_client, touchbistro["id"])
    # Verified with a grand total that no longer adds up to the report's card
    # payments — the count still matches, so this is the amount check alone.
    await verify_analysis(
        cashier_client,
        summary["id"],
        {"verifiedData": {**SERVER_SUMMARY_EXTRACTED, "grand_total": "1000.00"}},
    )

    body = await _try_complete(cashier_client, submission_id)

    assert body["_status"] == 409
    assert body["code"] == "RECONCILE_CARD_PAYMENT_MISMATCH"


async def test_complete_with_mismatched_transaction_counts_conflicts(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    submission_id = await create_submission(cashier_client)
    touchbistro, summary = await upload_reconcilable_documents(
        cashier_client, submission_id, ai_client=ai_client, drain=drain_outbox
    )
    await verify_analysis(cashier_client, touchbistro["id"])
    # The amounts still agree; only the transaction count is off.
    await verify_analysis(
        cashier_client,
        summary["id"],
        {
            "verifiedData": {
                **SERVER_SUMMARY_EXTRACTED,
                "grand_total_transaction_count": 41,
            }
        },
    )

    body = await _try_complete(cashier_client, submission_id)

    assert body["_status"] == 409
    assert body["code"] == "RECONCILE_CARD_TRANSACTION_MISMATCH"


async def test_complete_with_unreadable_verified_data_conflicts(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # Verification takes the corrections as typed, so an unreadable one only
    # surfaces here — as a conflict on the cashout, not a 422 on a field.
    submission_id = await create_submission(cashier_client)
    touchbistro, summary = await upload_reconcilable_documents(
        cashier_client, submission_id, ai_client=ai_client, drain=drain_outbox
    )
    await verify_analysis(cashier_client, summary["id"])
    await verify_analysis(
        cashier_client,
        touchbistro["id"],
        {"verifiedData": {**TOUCHBISTRO_EXTRACTED, "card_tip_total": "not a number"}},
    )

    body = await _try_complete(cashier_client, submission_id)

    assert body["_status"] == 409
    assert body["code"] == "RECONCILE_DOCUMENT_DATA_INVALID"


async def test_complete_without_card_payments_needs_no_server_summary(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # Nothing exempts a cashout from the cross-check: with no summaries both
    # sums are zero, which reconciles against a shift that took no card
    # payments and nothing else.
    configure_touchbistro(ai_client)
    submission_id = await create_submission(cashier_client)
    touchbistro = await create_upload(cashier_client, submission_id, drain=drain_outbox)
    await verify_analysis(
        cashier_client,
        touchbistro["id"],
        {
            "verifiedData": {
                **TOUCHBISTRO_EXTRACTED,
                "card_payment_total": "0.00",
                "card_transaction_count": 0,
            }
        },
    )

    await complete_submission(cashier_client, submission_id)

    (row,) = (await admin_client.get("/api/cashout/data")).json()
    assert row["cardPaymentTotal"] == "0.00"
