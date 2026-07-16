# backend/tests/test_cashout.py

from __future__ import annotations

from httpx import AsyncClient

from app.documents import DocumentAnalysis, DocumentClassification, FieldIssue
from app.features.cashout.extraction.schemas import ManualNoteData
from app.features.cashout.types import (
    CashoutDocumentType,
    CashoutSubmissionStatus,
    DocumentAnalysisStatus,
)

from .factories import csrf_headers
from .fakes import FakeAIClient

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


async def _create_submission(client: AsyncClient) -> int:
    response = await client.post("/api/cashouts", headers=csrf_headers(client))
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def _upload_pdf(client: AsyncClient, submission_id: int) -> int:
    response = await client.post(
        f"/api/cashouts/{submission_id}/documents",
        files={"file": PDF},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


# ================================
# --------- Happy path -----------
# ================================


async def test_full_cashout_flow(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
) -> None:
    _configure_manual_note(ai_client)

    submission_id = await _create_submission(cashier_client)
    document_id = await _upload_pdf(cashier_client, submission_id)

    # Uploaded documents start UNKNOWN until analyzed.
    detail = (await cashier_client.get(f"/api/cashouts/{submission_id}")).json()
    assert detail["status"] == CashoutSubmissionStatus.PROCESSING.value
    assert detail["documents"][0]["documentType"] == CashoutDocumentType.UNKNOWN.value

    # Extract: the fake AI classifies + extracts.
    extract = await cashier_client.post(
        f"/api/cashouts/documents/{document_id}/extract",
        headers=csrf_headers(cashier_client),
    )
    assert extract.status_code == 200, extract.text
    analysis = extract.json()
    assert analysis["status"] == DocumentAnalysisStatus.SUCCEEDED.value
    assert analysis["classification"] == CashoutDocumentType.MANUAL_NOTE.value
    assert analysis["classificationConfidence"] == 0.95
    assert analysis["extractedDataJson"] == {"note": "cash $100"}
    assert analysis["extractionConfidence"] == 0.9
    assert analysis["issues"] == [{"path": "note", "message": "partially legible"}]

    # Process → UNDER_REVIEW with reconciled data.
    process = await cashier_client.post(
        f"/api/cashouts/{submission_id}/process",
        headers=csrf_headers(cashier_client),
    )
    assert process.status_code == 200, process.text
    assert process.json()["status"] == CashoutSubmissionStatus.UNDER_REVIEW.value

    detail = (await cashier_client.get(f"/api/cashouts/{submission_id}")).json()
    data_id = detail["data"]["id"]
    assert detail["data"]["extractedDataJson"] is not None

    # Review is admin-only.
    review = await admin_client.patch(
        f"/api/cashouts/data/{data_id}",
        json={"reviewedData": {"note": "cash $100 confirmed"}},
        headers=csrf_headers(admin_client),
    )
    assert review.status_code == 200, review.text
    assert review.json()["reviewedDataJson"] == {"note": "cash $100 confirmed"}

    # Complete is admin-only.
    complete = await admin_client.post(
        f"/api/cashouts/{submission_id}/complete",
        headers=csrf_headers(admin_client),
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == CashoutSubmissionStatus.COMPLETED.value


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
        f"/api/cashouts/{submission_id}/documents",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "BAD_REQUEST"


async def test_extract_persists_failure_on_ai_error(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
) -> None:
    from app.integrations.ai import AIAnalysisError, AIErrorCode

    ai_client.error = AIAnalysisError(AIErrorCode.REFUSED, "declined")

    submission_id = await _create_submission(cashier_client)
    document_id = await _upload_pdf(cashier_client, submission_id)

    # The endpoint succeeds; the failure is persisted as a reviewable analysis.
    extract = await cashier_client.post(
        f"/api/cashouts/documents/{document_id}/extract",
        headers=csrf_headers(cashier_client),
    )
    assert extract.status_code == 200, extract.text
    analysis = extract.json()
    assert analysis["status"] == DocumentAnalysisStatus.FAILED.value
    assert analysis["errorCode"] == AIErrorCode.REFUSED.value


async def test_process_without_successful_analysis_marks_failed(
    cashier_client: AsyncClient,
) -> None:
    submission_id = await _create_submission(cashier_client)
    await _upload_pdf(cashier_client, submission_id)  # uploaded but never extracted

    response = await cashier_client.post(
        f"/api/cashouts/{submission_id}/process",
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 200
    assert response.json()["status"] == CashoutSubmissionStatus.FAILED.value


async def test_complete_requires_admin(
    cashier_client: AsyncClient, ai_client: FakeAIClient
) -> None:
    _configure_manual_note(ai_client)
    submission_id = await _create_submission(cashier_client)

    response = await cashier_client.post(
        f"/api/cashouts/{submission_id}/complete",
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_cannot_access_another_users_submission(
    cashier_client: AsyncClient,
    app: object,
) -> None:
    from httpx import ASGITransport

    submission_id = await _create_submission(cashier_client)

    # A second, unrelated cashier.
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as other:
        from .factories import register

        await register(other, email="other@test.com")
        response = await other.get(f"/api/cashouts/{submission_id}")

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
