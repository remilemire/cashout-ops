#
# End-to-end workflows that cross the cashout sub-features; per-sub-feature
# coverage lives in test_cashout_submissions / test_cashout_uploads /
# test_cashout_analyses / test_cashout_data.

from __future__ import annotations

from httpx import AsyncClient

from app.features.cashout.analyses.types import DocumentAnalysisStatus
from app.features.cashout.extraction.types import CashoutDocumentClassification
from app.features.cashout.submissions.types import CashoutSubmissionStatus
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
    poll_analysis,
    unsubmit_submission,
    unverify_analysis,
    upload_reconcilable_documents,
    verify_analysis,
)
from tests.support.documents import SAMPLE_PNG_UPLOAD
from tests.support.fakes import FakeAIClient
from tests.support.fixtures.clients import ClientFactory
from tests.support.fixtures.outbox import OutboxDrain


async def test_full_cashout_flow(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_touchbistro(ai_client)

    submission_id = await create_submission(cashier_client)

    # Upload returns immediately with an EXTRACTING analysis.
    created = await create_upload(cashier_client, submission_id, drain=drain_outbox)
    assert created["status"] == DocumentAnalysisStatus.EXTRACTING.value
    assert created["extractedDataJson"] is None
    assert created["schemaVersion"] is None

    # Polling picks up the background extraction's outcome.
    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value
    assert (
        analysis["classification"]
        == CashoutDocumentClassification.TOUCHBISTRO_REPORT.value
    )
    assert analysis["classificationConfidence"] == 0.95
    assert analysis["extractedDataJson"] == TOUCHBISTRO_EXTRACTED
    assert analysis["extractionConfidence"] == 0.9
    # The extraction records which shape of its schema it wrote.
    assert analysis["schemaName"] == "TouchBistroReportData"
    assert analysis["schemaVersion"] == 2

    # The cashout also needs the terminal summary its card payments are
    # cross-checked against.
    configure_server_summary(ai_client)
    created_summary = await create_upload(
        cashier_client, submission_id, drain=drain_outbox, file=SAMPLE_PNG_UPLOAD
    )
    summary = await poll_analysis(cashier_client, created_summary["id"])
    assert summary["extractedDataJson"] == SERVER_SUMMARY_EXTRACTED
    assert summary["issues"] == [
        {"path": "grand_total", "message": "partially legible"}
    ]

    # The detail view embeds each upload's analysis.
    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["status"] == CashoutSubmissionStatus.PROCESSING.value
    assert {upload["analyses"][0]["id"] for upload in detail["uploads"]} == {
        analysis["id"],
        summary["id"],
    }
    upload = next(
        entry
        for entry in detail["uploads"]
        if entry["analyses"][0]["id"] == analysis["id"]
    )
    assert (
        upload["analyses"][0]["classification"]
        == CashoutDocumentClassification.TOUCHBISTRO_REPORT.value
    )

    # The cashier verifies the summary as extracted, and the TouchBistro
    # report with a correction — to a figure the cross-check does not read,
    # so the pair still reconciles.
    await verify_analysis(cashier_client, summary["id"])
    verified = await verify_analysis(
        cashier_client,
        analysis["id"],
        {"verifiedData": {**TOUCHBISTRO_EXTRACTED, "card_tip_total": "200.00"}},
    )
    assert verified["status"] == DocumentAnalysisStatus.VERIFIED.value
    assert verified["verifiedDataJson"] == {
        **TOUCHBISTRO_EXTRACTED,
        "card_tip_total": "200.00",
    }
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
    # The source figures are the TouchBistro report as verified — the
    # correction included.
    assert detail["data"]["totalNetSales"] == "1200.00"
    assert detail["data"]["cardPaymentTotal"] == "1234.56"
    assert detail["data"]["cardTipTotal"] == "200.00"


async def test_admin_corrects_completed_cashout_via_unsubmit_and_unverify(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # The admin correction flow: unsubmit reopens the cashout, unverify
    # reopens one analysis, and re-completing reconciles fresh data.
    submission_id = await create_submission(cashier_client)
    touchbistro, summary = await upload_reconcilable_documents(
        cashier_client, submission_id, ai_client=ai_client, drain=drain_outbox
    )
    await verify_analysis(cashier_client, touchbistro["id"])
    await verify_analysis(cashier_client, summary["id"])
    await complete_submission(cashier_client, submission_id)

    await unsubmit_submission(admin_client, submission_id)
    reopened = await unverify_analysis(admin_client, touchbistro["id"])
    assert reopened["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value

    reverified = await verify_analysis(
        admin_client,
        touchbistro["id"],
        {"verifiedData": {**TOUCHBISTRO_EXTRACTED, "card_tip_total": "210.00"}},
    )
    assert reverified["verifiedDataJson"] == {
        **TOUCHBISTRO_EXTRACTED,
        "card_tip_total": "210.00",
    }

    recompleted = await complete_submission(admin_client, submission_id)
    assert recompleted["status"] == CashoutSubmissionStatus.COMPLETED.value
    detail = (
        await admin_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["data"] is not None
    assert detail["data"]["submissionId"] == submission_id
    # The correction reached the data: re-completion reconciles afresh.
    assert detail["data"]["cardTipTotal"] == "210.00"


async def test_admin_can_manage_another_users_submission(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # Admins have full control over every cashout: everything the employee
    # can do on their own submission, an admin can do on anyone's — with the
    # admin recorded as the acting user.
    configure_touchbistro(ai_client)
    cashier_id = (await cashier_client.get("/api/users/me")).json()["id"]
    admin_id = (await admin_client.get("/api/users/me")).json()["id"]
    submission_id = await create_submission(cashier_client)

    # Upload and retry extraction on the employee's behalf.
    created = await create_upload(admin_client, submission_id, drain=drain_outbox)
    retried = await admin_client.post(
        f"/api/cashout/analyses/{created['id']}/extract",
        headers=csrf_headers(admin_client),
    )
    assert retried.status_code == 200, retried.text
    await drain_outbox()
    analysis = await poll_analysis(admin_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value

    # Verify: the admin is recorded as the verifying user.
    verified = await verify_analysis(admin_client, analysis["id"])
    assert verified["verifiedByUserId"] == admin_id

    # The terminal summary the TouchBistro card payments reconcile against.
    configure_server_summary(ai_client)
    summary = await create_upload(
        admin_client, submission_id, drain=drain_outbox, file=SAMPLE_PNG_UPLOAD
    )
    await verify_analysis(admin_client, summary["id"])

    # The upload records the admin as its uploader; the submission keeps
    # the cashier as its employee.
    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["employeeUserId"] == cashier_id
    assert detail["uploads"][0]["uploadedByUserId"] == admin_id

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
        json=completion_body(),
        headers=csrf_headers(admin_client),
    )
    assert again.status_code == 409
    assert again.json()["code"] == "SUBMISSION_COMPLETED"


async def test_extract_with_corrected_classification_skips_ai_classify(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await create_upload(cashier_client, submission_id, drain=drain_outbox)

    # Only the extraction stays configured: a classify call would now fail the
    # fake (and land the analysis FAILED), so a NEEDS_VERIFICATION outcome
    # proves the corrected rerun skipped it.
    ai_client.classification = None
    response = await cashier_client.post(
        f"/api/cashout/analyses/{created['id']}/extract",
        json={
            "classification": CashoutDocumentClassification.SERVER_SUMMARY_REPORT.value
        },
        headers=csrf_headers(cashier_client),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == DocumentAnalysisStatus.EXTRACTING.value
    await drain_outbox()

    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value
    assert (
        analysis["classification"]
        == CashoutDocumentClassification.SERVER_SUMMARY_REPORT.value
    )
    # The corrected value is the user's assertion, not a model score.
    assert analysis["classificationConfidence"] is None
    assert analysis["extractedDataJson"] == SERVER_SUMMARY_EXTRACTED
    assert analysis["extractionConfidence"] == 0.9


async def test_extract_without_body_still_runs_the_full_pipeline(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await create_upload(cashier_client, submission_id, drain=drain_outbox)

    # The pre-existing retry: no body at all.
    response = await cashier_client.post(
        f"/api/cashout/analyses/{created['id']}/extract",
        headers=csrf_headers(cashier_client),
    )
    assert response.status_code == 200, response.text
    await drain_outbox()

    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value
    assert (
        analysis["classification"]
        == CashoutDocumentClassification.SERVER_SUMMARY_REPORT.value
    )
    # Classification confidence is retained alongside the extracted data.
    assert analysis["classificationConfidence"] == 0.95
    assert analysis["extractedDataJson"] == SERVER_SUMMARY_EXTRACTED


async def test_extract_rejects_an_invalid_classification_value(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await create_upload(cashier_client, submission_id, drain=drain_outbox)

    response = await cashier_client.post(
        f"/api/cashout/analyses/{created['id']}/extract",
        json={"classification": "coffee_receipt"},
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"


async def test_cannot_access_another_users_submission(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    make_client: ClientFactory,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await create_upload(cashier_client, submission_id, drain=drain_outbox)

    # A second, unrelated cashier can see neither the submission nor poll
    # its analyses.
    other = await make_client(email="other@test.com")
    submission_response = await other.get(f"/api/cashout/submissions/{submission_id}")
    analysis_response = await other.get(f"/api/cashout/analyses/{created['id']}")

    assert submission_response.status_code == 403
    assert submission_response.json()["code"] == "FORBIDDEN"
    assert analysis_response.status_code == 403
    assert analysis_response.json()["code"] == "FORBIDDEN"
