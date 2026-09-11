#
# Manual document entry: adding a document with typed-in details (no AI
# involved), and converting a failed or unverified analysis into a manual
# one. The AI-driven intake path is covered in test_cashout /
# test_cashout_uploads / test_cashout_analyses.

from __future__ import annotations

import json

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.document_ai import DocumentClassificationResponse
from app.features.cashout.analyses.types import DocumentAnalysisStatus
from app.features.cashout.extraction.types import CashoutDocumentClassification
from app.features.cashout.submissions.types import CashoutSubmissionStatus
from tests.support.api import csrf_headers
from tests.support.cashout import (
    SERVER_SUMMARY_EXTRACTED,
    complete_submission,
    configure_server_summary,
    create_manual_upload,
    create_submission,
    create_upload,
    enter_manual_analysis,
    manual_entry_body,
    poll_analysis,
    touchbistro_manual_entry_body,
    unverify_analysis,
    verify_analysis,
)
from tests.support.documents import SAMPLE_PDF_UPLOAD
from tests.support.fakes import FakeAIClient
from tests.support.fixtures.clients import ClientFactory
from tests.support.fixtures.outbox import OutboxDrain

# A second file with different bytes, for tests that need a non-duplicate.
OTHER_PDF_UPLOAD = ("other.pdf", b"%PDF-1.4 other fake bytes", "application/pdf")
THIRD_PDF_UPLOAD = ("third.pdf", b"%PDF-1.4 third fake bytes", "application/pdf")


