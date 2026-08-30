# backend/tests/integration/test_cashout_submissions.py

from __future__ import annotations

from datetime import date
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cashout.analyses.types import DocumentAnalysisStatus
from app.features.cashout.data.types import TipoutDepartment
from app.features.cashout.models import CashoutDocument, CashoutSubmission
from app.features.cashout.submissions.types import CashoutSubmissionStatus
from tests.support.api import csrf_headers
from tests.support.cashout import (
    TOUCHBISTRO_EXTRACTED,
    complete_submission,
    completion_body,
    configure_server_summary,
    create_submission,
    prepare_completable_submission,
    unsubmit_submission,
    unverify_analysis,
    upload_document,
    upload_reconcilable_documents,
    verify_analysis,
)
from tests.support.fakes import FakeAIClient, FakeDocumentStorage
from tests.support.fixtures.clients import ClientFactory
from tests.support.fixtures.outbox import OutboxDrain


async def test_list_submissions_scoped_by_role(
    cashier_client: AsyncClient, admin_client: AsyncClient
) -> None:
    mine = await create_submission(cashier_client)
    theirs = await create_submission(admin_client)

    cashier_list = (await cashier_client.get("/api/cashout/submissions")).json()
    assert [s["id"] for s in cashier_list] == [mine]
    assert cashier_list[0]["employee"]["email"] == "cashier@test.com"

    admin_list = (await admin_client.get("/api/cashout/submissions")).json()
    assert {s["id"] for s in admin_list} == {mine, theirs}


