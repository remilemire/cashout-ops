# backend/tests/integration/test_cashout_submissions.py

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cashout.analyses.types import DocumentAnalysisStatus
from app.features.cashout.data.types import TipoutDepartment
from app.features.cashout.models import CashoutSubmission, CashoutUpload
from app.features.cashout.submissions.types import CashoutSubmissionStatus
from tests.support.api import csrf_headers
from tests.support.cashout import (
    TOUCHBISTRO_EXTRACTED,
    complete_submission,
    completion_body,
    configure_server_summary,
    create_submission,
    create_upload,
    prepare_completable_submission,
    unsubmit_submission,
    unverify_analysis,
    update_business_date,
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


async def test_submission_detail_lists_uploads_oldest_first(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
    db_session: AsyncSession,
) -> None:
    submission_id = await create_submission(cashier_client)
    first, second = await upload_reconcilable_documents(
        cashier_client, submission_id, ai_client=ai_client, drain=drain_outbox
    )

    # Backdate the second upload, so creation order is the reverse of
    # insertion order and only a real ORDER BY can tell them apart.
    upload = await db_session.get(CashoutUpload, UUID(second["cashoutUploadId"]))
    assert upload is not None
    upload.created_at = datetime(2026, 7, 1, tzinfo=UTC)
    await db_session.commit()

    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert [upload["id"] for upload in detail["uploads"]] == [
        second["cashoutUploadId"],
        first["cashoutUploadId"],
    ]


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
    # No traces (no uploads, no data, never completed): a hard delete —
    # the row itself is gone, not merely stamped.
    stmt = select(CashoutSubmission).where(CashoutSubmission.id == UUID(submission_id))
    assert (await db_session.execute(stmt)).scalar_one_or_none() is None


async def test_delete_processing_submission_with_uploads_soft_deletes(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    drain_outbox: OutboxDrain,
    db_session: AsyncSession,
) -> None:
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    analysis = await create_upload(cashier_client, submission_id, drain=drain_outbox)
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

    # But it was a soft delete: the submission row is stamped, its upload
    # row survives, and the stored bytes were not cleaned up.
    stmt = select(CashoutSubmission).where(CashoutSubmission.id == UUID(submission_id))
    row = (await db_session.execute(stmt)).scalar_one()
    assert row.deleted_at is not None
    upload_stmt = select(CashoutUpload).where(
        CashoutUpload.cashout_submission_id == UUID(submission_id)
    )
    assert (await db_session.execute(upload_stmt)).scalar_one() is not None
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
        detail["uploads"][0]["analyses"][0]["status"]
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
    # The snapshot is the reconciled list: sorted, independent of the order
    # submitted, with the manager reconciliation adds to every cashout.
    assert completed["tipoutDepartments"] == ["bar", "kitchen", "manager"]

    # Unsubmit drops the data row but keeps the snapshot, so the completion
    # form can start from the previous choice.
    reopened = await unsubmit_submission(admin_client, submission_id)
    assert reopened["status"] == CashoutSubmissionStatus.PROCESSING.value
    assert reopened["tipoutDepartments"] == ["bar", "kitchen", "manager"]

    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["status"] == CashoutSubmissionStatus.PROCESSING.value
    assert detail["data"] is None
    assert detail["tipoutDepartments"] == ["bar", "kitchen", "manager"]

    # Re-completing with a different set overwrites the snapshot.
    recompleted = await complete_submission(
        cashier_client,
        submission_id,
        tipout_departments=(TipoutDepartment.HOST, TipoutDepartment.EXPO),
    )
    assert recompleted["tipoutDepartments"] == ["expo", "host", "manager"]


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
            f"/api/cashout/uploads/{analysis['cashoutUploadId']}",
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
    await create_upload(cashier_client, submission_id, drain=drain_outbox)

    # Cancelling soft-deletes (the upload is a trace), so the row survives —
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


# ================================
# -------- Business date ---------
# ================================


async def test_update_business_date_after_upload(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # The first upload used to lock the day. A cashier who picked the wrong
    # day can now fix it with uploads already in.
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client, business_date="2026-08-27")
    await create_upload(cashier_client, submission_id, drain=drain_outbox)

    updated = await update_business_date(
        cashier_client, submission_id, business_date="2026-08-28"
    )

    assert updated["businessDate"] == "2026-08-28"
    assert updated["status"] == CashoutSubmissionStatus.PROCESSING.value
    # Stored, not merely echoed: detail and list both read the new day.
    detail = await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["businessDate"] == "2026-08-28"
    (listed,) = (await cashier_client.get("/api/cashout/submissions")).json()
    assert listed["id"] == submission_id
    assert listed["businessDate"] == "2026-08-28"


async def test_admin_updates_another_users_business_date(
    cashier_client: AsyncClient, admin_client: AsyncClient
) -> None:
    submission_id = await create_submission(cashier_client, business_date="2026-08-27")

    updated = await update_business_date(
        admin_client, submission_id, business_date="2026-08-28"
    )

    assert updated["businessDate"] == "2026-08-28"
    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["businessDate"] == "2026-08-28"


async def test_update_business_date_requires_employee_or_admin(
    cashier_client: AsyncClient, make_client: ClientFactory
) -> None:
    submission_id = await create_submission(cashier_client, business_date="2026-08-27")

    # Plain staff cannot re-date someone else's cashout.
    other = await make_client(email="other@test.com")
    response = await other.patch(
        f"/api/cashout/submissions/{submission_id}",
        json={"businessDate": "2026-08-28"},
        headers=csrf_headers(other),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["businessDate"] == "2026-08-27"


async def test_update_business_date_on_completed_conflicts(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # Completion locks the cashout, business date included: the reconciled
    # data row reads its day through the submission, so it must not shift
    # underneath the admin data table.
    submission_id = await prepare_completable_submission(
        cashier_client,
        ai_client=ai_client,
        drain=drain_outbox,
        business_date="2026-08-27",
    )
    await complete_submission(cashier_client, submission_id)

    response = await cashier_client.patch(
        f"/api/cashout/submissions/{submission_id}",
        json={"businessDate": "2026-08-28"},
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "SUBMISSION_COMPLETED"
    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["businessDate"] == "2026-08-27"
    assert detail["status"] == CashoutSubmissionStatus.COMPLETED.value


async def test_update_business_date_to_occupied_day_conflicts(
    cashier_client: AsyncClient,
) -> None:
    # One live cashout per business day holds for moves too: the partial
    # unique index that rejects a duplicate creation rejects the UPDATE when
    # the request commits, and surfaces as the same clean 409.
    first = await create_submission(cashier_client, business_date="2026-08-27")
    await create_submission(cashier_client, business_date="2026-08-28")

    response = await cashier_client.patch(
        f"/api/cashout/submissions/{first}",
        json={"businessDate": "2026-08-28"},
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "SUBMISSION_DUPLICATE_DAY"
    detail = (await cashier_client.get(f"/api/cashout/submissions/{first}")).json()
    assert detail["businessDate"] == "2026-08-27"


async def test_update_business_date_vacates_the_old_day(
    cashier_client: AsyncClient,
) -> None:
    # Moving a cashout off a day frees it for a new one.
    submission_id = await create_submission(cashier_client, business_date="2026-08-27")
    await update_business_date(
        cashier_client, submission_id, business_date="2026-08-28"
    )

    replacement = await create_submission(cashier_client, business_date="2026-08-27")

    assert replacement != submission_id


async def test_update_business_date_to_same_day_is_noop(
    cashier_client: AsyncClient,
) -> None:
    # Re-saving the current day must not trip the unique index on itself.
    submission_id = await create_submission(cashier_client, business_date="2026-08-27")

    updated = await update_business_date(
        cashier_client, submission_id, business_date="2026-08-27"
    )

    assert updated["businessDate"] == "2026-08-27"
    assert updated["status"] == CashoutSubmissionStatus.PROCESSING.value


async def test_unsubmit_restores_business_date_editing(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # Editability keys on PROCESSING, which an unsubmit restores: the date is
    # locked while completed, open again afterwards, and the re-completed
    # data row reports the corrected day.
    submission_id = await prepare_completable_submission(
        cashier_client,
        ai_client=ai_client,
        drain=drain_outbox,
        business_date="2026-08-27",
    )
    await complete_submission(cashier_client, submission_id)

    locked = await cashier_client.patch(
        f"/api/cashout/submissions/{submission_id}",
        json={"businessDate": "2026-08-28"},
        headers=csrf_headers(cashier_client),
    )
    assert locked.status_code == 409
    assert locked.json()["code"] == "SUBMISSION_COMPLETED"

    await unsubmit_submission(admin_client, submission_id)
    updated = await update_business_date(
        cashier_client, submission_id, business_date="2026-08-28"
    )
    assert updated["businessDate"] == "2026-08-28"

    await complete_submission(cashier_client, submission_id)
    rows = (await admin_client.get("/api/cashout/data")).json()
    (row,) = [r for r in rows if r["submission"]["id"] == submission_id]
    assert row["submission"]["businessDate"] == "2026-08-28"


async def test_update_business_date_rejects_missing_null_or_malformed(
    cashier_client: AsyncClient,
) -> None:
    # Unlike creation there is no "today" to fall back on: the body must name
    # the day.
    submission_id = await create_submission(cashier_client, business_date="2026-08-27")

    for body in ({}, {"businessDate": None}, {"businessDate": "not-a-date"}):
        response = await cashier_client.patch(
            f"/api/cashout/submissions/{submission_id}",
            json=body,
            headers=csrf_headers(cashier_client),
        )

        assert response.status_code == 422, response.text
        payload = response.json()
        assert payload["code"] == "VALIDATION_FAILED"
        assert [issue["path"] for issue in payload["issues"]] == [["businessDate"]]

    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["businessDate"] == "2026-08-27"


async def test_update_business_date_rejects_other_fields(
    cashier_client: AsyncClient,
) -> None:
    submission_id = await create_submission(cashier_client, business_date="2026-08-27")

    response = await cashier_client.patch(
        f"/api/cashout/submissions/{submission_id}",
        json={"businessDate": "2026-08-28", "status": "completed"},
        headers=csrf_headers(cashier_client),
    )

    # BaseIn forbids extras: the endpoint re-dates and nothing else — in
    # particular it cannot complete the cashout.
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"
    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["status"] == CashoutSubmissionStatus.PROCESSING.value
    assert detail["businessDate"] == "2026-08-27"


async def test_update_unknown_submission_not_found(
    cashier_client: AsyncClient,
) -> None:
    response = await cashier_client.patch(
        f"/api/cashout/submissions/{uuid4()}",
        json={"businessDate": "2026-08-28"},
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "SUBMISSION_NOT_FOUND"


async def test_complete_requires_every_analysis_verified(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    await create_upload(
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
    created = await create_upload(cashier_client, submission_id, drain=drain_outbox)
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