async def test_manual_upload_lands_verified_without_ai(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    cashier_id = (await cashier_client.get("/api/users/me")).json()["id"]
    submission_id = await create_submission(cashier_client)

    analysis = await create_manual_upload(
        cashier_client, submission_id, body=manual_entry_body()
    )

    # Typing the values is the verification: the analysis is born VERIFIED,
    # with the null provider/model marking it as manual.
    assert analysis["status"] == DocumentAnalysisStatus.VERIFIED.value
    assert analysis["provider"] is None
    assert analysis["model"] is None
    assert (
        analysis["classification"]
        == CashoutDocumentClassification.SERVER_SUMMARY_REPORT.value
    )
    assert analysis["classificationConfidence"] is None
    assert analysis["schemaName"] == "ServerSummaryReportData"
    assert analysis["schemaVersion"] == 1
    # The messy typed input was coerced by the schema — Money strips the
    # comma, the count string parses to an int — and both data fields carry
    # the same validated dump.
    assert analysis["extractedDataJson"] == SERVER_SUMMARY_EXTRACTED
    assert analysis["verifiedDataJson"] == SERVER_SUMMARY_EXTRACTED
    assert analysis["extractionConfidence"] is None
    assert analysis["issues"] is None
    assert analysis["errorCode"] is None
    assert analysis["errorMessage"] is None
    assert analysis["completedAt"] is not None
    assert analysis["verifiedByUserId"] == cashier_id
    assert analysis["verifiedAt"] is not None

    # No AI call was made and nothing was enqueued for the dispatcher.
    assert ai_client.calls == []
    assert await drain_outbox() == 0

    # A fully manual cashout completes like any other — once the TouchBistro
    # report the figures are reconciled from is on it too.
    await create_manual_upload(
        cashier_client,
        submission_id,
        body=touchbistro_manual_entry_body(),
        file=OTHER_PDF_UPLOAD,
    )
    completed = await complete_submission(cashier_client, submission_id)
    assert completed["status"] == CashoutSubmissionStatus.COMPLETED.value


async def test_manual_upload_rejects_an_unrecognized_classification(
    cashier_client: AsyncClient,
) -> None:
    submission_id = await create_submission(cashier_client)

    # A manual entry asserts a document type the extraction schemas know; a
    # value outside the enum (`unknown` is no longer one of them) is refused
    # as an invalid option.
    response = await cashier_client.post(
        f"/api/cashout/submissions/{submission_id}/uploads/manual",
        files={"file": SAMPLE_PDF_UPLOAD},
        data={"payload": json.dumps(manual_entry_body(classification="unknown"))},
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED"
    [issue] = body["issues"]
    assert issue["code"] == "enum"
    assert issue["path"] == ["classification"]

    # Rejected before the upload was stored.
    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["uploads"] == []


async def test_manual_upload_rejects_invalid_data(
    cashier_client: AsyncClient,
) -> None:
    submission_id = await create_submission(cashier_client)

    # Non-numeric money and extra fields are invalid; omitted values remain
    # unknown until reconciliation enforces completeness.
    response = await cashier_client.post(
        f"/api/cashout/submissions/{submission_id}/uploads/manual",
        files={"file": SAMPLE_PDF_UPLOAD},
        data={
            "payload": json.dumps(
                manual_entry_body(
                    data={"grand_total": "not-a-number", "till_number": "7"}
                )
            )
        },
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED"
    issues = {(issue["code"], tuple(issue["path"])) for issue in body["issues"]}
    assert issues == {
        ("decimal_parsing", ("grandTotal",)),
        ("extra_forbidden", ("tillNumber",)),
    }

    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["uploads"] == []


async def test_manual_upload_rejects_duplicate_file(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    await create_upload(cashier_client, submission_id, drain=drain_outbox)

    # The same bytes again, this time via manual entry: the checksum check
    # applies to both intake routes.
    response = await cashier_client.post(
        f"/api/cashout/submissions/{submission_id}/uploads/manual",
        files={"file": SAMPLE_PDF_UPLOAD},
        data={"payload": json.dumps(manual_entry_body())},
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "UPLOAD_DUPLICATE"


async def test_manual_upload_after_completion_conflicts(
    cashier_client: AsyncClient,
) -> None:
    submission_id = await create_submission(cashier_client)
    await create_manual_upload(cashier_client, submission_id, body=manual_entry_body())
    await create_manual_upload(
        cashier_client,
        submission_id,
        body=touchbistro_manual_entry_body(),
        file=OTHER_PDF_UPLOAD,
    )
    await complete_submission(cashier_client, submission_id)

    response = await cashier_client.post(
        f"/api/cashout/submissions/{submission_id}/uploads/manual",
        files={"file": THIRD_PDF_UPLOAD},
        data={"payload": json.dumps(manual_entry_body())},
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "SUBMISSION_COMPLETED"


async def test_convert_failed_analysis_to_manual(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    from app.integrations.ai import AIAnalysisError, AIErrorCode

    ai_client.error = AIAnalysisError(
        AIErrorCode.CONTENT_REFUSED, "declined: raw provider text"
    )
    submission_id = await create_submission(cashier_client)
    created = await create_upload(cashier_client, submission_id, drain=drain_outbox)
    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.FAILED.value

    # Instead of retrying the AI, the cashier types the values in.
    entered = await enter_manual_analysis(
        cashier_client, created["id"], manual_entry_body()
    )

    assert entered["id"] == created["id"]
    assert entered["status"] == DocumentAnalysisStatus.VERIFIED.value
    assert entered["provider"] is None
    assert entered["model"] is None
    # The failed attempt's outcome does not survive under the manual entry.
    assert entered["errorCode"] is None
    assert entered["errorMessage"] is None
    assert (
        entered["classification"]
        == CashoutDocumentClassification.SERVER_SUMMARY_REPORT.value
    )
    assert entered["extractedDataJson"] == SERVER_SUMMARY_EXTRACTED
    assert entered["verifiedDataJson"] == SERVER_SUMMARY_EXTRACTED


async def test_convert_unclassified_analysis_to_manual(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # The AI can't place the document, so the extraction fails; entering the
    # details manually is one of the ways out (the other being a retry).
    ai_client.classification = DocumentClassificationResponse[
        CashoutDocumentClassification
    ](value=None, confidence=0.3)
    submission_id = await create_submission(cashier_client)
    created = await create_upload(cashier_client, submission_id, drain=drain_outbox)
    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.FAILED.value

    entered = await enter_manual_analysis(
        cashier_client, created["id"], manual_entry_body()
    )

    assert entered["status"] == DocumentAnalysisStatus.VERIFIED.value
    assert entered["provider"] is None
    assert entered["errorCode"] is None
    assert entered["errorMessage"] is None
    assert (
        entered["classification"]
        == CashoutDocumentClassification.SERVER_SUMMARY_REPORT.value
    )
    assert entered["classificationConfidence"] is None
    assert entered["schemaName"] == "ServerSummaryReportData"
    assert entered["schemaVersion"] == 1
    assert entered["extractedDataJson"] == SERVER_SUMMARY_EXTRACTED


async def test_convert_verified_analysis_conflicts(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await create_upload(cashier_client, submission_id, drain=drain_outbox)
    await verify_analysis(cashier_client, created["id"])

    response = await cashier_client.post(
        f"/api/cashout/analyses/{created['id']}/manual",
        json=manual_entry_body(),
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ANALYSIS_VERIFIED"


async def test_convert_while_extracting_conflicts(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
) -> None:
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)

    # Upload without draining the outbox: the analysis is still EXTRACTING,
    # owned by the (not-yet-run) background job.
    response = await cashier_client.post(
        f"/api/cashout/submissions/{submission_id}/uploads",
        files={"file": SAMPLE_PDF_UPLOAD},
        headers=csrf_headers(cashier_client),
    )
    assert response.status_code == 201, response.text
    created = response.json()

    blocked = await cashier_client.post(
        f"/api/cashout/analyses/{created['id']}/manual",
        json=manual_entry_body(),
        headers=csrf_headers(cashier_client),
    )

    assert blocked.status_code == 409
    assert blocked.json()["code"] == "EXTRACTION_IN_PROGRESS"


async def test_unverify_manual_analysis_reopens_for_editing(
    cashier_client: AsyncClient,
) -> None:
    # A manual entry re-enters the ordinary verification loop: unverify keeps
    # the entered data (and the manual markers) so the form can re-render.
    submission_id = await create_submission(cashier_client)
    analysis = await create_manual_upload(
        cashier_client, submission_id, body=manual_entry_body()
    )

    reopened = await unverify_analysis(cashier_client, analysis["id"])
    assert reopened["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value
    assert reopened["provider"] is None
    assert reopened["schemaName"] == "ServerSummaryReportData"
    assert reopened["schemaVersion"] == 1
    assert reopened["extractedDataJson"] == SERVER_SUMMARY_EXTRACTED
    # Unverify preserves the verified data as the seed for the re-edit; for a
    # manual entry it equals what was typed in.
    assert reopened["verifiedDataJson"] == SERVER_SUMMARY_EXTRACTED
    assert reopened["verifiedByUserId"] is None
    assert reopened["verifiedAt"] is None

    reverified = await verify_analysis(
        cashier_client,
        analysis["id"],
        {"verifiedData": {**SERVER_SUMMARY_EXTRACTED, "grand_total": "1200.00"}},
    )
    assert reverified["status"] == DocumentAnalysisStatus.VERIFIED.value
    assert reverified["verifiedDataJson"] == {
        **SERVER_SUMMARY_EXTRACTED,
        "grand_total": "1200.00",
    }


async def test_manual_entry_requires_employee_or_admin(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    make_client: ClientFactory,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    admin_id = (await admin_client.get("/api/users/me")).json()["id"]
    submission_id = await create_submission(cashier_client)
    created = await create_upload(cashier_client, submission_id, drain=drain_outbox)

    # Plain staff can neither add a manual upload to someone else's cashout
    # nor convert one of its analyses.
    other = await make_client(email="other@test.com")
    upload_forbidden = await other.post(
        f"/api/cashout/submissions/{submission_id}/uploads/manual",
        files={"file": OTHER_PDF_UPLOAD},
        data={"payload": json.dumps(manual_entry_body())},
        headers=csrf_headers(other),
    )
    convert_forbidden = await other.post(
        f"/api/cashout/analyses/{created['id']}/manual",
        json=manual_entry_body(),
        headers=csrf_headers(other),
    )
    assert upload_forbidden.status_code == 403
    assert upload_forbidden.json()["code"] == "FORBIDDEN"
    assert convert_forbidden.status_code == 403
    assert convert_forbidden.json()["code"] == "FORBIDDEN"

    # An admin can, on anyone's submission — recorded as the verifier.
    entered = await enter_manual_analysis(
        admin_client, created["id"], manual_entry_body()
    )
    assert entered["status"] == DocumentAnalysisStatus.VERIFIED.value
    assert entered["verifiedByUserId"] == admin_id


async def test_commit_failure_surfaces_as_error_not_phantom_success(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """A failure at commit time must reach the client as the translated error.

    The conversion's UPDATE never flushes during the request, so its first
    trip to the database is the commit in get_db's teardown. Because the
    session is function-scoped (`DbSession`), that commit runs before the
    response is sent: the client gets the translated integrity error and the
    row keeps its pre-request state. Under request-scoped teardown the 200
    with a VERIFIED body was already on the wire when the commit failed — the
    UI showed success while the row stayed FAILED (a silent lost write).
    """
    from app.integrations.ai import AIAnalysisError, AIErrorCode

    ai_client.error = AIAnalysisError(AIErrorCode.CONTENT_REFUSED, "boom")
    submission_id = await create_submission(cashier_client)
    created = await create_upload(cashier_client, submission_id, drain=drain_outbox)

    # The incident's stale schema: provider NOT NULL. The manual conversion
    # nulls provider, violating it — but only at commit, since nothing
    # flushes on this path.
    async with db_sessionmaker() as db:
        await db.execute(
            text(
                "ALTER TABLE cashout_document_analyses"
                " ALTER COLUMN provider SET NOT NULL"
            )
        )
        await db.commit()
    try:
        response = await cashier_client.post(
            f"/api/cashout/analyses/{created['id']}/manual",
            json=manual_entry_body(),
            headers=csrf_headers(cashier_client),
        )

        # The not-null violation (SQLSTATE 23502) arrives through the shared
        # error contract, not as an apparent success.
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "VALIDATION_FAILED"

        # The transaction rolled back whole: the analysis still reads FAILED.
        analysis = await poll_analysis(cashier_client, created["id"])
        assert analysis["status"] == DocumentAnalysisStatus.FAILED.value
    finally:
        # The schema fixture is session-scoped; put the column back so other
        # tests see the real schema.
        async with db_sessionmaker() as db:
            await db.execute(
                text(
                    "ALTER TABLE cashout_document_analyses"
                    " ALTER COLUMN provider DROP NOT NULL"
                )
            )
            await db.commit()
