# backend/tests/integration/test_cashout.py

from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.document_ai import DocumentClassification
from app.features.cashout.analyses.types import DocumentAnalysisStatus
from app.features.cashout.extraction.types import CashoutDocumentClassification
from app.features.cashout.models import CashoutDocument, CashoutSubmission
from app.features.cashout.submissions.types import CashoutSubmissionStatus
from tests.support.api import csrf_headers
from tests.support.cashout import (
    complete_submission,
    configure_manual_note,
    create_submission,
    poll_analysis,
    unsubmit_submission,
    unverify_analysis,
    upload_document,
    verify_analysis,
)
from tests.support.documents import SAMPLE_PDF_BYTES, SAMPLE_PNG_UPLOAD
from tests.support.fakes import FakeAIClient, FakeDocumentStorage
from tests.support.fixtures.clients import ClientFactory
from tests.support.fixtures.outbox import OutboxDrain

# ================================
# --------- Happy path -----------
# ================================


async def test_full_cashout_flow(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_manual_note(ai_client)

    submission_id = await create_submission(cashier_client)

    # Upload returns immediately with an EXTRACTING analysis.
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    assert created["status"] == DocumentAnalysisStatus.EXTRACTING.value
    assert created["extractedDataJson"] is None

    # Polling picks up the background extraction's outcome.
    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value
    assert analysis["classification"] == CashoutDocumentClassification.MANUAL_NOTE.value
    assert analysis["classificationConfidence"] == 0.95
    assert analysis["extractedDataJson"] == {"note": "cash $100"}
    assert analysis["extractionConfidence"] == 0.9
    assert analysis["issues"] == [{"path": "note", "message": "partially legible"}]

    # The detail view embeds each document's analysis.
    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["status"] == CashoutSubmissionStatus.PROCESSING.value
    document = detail["documents"][0]
    assert document["analysis"]["id"] == analysis["id"]
    assert (
        document["analysis"]["classification"]
        == CashoutDocumentClassification.MANUAL_NOTE.value
    )

    # The cashier verifies with a correction.
    verified = await verify_analysis(
        cashier_client,
        analysis["id"],
        {"verifiedData": {"note": "cash $100 confirmed"}},
    )
    assert verified["status"] == DocumentAnalysisStatus.VERIFIED.value
    assert verified["verifiedDataJson"] == {"note": "cash $100 confirmed"}
    assert verified["verifiedByUserId"] is not None
    assert verified["verifiedAt"] is not None

    # Completing reconciles the verified analyses into a cashout data row and
    # records the completing user (the employee, completing their own).
    completed = await complete_submission(cashier_client, submission_id)
    assert completed["status"] == CashoutSubmissionStatus.COMPLETED.value
    assert completed["completedByUserId"] == completed["employeeUserId"]
    assert completed["firstCompletedAt"] is not None
    assert completed["updatedAt"] is not None

    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["data"] is not None
    assert detail["data"]["submissionId"] == submission_id


async def test_verify_without_corrections_confirms_extraction(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    analysis = await poll_analysis(cashier_client, created["id"])

    verified = await verify_analysis(cashier_client, analysis["id"])

    assert verified["verifiedDataJson"] == analysis["extractedDataJson"]


# ================================
# --------- Read endpoints -------
# ================================


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


async def test_document_content_served_to_owner_and_admin(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    url = f"/api/cashout/documents/{created['cashoutDocumentId']}/content"

    owner = await cashier_client.get(url)
    assert owner.status_code == 200
    assert owner.headers["content-type"].startswith("application/pdf")
    assert owner.content == SAMPLE_PDF_BYTES

    admin = await admin_client.get(url)
    assert admin.status_code == 200


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


# ================================
# ------- Delete endpoints -------
# ================================


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
    configure_manual_note(ai_client)
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
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    analysis = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    await verify_analysis(cashier_client, analysis["id"])
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


async def test_delete_document_from_processing_submission(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    drain_outbox: OutboxDrain,
) -> None:
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    analysis = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    assert storage.objects

    response = await cashier_client.delete(
        f"/api/cashout/documents/{analysis['cashoutDocumentId']}",
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 204
    assert response.content == b""
    assert storage.objects == {}
    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["documents"] == []
    missing_analysis = await cashier_client.get(
        f"/api/cashout/analyses/{analysis['id']}"
    )
    assert missing_analysis.status_code == 404


async def test_delete_document_after_completion_conflicts(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    drain_outbox: OutboxDrain,
) -> None:
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    analysis = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    await verify_analysis(cashier_client, analysis["id"])
    await complete_submission(cashier_client, submission_id)

    response = await cashier_client.delete(
        f"/api/cashout/documents/{analysis['cashoutDocumentId']}",
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "SUBMISSION_COMPLETED"
    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert len(detail["documents"]) == 1
    assert storage.objects


async def test_delete_document_requires_employee_or_admin(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    make_client: ClientFactory,
    drain_outbox: OutboxDrain,
) -> None:
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    analysis = await upload_document(cashier_client, submission_id, drain=drain_outbox)

    # Plain staff cannot remove a document from someone else's cashout.
    other = await make_client(email="other@test.com")
    forbidden = await other.delete(
        f"/api/cashout/documents/{analysis['cashoutDocumentId']}",
        headers=csrf_headers(other),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"
    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert len(detail["documents"]) == 1
    assert storage.objects

    # An admin can.
    response = await admin_client.delete(
        f"/api/cashout/documents/{analysis['cashoutDocumentId']}",
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 204, response.text
    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["documents"] == []
    assert storage.objects == {}


# ================================
# ---------- Unsubmit ------------
# ================================


async def test_admin_unsubmit_reopens_completed_cashout(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_manual_note(ai_client)
    cashier_id = (await cashier_client.get("/api/users/me")).json()["id"]
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    await verify_analysis(cashier_client, created["id"])
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
    second = await upload_document(
        cashier_client, submission_id, drain=drain_outbox, file=SAMPLE_PNG_UPLOAD
    )
    await verify_analysis(cashier_client, second["id"])

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


async def test_unsubmit_is_admin_only(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    await verify_analysis(cashier_client, created["id"])
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
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    await verify_analysis(cashier_client, created["id"])
    await complete_submission(cashier_client, submission_id)
    await unsubmit_submission(admin_client, submission_id)

    removed = await cashier_client.delete(
        f"/api/cashout/documents/{created['cashoutDocumentId']}",
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


# ================================
# ---------- Unverify ------------
# ================================


async def test_unverify_reopens_verification_for_editing(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # The full edit loop: verify, unverify, re-verify with a correction,
    # complete.
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    await verify_analysis(cashier_client, created["id"])

    # Unverify clears the verification outcome but keeps the extraction, so
    # the verification form has fields to re-render.
    reopened = await unverify_analysis(cashier_client, created["id"])
    assert reopened["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value
    assert reopened["verifiedDataJson"] is None
    assert reopened["verifiedByUserId"] is None
    assert reopened["verifiedAt"] is None
    assert reopened["extractedDataJson"] == {"note": "cash $100"}

    reverified = await verify_analysis(
        cashier_client,
        created["id"],
        {"verifiedData": {"note": "cash $100 corrected"}},
    )
    assert reverified["status"] == DocumentAnalysisStatus.VERIFIED.value
    assert reverified["verifiedDataJson"] == {"note": "cash $100 corrected"}

    completed = await complete_submission(cashier_client, submission_id)
    assert completed["status"] == CashoutSubmissionStatus.COMPLETED.value


async def test_unverify_non_verified_analysis_conflicts(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    # Extracted but never verified: nothing to send back.

    response = await cashier_client.post(
        f"/api/cashout/analyses/{created['id']}/unverify",
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ANALYSIS_NOT_VERIFIED"


async def test_unverify_after_completion_conflicts(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    await verify_analysis(cashier_client, created["id"])
    await complete_submission(cashier_client, submission_id)

    # A completed cashout is frozen; it must be unsubmitted first.
    response = await cashier_client.post(
        f"/api/cashout/analyses/{created['id']}/unverify",
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "SUBMISSION_COMPLETED"
    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.VERIFIED.value


async def test_unverify_requires_employee_or_admin(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    make_client: ClientFactory,
    drain_outbox: OutboxDrain,
) -> None:
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    await verify_analysis(cashier_client, created["id"])

    # Plain staff cannot edit someone else's cashout.
    other = await make_client(email="other@test.com")
    forbidden = await other.post(
        f"/api/cashout/analyses/{created['id']}/unverify",
        headers=csrf_headers(other),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"

    # An admin can, on anyone's submission.
    reopened = await unverify_analysis(admin_client, created["id"])
    assert reopened["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value


async def test_admin_corrects_completed_cashout_via_unsubmit_and_unverify(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # The admin correction flow: unsubmit reopens the cashout, unverify
    # reopens one analysis, and re-completing reconciles fresh data.
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    await verify_analysis(cashier_client, created["id"])
    await complete_submission(cashier_client, submission_id)

    await unsubmit_submission(admin_client, submission_id)
    reopened = await unverify_analysis(admin_client, created["id"])
    assert reopened["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value

    reverified = await verify_analysis(
        admin_client,
        created["id"],
        {"verifiedData": {"note": "cash $90 (admin corrected)"}},
    )
    assert reverified["verifiedDataJson"] == {"note": "cash $90 (admin corrected)"}

    recompleted = await complete_submission(admin_client, submission_id)
    assert recompleted["status"] == CashoutSubmissionStatus.COMPLETED.value
    detail = (
        await admin_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["data"] is not None
    assert detail["data"]["submissionId"] == submission_id


# ================================
# ------- Guard conditions -------
# ================================


async def test_create_submission_anytime(cashier_client: AsyncClient) -> None:
    # Cashouts are not shift-locked: a user can open one at any time, and
    # can open more than one.
    first = await create_submission(cashier_client)
    second = await create_submission(cashier_client)

    assert first != second


async def test_upload_rejects_unsupported_content_type(
    cashier_client: AsyncClient,
) -> None:
    submission_id = await create_submission(cashier_client)

    response = await cashier_client.post(
        f"/api/cashout/submissions/{submission_id}/documents",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "UNSUPPORTED_DOCUMENT_TYPE"


async def test_upload_rejects_oversized_document(
    cashier_client: AsyncClient,
    storage: FakeDocumentStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Shrink the configured limit rather than posting a full-size body.
    monkeypatch.setattr(settings.storage, "MAX_DOCUMENT_SIZE_MB", 1)
    submission_id = await create_submission(cashier_client)
    stored_before = len(storage.objects)
    oversized = SAMPLE_PDF_BYTES + b"\0" * settings.storage.MAX_DOCUMENT_SIZE_BYTES

    response = await cashier_client.post(
        f"/api/cashout/submissions/{submission_id}/documents",
        files={"file": ("oversized.pdf", oversized, "application/pdf")},
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "DOCUMENT_TOO_LARGE"
    # Rejected before its bytes were written to storage.
    assert len(storage.objects) == stored_before


async def test_upload_rejects_duplicate_document(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    drain_outbox: OutboxDrain,
) -> None:
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    await upload_document(cashier_client, submission_id, drain=drain_outbox)
    stored_before = len(storage.objects)

    # Same bytes again (filename doesn't matter): rejected by checksum.
    response = await cashier_client.post(
        f"/api/cashout/submissions/{submission_id}/documents",
        files={"file": ("renamed.pdf", SAMPLE_PDF_BYTES, "application/pdf")},
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "DOCUMENT_DUPLICATE"
    # The duplicate was rejected before its bytes were written to storage.
    assert len(storage.objects) == stored_before

    # The same file is still allowed in a *different* submission.
    other_submission_id = await create_submission(cashier_client)
    await upload_document(cashier_client, other_submission_id, drain=drain_outbox)


async def test_unknown_document_completes_without_data(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    ai_client.classification = DocumentClassification[CashoutDocumentClassification](
        value=None, confidence=0.3
    )

    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)

    # A document the AI can't place is not a failure: the analysis completes
    # as UNKNOWN with nothing to extract, awaiting the cashier.
    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value
    assert analysis["classification"] == CashoutDocumentClassification.UNKNOWN.value
    assert analysis["classificationConfidence"] == 0.3
    assert analysis["extractedDataJson"] is None
    assert analysis["errorCode"] is None
    assert analysis["errorMessage"] is None


async def test_failed_extraction_and_retry(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    from app.features.cashout.analysis_errors import analysis_error_message
    from app.integrations.ai import AIAnalysisError, AIErrorCode

    ai_client.error = AIAnalysisError(
        AIErrorCode.DOCUMENT_REJECTED, "declined: raw provider text"
    )

    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)

    # The provider failure is recorded on the analysis as FAILED.
    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.FAILED.value
    assert analysis["errorCode"] == AIErrorCode.DOCUMENT_REJECTED.value
    # The raw provider text must not leak; a safe mapped message is surfaced.
    assert analysis["errorMessage"] == analysis_error_message(
        AIErrorCode.DOCUMENT_REJECTED.value
    )
    assert "raw provider text" not in analysis["errorMessage"]

    # A FAILED analysis cannot be verified.
    blocked = await cashier_client.post(
        f"/api/cashout/analyses/{analysis['id']}/verify",
        json={},
        headers=csrf_headers(cashier_client),
    )
    assert blocked.status_code == 409

    # Retry once the provider recovers.
    ai_client.error = None
    configure_manual_note(ai_client)
    retry = await cashier_client.post(
        f"/api/cashout/documents/{analysis['cashoutDocumentId']}/extract",
        headers=csrf_headers(cashier_client),
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["status"] == DocumentAnalysisStatus.EXTRACTING.value

    # The retry only enqueued the extraction; run it before polling.
    await drain_outbox()
    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value
    assert analysis["errorCode"] is None


async def test_retry_extraction_from_needs_verification(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # A retry is not reserved for FAILED: an unverified extraction can be
    # re-run too (e.g. the cashier wants a fresh read of the document).
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value

    retry = await cashier_client.post(
        f"/api/cashout/documents/{created['cashoutDocumentId']}/extract",
        headers=csrf_headers(cashier_client),
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["status"] == DocumentAnalysisStatus.EXTRACTING.value

    await drain_outbox()
    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value
    assert analysis["extractedDataJson"] == {"note": "cash $100"}


async def test_verify_twice_conflicts(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    await verify_analysis(cashier_client, created["id"])

    response = await cashier_client.post(
        f"/api/cashout/analyses/{created['id']}/verify",
        json={},
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ANALYSIS_VERIFIED"


async def test_complete_requires_every_analysis_verified(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    await upload_document(
        cashier_client, submission_id, drain=drain_outbox
    )  # extracted, never verified

    response = await cashier_client.post(
        f"/api/cashout/submissions/{submission_id}/complete",
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
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    await verify_analysis(cashier_client, created["id"])

    # Plain staff cannot close out someone else's cashout (admins can — see
    # test_admin_can_manage_another_users_submission).
    other = await make_client(email="other@test.com")
    response = await other.post(
        f"/api/cashout/submissions/{submission_id}/complete",
        headers=csrf_headers(other),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_admin_can_manage_another_users_submission(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # Admins have full control over every cashout: everything the employee
    # can do on their own submission, an admin can do on anyone's — with the
    # admin recorded as the acting user.
    configure_manual_note(ai_client)
    cashier_id = (await cashier_client.get("/api/users/me")).json()["id"]
    admin_id = (await admin_client.get("/api/users/me")).json()["id"]
    submission_id = await create_submission(cashier_client)

    # Upload and retry extraction on the employee's behalf.
    created = await upload_document(admin_client, submission_id, drain=drain_outbox)
    retried = await admin_client.post(
        f"/api/cashout/documents/{created['cashoutDocumentId']}/extract",
        headers=csrf_headers(admin_client),
    )
    assert retried.status_code == 200, retried.text
    await drain_outbox()
    analysis = await poll_analysis(admin_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value

    # Verify: the admin is recorded as the verifying user.
    verified = await verify_analysis(admin_client, analysis["id"])
    assert verified["verifiedByUserId"] == admin_id

    # The document records the admin as its uploader; the submission keeps
    # the cashier as its employee.
    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["employeeUserId"] == cashier_id
    assert detail["documents"][0]["uploadedByUserId"] == admin_id

    # Complete: the admin is recorded as the completer, and the first
    # completion time is stamped.
    completed = await complete_submission(admin_client, submission_id)
    assert completed["status"] == CashoutSubmissionStatus.COMPLETED.value
    assert completed["employeeUserId"] == cashier_id
    assert completed["completedByUserId"] == admin_id
    assert completed["firstCompletedAt"] is not None

    # A completed cashout cannot be completed again — by anyone.
    again = await admin_client.post(
        f"/api/cashout/submissions/{submission_id}/complete",
        headers=csrf_headers(admin_client),
    )
    assert again.status_code == 409
    assert again.json()["code"] == "SUBMISSION_COMPLETED"


async def test_cannot_access_another_users_submission(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    make_client: ClientFactory,
    drain_outbox: OutboxDrain,
) -> None:
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)

    # A second, unrelated cashier can see neither the submission nor poll
    # its analyses.
    other = await make_client(email="other@test.com")
    submission_response = await other.get(f"/api/cashout/submissions/{submission_id}")
    analysis_response = await other.get(f"/api/cashout/analyses/{created['id']}")

    assert submission_response.status_code == 403
    assert submission_response.json()["code"] == "FORBIDDEN"
    assert analysis_response.status_code == 403
    assert analysis_response.json()["code"] == "FORBIDDEN"
