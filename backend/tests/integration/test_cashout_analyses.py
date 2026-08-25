# backend/tests/integration/test_cashout_analyses.py

from __future__ import annotations

from httpx import AsyncClient

from app.document_ai import DocumentClassification
from app.features.cashout.analyses.types import DocumentAnalysisStatus
from app.features.cashout.extraction.types import CashoutDocumentClassification
from app.features.cashout.submissions.types import CashoutSubmissionStatus
from tests.support.api import csrf_headers
from tests.support.cashout import (
    complete_submission,
    configure_manual_note,
    create_submission,
    poll_analysis,
    unverify_analysis,
    upload_document,
    verify_analysis,
)
from tests.support.fakes import FakeAIClient
from tests.support.fixtures.clients import ClientFactory
from tests.support.fixtures.outbox import OutboxDrain


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
    from app.features.cashout.analyses.messages import analysis_error_message
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
