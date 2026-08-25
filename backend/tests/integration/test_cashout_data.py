# backend/tests/integration/test_cashout_data.py

from __future__ import annotations

from httpx import AsyncClient

from tests.support.cashout import (
    complete_submission,
    configure_manual_note,
    create_submission,
    upload_document,
    verify_analysis,
)
from tests.support.fakes import FakeAIClient
from tests.support.fixtures.outbox import OutboxDrain


async def test_data_table_is_admin_only(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    await verify_analysis(cashier_client, created["id"])
    await complete_submission(cashier_client, submission_id)

    forbidden = await cashier_client.get("/api/cashout/data")
    assert forbidden.status_code == 403

    allowed = await admin_client.get("/api/cashout/data")
    assert allowed.status_code == 200
    assert [row["submissionId"] for row in allowed.json()] == [submission_id]
