# backend/tests/test_cashout.py

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from app.documents import DocumentAnalysis, DocumentClassification, FieldIssue
from app.features.cashout.extraction.schemas import ManualNoteData
from app.features.cashout.types import (
    CashoutDocumentType,
    CashoutSubmissionStatus,
    DocumentAnalysisStatus,
)

from .factories import csrf_headers
from .fakes import FakeAIClient, FakeDocumentStorage

PDF = ("receipt.pdf", b"%PDF-1.4 fake bytes", "application/pdf")


def _configure_manual_note(ai_client: FakeAIClient, note: str = "cash $100") -> None:
    ai_client.classification = DocumentClassification[CashoutDocumentType](
        value=CashoutDocumentType.MANUAL_NOTE, confidence=0.95
    )
    ai_client.extraction = DocumentAnalysis[ManualNoteData](
        data=ManualNoteData(note=note),
        confidence=0.9,
        issues=[FieldIssue(path="note", message="partially legible")],
    )


async def _create_submission(client: AsyncClient) -> str:
    response = await client.post(
        "/api/cashout/submissions", headers=csrf_headers(client)
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _upload_pdf(client: AsyncClient, submission_id: str) -> dict[str, Any]:
    """Upload a document; returns the freshly created EXTRACTING analysis."""
    response = await client.post(
        f"/api/cashout/submissions/{submission_id}/documents",
        files={"file": PDF},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _poll_analysis(client: AsyncClient, analysis_id: str) -> dict[str, Any]:
    """One poll is deterministic here: the ASGI transport awaits the whole
    request lifecycle, including the post-commit extraction job."""
    response = await client.get(f"/api/cashout/analyses/{analysis_id}")
    assert response.status_code == 200, response.text
    return response.json()


async def _verify(
    client: AsyncClient, analysis_id: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    response = await client.post(
        f"/api/cashout/analyses/{analysis_id}/verify",
        json=body or {},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    return response.json()


# ================================
# --------- Happy path -----------
# ================================


async def test_full_cashout_flow(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
) -> None:
    _configure_manual_note(ai_client)

    submission_id = await _create_submission(cashier_client)

    # Upload returns immediately with an EXTRACTING analysis.
    created = await _upload_pdf(cashier_client, submission_id)
    assert created["status"] == DocumentAnalysisStatus.EXTRACTING.value
    assert created["extractedDataJson"] is None

    # Polling picks up the background extraction's outcome.
    analysis = await _poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value
    assert analysis["classification"] == CashoutDocumentType.MANUAL_NOTE.value
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
    assert document["documentType"] == CashoutDocumentType.MANUAL_NOTE.value
    assert document["analysis"]["id"] == analysis["id"]

    # The cashier verifies with a correction.
    verified = await _verify(
        cashier_client,
        analysis["id"],
        {"verifiedData": {"note": "cash $100 confirmed"}},
    )
    assert verified["status"] == DocumentAnalysisStatus.VERIFIED.value
    assert verified["verifiedDataJson"] == {"note": "cash $100 confirmed"}
    assert verified["verifiedByUserId"] is not None
    assert verified["verifiedAt"] is not None

    # Completing reconciles the verified analyses into a cashout data row.
    complete = await cashier_client.post(
        f"/api/cashout/submissions/{submission_id}/complete",
        headers=csrf_headers(cashier_client),
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == CashoutSubmissionStatus.COMPLETED.value

    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert detail["data"] is not None
    assert detail["data"]["submissionId"] == submission_id


async def test_verify_without_corrections_confirms_extraction(
    cashier_client: AsyncClient, ai_client: FakeAIClient
) -> None:
    _configure_manual_note(ai_client)
    submission_id = await _create_submission(cashier_client)
    created = await _upload_pdf(cashier_client, submission_id)
    analysis = await _poll_analysis(cashier_client, created["id"])

    verified = await _verify(cashier_client, analysis["id"])

    assert verified["verifiedDataJson"] == analysis["extractedDataJson"]


# ================================
# --------- Read endpoints -------
# ================================


async def test_list_submissions_scoped_by_role(
    cashier_client: AsyncClient, admin_client: AsyncClient
) -> None:
    mine = await _create_submission(cashier_client)
    theirs = await _create_submission(admin_client)

    cashier_list = (await cashier_client.get("/api/cashout/submissions")).json()
    assert [s["id"] for s in cashier_list] == [mine]
    assert cashier_list[0]["submittedBy"]["email"] == "cashier@test.com"

    admin_list = (await admin_client.get("/api/cashout/submissions")).json()
    assert {s["id"] for s in admin_list} == {mine, theirs}


async def test_document_content_served_to_owner_and_admin(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
) -> None:
    _configure_manual_note(ai_client)
    submission_id = await _create_submission(cashier_client)
    created = await _upload_pdf(cashier_client, submission_id)
    url = f"/api/cashout/documents/{created['cashoutDocumentId']}/content"

    owner = await cashier_client.get(url)
    assert owner.status_code == 200
    assert owner.headers["content-type"].startswith("application/pdf")
    assert owner.content == PDF[1]

    admin = await admin_client.get(url)
    assert admin.status_code == 200


async def test_data_table_is_admin_only(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
) -> None:
    _configure_manual_note(ai_client)
    submission_id = await _create_submission(cashier_client)
    created = await _upload_pdf(cashier_client, submission_id)
    await _verify(cashier_client, created["id"])
    complete = await cashier_client.post(
        f"/api/cashout/submissions/{submission_id}/complete",
        headers=csrf_headers(cashier_client),
    )
    assert complete.status_code == 200, complete.text

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
    submission_id = await _create_submission(cashier_client)

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
) -> None:
    _configure_manual_note(ai_client)
    submission_id = await _create_submission(cashier_client)
    analysis = await _upload_pdf(cashier_client, submission_id)
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
) -> None:
    _configure_manual_note(ai_client)
    submission_id = await _create_submission(cashier_client)
    analysis = await _upload_pdf(cashier_client, submission_id)
    await _verify(cashier_client, analysis["id"])
    completed = await cashier_client.post(
        f"/api/cashout/submissions/{submission_id}/complete",
        headers=csrf_headers(cashier_client),
    )
    assert completed.status_code == 200, completed.text

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
    submission_id = await _create_submission(cashier_client)

    response = await admin_client.delete(
        f"/api/cashout/submissions/{submission_id}",
        headers=csrf_headers(admin_client),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
    assert (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).status_code == 200


# ================================
# ------- Guard conditions -------
# ================================


async def test_create_submission_anytime(cashier_client: AsyncClient) -> None:
    # Cashouts are not shift-locked: a user can open one at any time, and
    # can open more than one.
    first = await _create_submission(cashier_client)
    second = await _create_submission(cashier_client)

    assert first != second


async def test_upload_rejects_unsupported_content_type(
    cashier_client: AsyncClient,
) -> None:
    submission_id = await _create_submission(cashier_client)

    response = await cashier_client.post(
        f"/api/cashout/submissions/{submission_id}/documents",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "UNSUPPORTED_DOCUMENT_TYPE"


async def test_failed_extraction_and_retry(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
) -> None:
    from app.features.cashout.types import analysis_error_message
    from app.integrations.ai import AIAnalysisError, AIErrorCode

    ai_client.error = AIAnalysisError(
        AIErrorCode.REFUSED, "declined: raw provider text"
    )

    submission_id = await _create_submission(cashier_client)
    created = await _upload_pdf(cashier_client, submission_id)

    # The provider failure is recorded on the analysis as FAILED.
    analysis = await _poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.FAILED.value
    assert analysis["errorCode"] == AIErrorCode.REFUSED.value
    # The raw provider text must not leak; a safe mapped message is surfaced.
    assert analysis["errorMessage"] == analysis_error_message(AIErrorCode.REFUSED.value)
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
    _configure_manual_note(ai_client)
    retry = await cashier_client.post(
        f"/api/cashout/documents/{analysis['cashoutDocumentId']}/extract",
        headers=csrf_headers(cashier_client),
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["status"] == DocumentAnalysisStatus.EXTRACTING.value

    analysis = await _poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value
    assert analysis["errorCode"] is None


async def test_verify_twice_conflicts(
    cashier_client: AsyncClient, ai_client: FakeAIClient
) -> None:
    _configure_manual_note(ai_client)
    submission_id = await _create_submission(cashier_client)
    created = await _upload_pdf(cashier_client, submission_id)
    await _verify(cashier_client, created["id"])

    response = await cashier_client.post(
        f"/api/cashout/analyses/{created['id']}/verify",
        json={},
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ANALYSIS_VERIFIED"


async def test_complete_requires_every_analysis_verified(
    cashier_client: AsyncClient, ai_client: FakeAIClient
) -> None:
    _configure_manual_note(ai_client)
    submission_id = await _create_submission(cashier_client)
    await _upload_pdf(cashier_client, submission_id)  # extracted, never verified

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
) -> None:
    _configure_manual_note(ai_client)
    submission_id = await _create_submission(cashier_client)
    created = await _upload_pdf(cashier_client, submission_id)
    await _verify(cashier_client, created["id"])

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
    app: object,
) -> None:
    from httpx import ASGITransport

    _configure_manual_note(ai_client)
    submission_id = await _create_submission(cashier_client)
    created = await _upload_pdf(cashier_client, submission_id)

    # A second, unrelated cashier can see neither the submission nor poll
    # its analyses.
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as other:
        from .factories import register

        await register(other, email="other@test.com")
        submission_response = await other.get(
            f"/api/cashout/submissions/{submission_id}"
        )
        analysis_response = await other.get(f"/api/cashout/analyses/{created['id']}")

    assert submission_response.status_code == 403
    assert submission_response.json()["code"] == "FORBIDDEN"
    assert analysis_response.status_code == 403
    assert analysis_response.json()["code"] == "FORBIDDEN"
