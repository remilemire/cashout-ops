# backend/tests/integration/test_cashout.py

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.document_ai import DocumentClassification
from app.features.cashout.types import (
    CashoutDocumentClassification,
    CashoutSubmissionStatus,
    DocumentAnalysisStatus,
)
from tests.support.api import csrf_headers
from tests.support.cashout import (
    complete_submission,
    configure_manual_note,
    create_submission,
    poll_analysis,
    upload_document,
    verify_analysis,
)
from tests.support.documents import SAMPLE_PDF_BYTES
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

    # Completing reconciles the verified analyses into a cashout data row.
    completed = await complete_submission(cashier_client, submission_id)
    assert completed["status"] == CashoutSubmissionStatus.COMPLETED.value

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
    assert cashier_list[0]["submittedBy"]["email"] == "cashier@test.com"

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


async def test_delete_processing_submission_removes_documents(
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
        f"/api/cashout/submissions/{submission_id}",
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 204
    assert storage.objects == {}
    missing_analysis = await cashier_client.get(
        f"/api/cashout/analyses/{analysis['id']}"
    )
    assert missing_analysis.status_code == 404


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
    assert response.json()["code"] == "SUBMISSION_HAS_DATA"
    detail = await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    assert detail.status_code == 200
    assert detail.json()["data"] is not None
    assert storage.objects


async def test_delete_submission_requires_owner(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
) -> None:
    submission_id = await create_submission(cashier_client)

    response = await admin_client.delete(
        f"/api/cashout/submissions/{submission_id}",
        headers=csrf_headers(admin_client),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
    assert (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).status_code == 200


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


async def test_delete_document_requires_owner(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    drain_outbox: OutboxDrain,
) -> None:
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    analysis = await upload_document(cashier_client, submission_id, drain=drain_outbox)

    response = await admin_client.delete(
        f"/api/cashout/documents/{analysis['cashoutDocumentId']}",
        headers=csrf_headers(admin_client),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert len(detail["documents"]) == 1
    assert storage.objects


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


async def test_complete_requires_owner(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_manual_note(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    await verify_analysis(cashier_client, created["id"])

    # Completion is the cashier's action; even an admin cannot close out
    # someone else's cashout.
    response = await admin_client.post(
        f"/api/cashout/submissions/{submission_id}/complete",
        headers=csrf_headers(admin_client),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


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