async def test_delete_empty_processing_submission(
    cashier_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    submission_id = await create_submission(cashier_client)

    response = await cashier_client.delete(
        f"/api/cashout/submissions/{submission_id}",
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 204
    assert response.content == b""
    missing = await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    assert missing.status_code == 404
    # No traces (no documents, no data, never completed): a hard delete —
    # the row itself is gone, not merely stamped.
    stmt = select(CashoutSubmission).where(CashoutSubmission.id == UUID(submission_id))
    assert (await db_session.execute(stmt)).scalar_one_or_none() is None


async def test_delete_processing_submission_with_documents_soft_deletes(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    drain_outbox: OutboxDrain,
    db_session: AsyncSession,
) -> None:
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    analysis = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    assert storage.objects

    response = await cashier_client.delete(
        f"/api/cashout/submissions/{submission_id}",
        headers=csrf_headers(cashier_client),
    )
    assert response.status_code == 204
    assert response.content == b""

    # Gone from the API: list, detail, and (via the stranded submission) the
    # analysis all behave as if the cashout never existed.
    listed = (await cashier_client.get("/api/cashout/submissions")).json()
    assert submission_id not in [entry["id"] for entry in listed]
    missing = await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    assert missing.status_code == 404
    missing_analysis = await cashier_client.get(
        f"/api/cashout/analyses/{analysis['id']}"
    )
    assert missing_analysis.status_code == 404

    # But it was a soft delete: the submission row is stamped, its document
    # row survives, and the stored bytes were not cleaned up.
    stmt = select(CashoutSubmission).where(CashoutSubmission.id == UUID(submission_id))
    row = (await db_session.execute(stmt)).scalar_one()
    assert row.deleted_at is not None
    document_stmt = select(CashoutDocument).where(
        CashoutDocument.cashout_submission_id == UUID(submission_id)
    )
    assert (await db_session.execute(document_stmt)).scalar_one() is not None
    assert storage.objects


async def test_delete_completed_submission_is_restricted(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    drain_outbox: OutboxDrain,
) -> None:
    submission_id = await prepare_completable_submission(
        cashier_client, ai_client=ai_client, drain=drain_outbox
    )
    await complete_submission(cashier_client, submission_id)

    response = await cashier_client.delete(
        f"/api/cashout/submissions/{submission_id}",
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "SUBMISSION_COMPLETED"
    detail = await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    assert detail.status_code == 200
    assert detail.json()["data"] is not None
    assert storage.objects


async def test_delete_submission_requires_employee_or_admin(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    make_client: ClientFactory,
) -> None:
    submission_id = await create_submission(cashier_client)

    # Plain staff cannot cancel someone else's cashout.
    other = await make_client(email="other@test.com")
    forbidden = await other.delete(
        f"/api/cashout/submissions/{submission_id}",
        headers=csrf_headers(other),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"
    assert (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).status_code == 200

    # An admin can.
    response = await admin_client.delete(
        f"/api/cashout/submissions/{submission_id}",
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 204, response.text
    assert (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).status_code == 404


# ================================
# ---------- Unsubmit ------------
# ================================


async def test_admin_unsubmit_reopens_completed_cashout(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    cashier_id = (await cashier_client.get("/api/users/me")).json()["id"]
    submission_id = await create_submission(cashier_client)
    touchbistro, summary = await upload_reconcilable_documents(
        cashier_client, submission_id, ai_client=ai_client, drain=drain_outbox
    )
    await verify_analysis(cashier_client, touchbistro["id"])
    await verify_analysis(cashier_client, summary["id"])
    completed = await complete_submission(cashier_client, submission_id)
    first_completed_at = completed["firstCompletedAt"]
    assert first_completed_at is not None
    first_data_id = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()["data"]["id"]

    # The admin reopens it: back to PROCESSING, the reconciled data is gone,
    # the current completer clears — but the first completion stays on record.
    reopened = await unsubmit_submission(admin_client, submission_id)
    assert reopened["status"] == CashoutSubmissionStatus.PROCESSING.value
    assert reopened["completedByUserId"] is None
    assert reopened["firstCompletedAt"] == first_completed_at

    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["data"] is None
    # The analyses stay verified — nothing to re-verify on re-completion.
    assert (
        detail["documents"][0]["analysis"]["status"]
        == DocumentAnalysisStatus.VERIFIED.value
    )

    # The employee can edit again without any admin help: editability keys on
    # PROCESSING, which the unsubmit restored.
    await unverify_analysis(cashier_client, touchbistro["id"])
    await verify_analysis(
        cashier_client,
        touchbistro["id"],
        {"verifiedData": {**TOUCHBISTRO_EXTRACTED, "card_tip_total": "200.00"}},
    )

    # Re-completing reconciles a fresh data row and re-stamps the completer.
    recompleted = await complete_submission(cashier_client, submission_id)
    assert recompleted["status"] == CashoutSubmissionStatus.COMPLETED.value
    assert recompleted["completedByUserId"] == cashier_id
    assert recompleted["firstCompletedAt"] == first_completed_at
    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["data"] is not None
    assert detail["data"]["id"] != first_data_id
    # Reconciled afresh, so the edit is in the new row.
    assert detail["data"]["cardTipTotal"] == "200.00"


async def test_tipout_snapshot_survives_unsubmit(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    submission_id = await create_submission(cashier_client)

    # Never completed: no snapshot yet.
    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["tipoutDepartments"] is None

    touchbistro, summary = await upload_reconcilable_documents(
        cashier_client, submission_id, ai_client=ai_client, drain=drain_outbox
    )
    await verify_analysis(cashier_client, touchbistro["id"])
    await verify_analysis(cashier_client, summary["id"])
    completed = await complete_submission(
        cashier_client,
        submission_id,
        tipout_departments=(TipoutDepartment.KITCHEN, TipoutDepartment.BAR),
    )
    # The snapshot is stored sorted, independent of the order submitted.
    assert completed["tipoutDepartments"] == ["bar", "kitchen"]

    # Unsubmit drops the data row but keeps the snapshot, so the completion
    # form can start from the previous choice.
    reopened = await unsubmit_submission(admin_client, submission_id)
    assert reopened["status"] == CashoutSubmissionStatus.PROCESSING.value
    assert reopened["tipoutDepartments"] == ["bar", "kitchen"]

    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["status"] == CashoutSubmissionStatus.PROCESSING.value
    assert detail["data"] is None
    assert detail["tipoutDepartments"] == ["bar", "kitchen"]

    # Re-completing with a different set overwrites the snapshot.
    recompleted = await complete_submission(
        cashier_client,
        submission_id,
        tipout_departments=(TipoutDepartment.HOST, TipoutDepartment.EXPO),
    )
    assert recompleted["tipoutDepartments"] == ["expo", "host"]


async def test_unsubmit_is_admin_only(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    submission_id = await prepare_completable_submission(
        cashier_client, ai_client=ai_client, drain=drain_outbox
    )
    await complete_submission(cashier_client, submission_id)

    # The employee (plain staff) cannot reopen their own completed cashout —
    # that is the point of the endpoint.
    response = await cashier_client.post(
        f"/api/cashout/submissions/{submission_id}/unsubmit",
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["status"] == CashoutSubmissionStatus.COMPLETED.value


async def test_unsubmit_processing_submission_conflicts(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
) -> None:
    submission_id = await create_submission(cashier_client)

    response = await admin_client.post(
        f"/api/cashout/submissions/{submission_id}/unsubmit",
        headers=csrf_headers(admin_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "SUBMISSION_NOT_COMPLETED"


async def test_delete_unsubmitted_then_emptied_submission_soft_deletes(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
    db_session: AsyncSession,
) -> None:
    # Complete once, unsubmit, then strip the cashout down to nothing: the
    # completion on record (first_completed_at) still blocks a hard delete.
    submission_id = await create_submission(cashier_client)
    touchbistro, summary = await upload_reconcilable_documents(
        cashier_client, submission_id, ai_client=ai_client, drain=drain_outbox
    )
    await verify_analysis(cashier_client, touchbistro["id"])
    await verify_analysis(cashier_client, summary["id"])
    await complete_submission(cashier_client, submission_id)
    await unsubmit_submission(admin_client, submission_id)

    for analysis in (touchbistro, summary):
        removed = await cashier_client.delete(
            f"/api/cashout/documents/{analysis['cashoutDocumentId']}",
            headers=csrf_headers(cashier_client),
        )
        assert removed.status_code == 204, removed.text

    response = await cashier_client.delete(
        f"/api/cashout/submissions/{submission_id}",
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 204
    missing = await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    assert missing.status_code == 404
    # Soft-deleted, not removed: the row survives with its completion history.
    stmt = select(CashoutSubmission).where(CashoutSubmission.id == UUID(submission_id))
    row = (await db_session.execute(stmt)).scalar_one()
    assert row.deleted_at is not None
    assert row.first_completed_at is not None


async def test_create_submission_anytime(cashier_client: AsyncClient) -> None:
    # Cashouts are not shift-locked: a user can open one at any time — say,
    # catching up several missed days at once — as long as each is for its
    # own business day.
    first = await create_submission(cashier_client, business_date="2026-08-27")
    second = await create_submission(cashier_client, business_date="2026-08-28")

    assert first != second


async def test_create_duplicate_day_conflicts(cashier_client: AsyncClient) -> None:
    # One live cashout per business day: the partial unique index rejects a
    # second, and the constraint violation surfaces as a clean 409.
    await create_submission(cashier_client, business_date="2026-08-28")

    response = await cashier_client.post(
        "/api/cashout/submissions",
        json={"businessDate": "2026-08-28"},
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "SUBMISSION_DUPLICATE_DAY"


async def test_cancelled_cashout_does_not_block_the_day(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client, business_date="2026-08-28")
    await upload_document(cashier_client, submission_id, drain=drain_outbox)

    # Cancelling soft-deletes (the document is a trace), so the row survives —
    # but the unique index is partial, and a stamped row no longer holds the
    # day.
    response = await cashier_client.delete(
        f"/api/cashout/submissions/{submission_id}",
        headers=csrf_headers(cashier_client),
    )
    assert response.status_code == 204

    replacement = await create_submission(cashier_client, business_date="2026-08-28")
    assert replacement != submission_id


async def test_two_users_may_share_a_business_day(
    cashier_client: AsyncClient, make_client: ClientFactory
) -> None:
    # The day is unique per employee, not per restaurant: two cashiers each
    # open their own cashout for the same day.
    other = await make_client(email="other@test.com")

    await create_submission(cashier_client, business_date="2026-08-28")
    await create_submission(other, business_date="2026-08-28")


async def test_create_submission_with_business_date(
    cashier_client: AsyncClient,
) -> None:
    # A cashier catching up a missed day opens the cashout for that day.
    response = await cashier_client.post(
        "/api/cashout/submissions",
        json={"businessDate": "2026-08-28"},
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["businessDate"] == "2026-08-28"

    # Stored, not merely echoed: the detail read returns the same day.
    detail = await cashier_client.get(f"/api/cashout/submissions/{created['id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["businessDate"] == "2026-08-28"


async def test_create_submission_without_body_defaults_business_date(
    cashier_client: AsyncClient,
) -> None:
    # A bare POST (no body at all) still works and lands on today.
    submission_id = await create_submission(cashier_client)

    detail = await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["businessDate"] == date.today().isoformat()


async def test_complete_requires_every_analysis_verified(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    await upload_document(
        cashier_client, submission_id, drain=drain_outbox
    )  # extracted, never verified

    response = await cashier_client.post(
        f"/api/cashout/submissions/{submission_id}/complete",
        json=completion_body(),
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "SUBMISSION_UNVERIFIED"


async def test_complete_requires_employee_or_admin(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    make_client: ClientFactory,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    await verify_analysis(cashier_client, created["id"])

    # Plain staff cannot close out someone else's cashout (admins can — see
    # test_admin_can_manage_another_users_submission).
    other = await make_client(email="other@test.com")
    response = await other.post(
        f"/api/cashout/submissions/{submission_id}/complete",
        json=completion_body(),
        headers=csrf_headers(other),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
