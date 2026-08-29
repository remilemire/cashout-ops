# backend/tests/integration/test_cashout_data.py

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.features.cashout.data.types import TipoutDepartment
from tests.support.cashout import (
    complete_submission,
    configure_server_summary,
    create_submission,
    upload_document,
    verify_analysis,
)
from tests.support.fakes import FakeAIClient
from tests.support.fixtures.outbox import OutboxDrain


async def _complete_a_cashout(
    client: AsyncClient,
    ai_client: FakeAIClient,
    drain: OutboxDrain,
    *,
    tipout_departments: list[TipoutDepartment],
) -> str:
    configure_server_summary(ai_client)
    submission_id = await create_submission(client)
    created = await upload_document(client, submission_id, drain=drain)
    await verify_analysis(client, created["id"])
    await complete_submission(
        client, submission_id, tipout_departments=tipout_departments
    )
    return submission_id


async def test_data_table_is_admin_only(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    await verify_analysis(cashier_client, created["id"])
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

    assert row["tipoutDepartments"] == ["bar", "expo"]


async def test_completion_snapshots_the_configured_rates(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A cashout closes against the rates in force at that moment, so the row
    # keeps its own copy rather than reading the configured value back later.
    monkeypatch.setattr(settings.tipout, "KITCHEN_RATE", Decimal("0.0350"))

    await _complete_a_cashout(
        cashier_client,
        ai_client,
        drain_outbox,
        tipout_departments=[TipoutDepartment.KITCHEN],
    )

    (row,) = (await admin_client.get("/api/cashout/data")).json()
    assert row["kitchenTipoutRate"] == "0.0350"

    # Changing the rate afterwards must not restate the closed cashout.
    monkeypatch.setattr(settings.tipout, "KITCHEN_RATE", Decimal("0.9900"))

    (unchanged,) = (await admin_client.get("/api/cashout/data")).json()
    assert unchanged["kitchenTipoutRate"] == "0.0350"


async def test_unreconciled_cashout_reports_no_figures(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # Until service.reconcile fills the source figures, the generated tipouts
    # have nothing to compute from — a completed-but-unreconciled cashout.
    await _complete_a_cashout(
        cashier_client,
        ai_client,
        drain_outbox,
        tipout_departments=[TipoutDepartment.KITCHEN],
    )

    (row,) = (await admin_client.get("/api/cashout/data")).json()

    assert row["foodNetSales"] is None
    assert row["kitchenTipout"] is None
    assert row["cashOwedToHouse"] is None
    assert row["cashOwedToEmployee"] is None
