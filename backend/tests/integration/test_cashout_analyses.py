# backend/tests/integration/test_cashout_analyses.py

from __future__ import annotations

import io
from typing import Any

from httpx import AsyncClient
from PIL import Image

from app.document_ai import DocumentClassificationResponse
from app.features.cashout.analyses.types import DocumentAnalysisStatus
from app.features.cashout.extraction.types import CashoutDocumentClassification
from app.features.cashout.submissions.types import CashoutSubmissionStatus
from app.integrations.ai import AIAnalysisError, AIErrorCode
from app.integrations.ocr import TextDetectionError
from app.lib.documents import DocumentContent, DocumentContentType
from tests.support.api import csrf_headers
from tests.support.cashout import (
    SERVER_SUMMARY_EXTRACTED,
    TOUCHBISTRO_EXTRACTED,
    complete_submission,
    completion_body,
    configure_server_summary,
    create_submission,
    poll_analysis,
    unverify_analysis,
    upload_document,
    upload_reconcilable_documents,
    verify_analysis,
)
from tests.support.documents import (
    SAMPLE_PDF_UPLOAD,
    SAMPLE_PHOTO_BYTES,
    SAMPLE_PHOTO_TEXT_BOXES,
    SAMPLE_PHOTO_UPLOAD,
    SAMPLE_RECEIPT_PDF_UPLOAD,
    SAMPLE_TWO_RECEIPTS_TEXT_BOXES,
    SAMPLE_TWO_RECEIPTS_UPLOAD,
)
from tests.support.fakes import FakeAIClient, FakeDocumentStorage, FakeTextDetector
from tests.support.fixtures.clients import ClientFactory
from tests.support.fixtures.outbox import OutboxDrain


async def test_verify_without_corrections_confirms_extraction(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
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
    submission_id = await create_submission(cashier_client)
    touchbistro, summary = await upload_reconcilable_documents(
        cashier_client, submission_id, ai_client=ai_client, drain=drain_outbox
    )
    await verify_analysis(cashier_client, touchbistro["id"])
    await verify_analysis(cashier_client, summary["id"])

    # Unverify clears the verifier and timestamp but keeps the extraction and
    # the verified data, so the verification form has fields to re-render and
    # any prior corrections to seed them from.
    reopened = await unverify_analysis(cashier_client, touchbistro["id"])
    assert reopened["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value
    assert reopened["verifiedDataJson"] == TOUCHBISTRO_EXTRACTED
    assert reopened["verifiedByUserId"] is None
    assert reopened["verifiedAt"] is None
    assert reopened["extractedDataJson"] == TOUCHBISTRO_EXTRACTED

    # Corrected on a figure the cross-check does not read, so the cashout
    # still reconciles and can be completed.
    reverified = await verify_analysis(
        cashier_client,
        touchbistro["id"],
        {"verifiedData": {**TOUCHBISTRO_EXTRACTED, "card_tip_total": "200.00"}},
    )
    assert reverified["status"] == DocumentAnalysisStatus.VERIFIED.value
    assert reverified["verifiedDataJson"] == {
        **TOUCHBISTRO_EXTRACTED,
        "card_tip_total": "200.00",
    }

    completed = await complete_submission(cashier_client, submission_id)
    assert completed["status"] == CashoutSubmissionStatus.COMPLETED.value


async def test_unverify_preserves_corrections_for_reediting(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # Regression: verify with a correction, then unverify to re-edit — the
    # correction must survive as the seed for the re-edit, not silently
    # revert to the extracted value.
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    analysis = await poll_analysis(cashier_client, created["id"])

    corrected = {**SERVER_SUMMARY_EXTRACTED, "grand_total": "1300.00"}
    await verify_analysis(cashier_client, analysis["id"], {"verifiedData": corrected})

    reopened = await unverify_analysis(cashier_client, analysis["id"])
    assert reopened["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value
    assert reopened["verifiedDataJson"] == corrected
    assert reopened["extractedDataJson"] == SERVER_SUMMARY_EXTRACTED
    assert reopened["verifiedByUserId"] is None
    assert reopened["verifiedAt"] is None

    # A fresh read agrees: the preserved correction is persisted, not just
    # echoed back by the unverify response.
    fetched = await poll_analysis(cashier_client, analysis["id"])
    assert fetched["verifiedDataJson"] == corrected
    assert fetched["extractedDataJson"] == SERVER_SUMMARY_EXTRACTED
    assert fetched["verifiedByUserId"] is None
    assert fetched["verifiedAt"] is None


async def test_retry_extraction_clears_stale_correction(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # A correction preserved through unverify was made against the previous
    # extraction; a re-run must not carry it into the fresh one.
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    analysis = await poll_analysis(cashier_client, created["id"])

    corrected = {**SERVER_SUMMARY_EXTRACTED, "grand_total": "1300.00"}
    await verify_analysis(cashier_client, analysis["id"], {"verifiedData": corrected})
    await unverify_analysis(cashier_client, analysis["id"])

    retry = await cashier_client.post(
        f"/api/cashout/analyses/{created['id']}/extract",
        headers=csrf_headers(cashier_client),
    )
    assert retry.status_code == 200, retry.text
    await drain_outbox()

    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value
    assert analysis["extractedDataJson"] == SERVER_SUMMARY_EXTRACTED
    assert analysis["verifiedDataJson"] is None
    assert analysis["verifiedByUserId"] is None
    assert analysis["verifiedAt"] is None


async def test_unverify_non_verified_analysis_conflicts(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
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
    submission_id = await create_submission(cashier_client)
    touchbistro, summary = await upload_reconcilable_documents(
        cashier_client, submission_id, ai_client=ai_client, drain=drain_outbox
    )
    await verify_analysis(cashier_client, touchbistro["id"])
    await verify_analysis(cashier_client, summary["id"])
    await complete_submission(cashier_client, submission_id)

    # A completed cashout is frozen; it must be unsubmitted first.
    response = await cashier_client.post(
        f"/api/cashout/analyses/{touchbistro['id']}/unverify",
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "SUBMISSION_COMPLETED"
    analysis = await poll_analysis(cashier_client, touchbistro["id"])
    assert analysis["status"] == DocumentAnalysisStatus.VERIFIED.value


async def test_unverify_requires_employee_or_admin(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    make_client: ClientFactory,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
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


async def test_unclassifiable_document_fails_for_retry(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    from app.document_ai import DocumentAIErrorCode
    from app.features.cashout.analyses.messages import analysis_error_message

    ai_client.classification = DocumentClassificationResponse[
        CashoutDocumentClassification
    ](value=None, confidence=0.3)

    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)

    # A document the AI can't place has nothing to verify: the analysis fails
    # like any other extraction failure, so the cashier has to act on it.
    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.FAILED.value
    unclassifiable = DocumentAIErrorCode.UNCLASSIFIABLE_DOCUMENT.value
    assert analysis["errorCode"] == unclassifiable
    assert analysis["errorMessage"] == analysis_error_message(unclassifiable)
    assert analysis["classification"] is None
    assert analysis["classificationConfidence"] is None
    assert analysis["extractedDataJson"] is None
    assert analysis["completedAt"] is not None

    # Verifying it is refused; a retry is the way forward.
    refused = await cashier_client.post(
        f"/api/cashout/analyses/{created['id']}/verify",
        json={},
        headers=csrf_headers(cashier_client),
    )
    assert refused.status_code == 409
    assert refused.json()["code"] == "EXTRACTION_FAILED"

    configure_server_summary(ai_client)
    retried = await cashier_client.post(
        f"/api/cashout/analyses/{created['id']}/extract",
        headers=csrf_headers(cashier_client),
    )
    assert retried.status_code == 200, retried.text
    await drain_outbox()

    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value
    assert (
        analysis["classification"]
        == CashoutDocumentClassification.SERVER_SUMMARY_REPORT.value
    )
    # The failed attempt's outcome does not survive the retry.
    assert analysis["errorCode"] is None
    assert analysis["errorMessage"] is None


async def test_failed_extraction_and_retry(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    from app.document_ai import DocumentAIErrorCode
    from app.features.cashout.analyses.messages import analysis_error_message
    from app.integrations.ai import AIAnalysisError, AIErrorCode

    ai_client.error = AIAnalysisError(
        AIErrorCode.CONTENT_REFUSED, "declined: raw provider text"
    )

    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)

    # The provider failure is recorded on the analysis as FAILED, under the
    # document-AI code the general AI refusal maps to.
    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.FAILED.value
    assert analysis["errorCode"] == DocumentAIErrorCode.DOCUMENT_REJECTED.value
    # The raw provider text must not leak; a safe mapped message is surfaced.
    assert analysis["errorMessage"] == analysis_error_message(
        DocumentAIErrorCode.DOCUMENT_REJECTED.value
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
    configure_server_summary(ai_client)
    retry = await cashier_client.post(
        f"/api/cashout/analyses/{analysis['id']}/extract",
        headers=csrf_headers(cashier_client),
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["status"] == DocumentAnalysisStatus.EXTRACTING.value

    # The retry only enqueued the extraction; run it before polling.
    await drain_outbox()
    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value
    assert analysis["errorCode"] is None


async def test_extraction_with_missing_file_fails_as_missing_document(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    drain_outbox: OutboxDrain,
) -> None:
    from app.document_ai import DocumentAIErrorCode
    from app.features.cashout.analyses.messages import analysis_error_message

    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await cashier_client.post(
        f"/api/cashout/submissions/{submission_id}/documents",
        files={"file": SAMPLE_PDF_UPLOAD},
        headers=csrf_headers(cashier_client),
    )
    assert created.status_code == 201, created.text

    # The stored bytes vanish before the outbox delivers the extraction: the
    # analysis fails under its own code — no AI call, and not the generic
    # "try again" message a retry could never satisfy.
    storage.objects.clear()
    await drain_outbox()

    analysis = await poll_analysis(cashier_client, created.json()["id"])
    assert analysis["status"] == DocumentAnalysisStatus.FAILED.value
    missing = DocumentAIErrorCode.MISSING_DOCUMENT.value
    assert analysis["errorCode"] == missing
    assert analysis["errorMessage"] == analysis_error_message(missing)
    assert ai_client.calls == []


async def test_extraction_skipped_when_submission_cancelled_before_dispatch(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await cashier_client.post(
        f"/api/cashout/submissions/{submission_id}/documents",
        files={"file": SAMPLE_PDF_UPLOAD},
        headers=csrf_headers(cashier_client),
    )
    assert created.status_code == 201, created.text

    # Cancelling a cashout that holds documents soft-deletes it; the enqueued
    # extraction still dispatches, but must not burn an AI call analyzing a
    # cashout nothing can reach anymore.
    cancelled = await cashier_client.delete(
        f"/api/cashout/submissions/{submission_id}",
        headers=csrf_headers(cashier_client),
    )
    assert cancelled.status_code == 204
    await drain_outbox()

    assert ai_client.calls == []
    # Every read path resolves the submission first, so the analysis is gone
    # from the API's point of view.
    polled = await cashier_client.get(f"/api/cashout/analyses/{created.json()['id']}")
    assert polled.status_code == 404
    assert polled.json()["code"] == "SUBMISSION_NOT_FOUND"


async def test_retry_extraction_from_needs_verification(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    # A retry is not reserved for FAILED: an unverified extraction can be
    # re-run too (e.g. the cashier wants a fresh read of the document).
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value

    retry = await cashier_client.post(
        f"/api/cashout/analyses/{created['id']}/extract",
        headers=csrf_headers(cashier_client),
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["status"] == DocumentAnalysisStatus.EXTRACTING.value

    await drain_outbox()
    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == DocumentAnalysisStatus.NEEDS_VERIFICATION.value
    assert analysis["extractedDataJson"] == SERVER_SUMMARY_EXTRACTED


async def test_verify_twice_conflicts(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
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


# ---------- Cropping ----------

_PHOTO_CONTENT = DocumentContent(
    data=SAMPLE_PHOTO_BYTES, content_type=DocumentContentType.PNG
)


def _cropped_key(storage: FakeDocumentStorage) -> str:
    (key,) = [key for key in storage.objects if key.endswith("-crop-1")]
    return key


async def test_extraction_crops_the_document_and_reads_the_crop(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    text_detector: FakeTextDetector,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    text_detector.boxes = SAMPLE_PHOTO_TEXT_BOXES
    submission_id = await create_submission(cashier_client)
    created = await upload_document(
        cashier_client, submission_id, drain=drain_outbox, file=SAMPLE_PHOTO_UPLOAD
    )

    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == "needs_verification"
    assert analysis["croppedContentType"] == "image/png"

    # The original is untouched, and still what the document endpoint serves.
    original = await cashier_client.get(
        f"/api/cashout/documents/{created['cashoutDocumentId']}/content"
    )
    assert original.content == SAMPLE_PHOTO_BYTES

    # The crop is the printed area plus its margin: the boxes span
    # (160, 120)–(480, 350), 320 by 230, so the 3% margin is 10 pixels.
    cropped = await cashier_client.get(f"/api/cashout/analyses/{created['id']}/cropped")
    assert cropped.status_code == 200, cropped.text
    assert cropped.headers["content-type"].startswith("image/png")
    assert cropped.content == storage.objects[_cropped_key(storage)]
    assert Image.open(io.BytesIO(cropped.content)).size == (340, 250)

    # The AI read the crop, not the photo — on the classify and the extract.
    crop_content = DocumentContent(
        data=cropped.content, content_type=DocumentContentType.PNG
    )
    assert [call[0] for call in ai_client.calls] == [crop_content, crop_content]
    assert len(text_detector.calls) == 1


async def test_retry_reads_the_stored_crop_without_detecting_again(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    text_detector: FakeTextDetector,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    text_detector.boxes = SAMPLE_PHOTO_TEXT_BOXES
    submission_id = await create_submission(cashier_client)
    created = await upload_document(
        cashier_client, submission_id, drain=drain_outbox, file=SAMPLE_PHOTO_UPLOAD
    )
    crop_content = DocumentContent(
        data=storage.objects[_cropped_key(storage)],
        content_type=DocumentContentType.PNG,
    )
    ai_client.calls.clear()

    response = await cashier_client.post(
        f"/api/cashout/analyses/{created['id']}/extract",
        headers=csrf_headers(cashier_client),
    )
    assert response.status_code == 200, response.text
    await drain_outbox()

    # The reset kept the crop: the rerun read it, and detection did not run
    # again.
    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["croppedContentType"] == "image/png"
    assert [call[0] for call in ai_client.calls] == [crop_content, crop_content]
    assert len(text_detector.calls) == 1
    assert len(storage.objects) == 2


async def test_extraction_without_detectable_text_reads_the_original(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    drain_outbox: OutboxDrain,
) -> None:
    # The default detector finds nothing: the AI reads the photo whole, and
    # there is no crop to serve.
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(
        cashier_client, submission_id, drain=drain_outbox, file=SAMPLE_PHOTO_UPLOAD
    )

    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == "needs_verification"
    assert analysis["croppedContentType"] is None
    assert len(storage.objects) == 1
    assert ai_client.calls[0][0] == _PHOTO_CONTENT

    cropped = await cashier_client.get(f"/api/cashout/analyses/{created['id']}/cropped")
    assert cropped.status_code == 404
    assert cropped.json()["code"] == "DOCUMENT_NOT_FOUND"


async def test_cropped_document_with_missing_file_is_not_found(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    text_detector: FakeTextDetector,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    text_detector.boxes = SAMPLE_PHOTO_TEXT_BOXES
    submission_id = await create_submission(cashier_client)
    created = await upload_document(
        cashier_client, submission_id, drain=drain_outbox, file=SAMPLE_PHOTO_UPLOAD
    )
    del storage.objects[_cropped_key(storage)]

    response = await cashier_client.get(
        f"/api/cashout/analyses/{created['id']}/cropped"
    )

    assert response.status_code == 404
    assert response.json()["code"] == "DOCUMENT_NOT_FOUND"


async def test_extraction_survives_a_failed_detection(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    text_detector: FakeTextDetector,
    drain_outbox: OutboxDrain,
) -> None:
    # Cropping is best-effort: a detector that cannot run costs the crop,
    # never the extraction.
    configure_server_summary(ai_client)
    text_detector.error = TextDetectionError("model down")
    submission_id = await create_submission(cashier_client)
    created = await upload_document(
        cashier_client, submission_id, drain=drain_outbox, file=SAMPLE_PHOTO_UPLOAD
    )

    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == "needs_verification"
    assert analysis["croppedContentType"] is None
    assert len(storage.objects) == 1
    assert ai_client.calls[0][0] == _PHOTO_CONTENT


async def test_a_failed_extraction_keeps_its_crop(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    text_detector: FakeTextDetector,
    drain_outbox: OutboxDrain,
) -> None:
    # The crop is recorded before the AI is called, so a provider failure
    # leaves it in place for the retry (which then reads it) and the card.
    ai_client.error = AIAnalysisError(AIErrorCode.SERVICE_UNAVAILABLE, "down")
    text_detector.boxes = SAMPLE_PHOTO_TEXT_BOXES
    submission_id = await create_submission(cashier_client)
    created = await upload_document(
        cashier_client, submission_id, drain=drain_outbox, file=SAMPLE_PHOTO_UPLOAD
    )

    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == "failed"
    assert analysis["errorCode"] == "service_unavailable"
    assert analysis["croppedContentType"] == "image/png"
    assert len(storage.objects) == 2


# ---------- Several documents in one upload ----------


async def _document_analyses(
    client: AsyncClient, submission_id: str
) -> list[dict[str, Any]]:
    detail = (await client.get(f"/api/cashout/submissions/{submission_id}")).json()
    (document,) = detail["documents"]
    return document["analyses"]


async def _crop(client: AsyncClient, analysis_id: str) -> bytes:
    response = await client.get(f"/api/cashout/analyses/{analysis_id}/cropped")
    assert response.status_code == 200, response.text
    return response.content


async def test_an_upload_holding_two_documents_gets_an_analysis_each(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    text_detector: FakeTextDetector,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    text_detector.boxes = SAMPLE_TWO_RECEIPTS_TEXT_BOXES
    submission_id = await create_submission(cashier_client)
    created = await upload_document(
        cashier_client,
        submission_id,
        drain=drain_outbox,
        file=SAMPLE_TWO_RECEIPTS_UPLOAD,
    )

    # The upload's own analysis took the first receipt; the job added a
    # sibling for the second and queued its extraction, which the drain ran.
    analyses = await _document_analyses(cashier_client, submission_id)
    assert [analysis["position"] for analysis in analyses] == [1, 2]
    assert analyses[0]["id"] == created["id"]
    for analysis in analyses:
        assert analysis["status"] == "needs_verification"
        assert analysis["croppedContentType"] == "image/png"

    # Each read its own crop — the left receipt first — cut from the one
    # original, which is stored once.
    left = DocumentContent(
        data=await _crop(cashier_client, analyses[0]["id"]),
        content_type=DocumentContentType.PNG,
    )
    right = DocumentContent(
        data=await _crop(cashier_client, analyses[1]["id"]),
        content_type=DocumentContentType.PNG,
    )
    assert left != right
    assert len(storage.objects) == 3
    assert [call[0] for call in ai_client.calls] == [left, left, right, right]
    # Detection ran once, over the whole upload.
    assert len(text_detector.calls) == 1


async def test_a_pdf_gets_an_analysis_per_page(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    text_detector: FakeTextDetector,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    text_detector.boxes = SAMPLE_PHOTO_TEXT_BOXES
    submission_id = await create_submission(cashier_client)
    await upload_document(
        cashier_client,
        submission_id,
        drain=drain_outbox,
        file=SAMPLE_RECEIPT_PDF_UPLOAD,
    )

    analyses = await _document_analyses(cashier_client, submission_id)
    assert [analysis["position"] for analysis in analyses] == [1, 2]
    # A page's crop is a render, stored as PNG whatever the upload was.
    for analysis in analyses:
        assert analysis["status"] == "needs_verification"
        assert analysis["croppedContentType"] == "image/png"
    cropped = await cashier_client.get(
        f"/api/cashout/analyses/{analyses[1]['id']}/cropped"
    )
    assert cropped.headers["content-type"].startswith("image/png")
    # One detection per page.
    assert len(text_detector.calls) == 2
    assert len(storage.objects) == 3


async def test_restarting_a_document_detects_its_documents_again(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    text_detector: FakeTextDetector,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    text_detector.boxes = SAMPLE_TWO_RECEIPTS_TEXT_BOXES
    submission_id = await create_submission(cashier_client)
    created = await upload_document(
        cashier_client,
        submission_id,
        drain=drain_outbox,
        file=SAMPLE_TWO_RECEIPTS_UPLOAD,
    )
    before = await _document_analyses(cashier_client, submission_id)
    assert len(before) == 2

    # Starting over: every analysis and its crop go, one fresh analysis
    # comes back, and the job finds both documents again.
    restarted = await cashier_client.post(
        f"/api/cashout/documents/{created['cashoutDocumentId']}/extract",
        headers=csrf_headers(cashier_client),
    )
    assert restarted.status_code == 200, restarted.text
    fresh = restarted.json()
    assert fresh["status"] == "extracting"
    assert fresh["position"] == 1
    assert fresh["croppedContentType"] is None
    assert fresh["id"] not in {analysis["id"] for analysis in before}
    await drain_outbox()

    after = await _document_analyses(cashier_client, submission_id)
    assert [analysis["position"] for analysis in after] == [1, 2]
    assert after[0]["id"] == fresh["id"]
    assert {analysis["id"] for analysis in after}.isdisjoint(
        {analysis["id"] for analysis in before}
    )
    assert len(text_detector.calls) == 2
    # The crops were replaced in place, not piled up.
    assert len(storage.objects) == 3


async def test_restart_is_refused_while_an_analysis_is_verified(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    text_detector: FakeTextDetector,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    text_detector.boxes = SAMPLE_TWO_RECEIPTS_TEXT_BOXES
    submission_id = await create_submission(cashier_client)
    created = await upload_document(
        cashier_client,
        submission_id,
        drain=drain_outbox,
        file=SAMPLE_TWO_RECEIPTS_UPLOAD,
    )
    first, second = await _document_analyses(cashier_client, submission_id)
    await verify_analysis(cashier_client, second["id"])

    # A verified sibling settles the document: starting over would discard
    # the cashier's confirmation.
    response = await cashier_client.post(
        f"/api/cashout/documents/{created['cashoutDocumentId']}/extract",
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ANALYSIS_VERIFIED"
    # Retrying just the unverified one is still fine, and keeps its crop.
    retry = await cashier_client.post(
        f"/api/cashout/analyses/{first['id']}/extract",
        headers=csrf_headers(cashier_client),
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["croppedContentType"] == "image/png"


async def test_completion_requires_every_analysis_verified(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    text_detector: FakeTextDetector,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    text_detector.boxes = SAMPLE_TWO_RECEIPTS_TEXT_BOXES
    submission_id = await create_submission(cashier_client)
    await upload_document(
        cashier_client,
        submission_id,
        drain=drain_outbox,
        file=SAMPLE_TWO_RECEIPTS_UPLOAD,
    )
    first, _ = await _document_analyses(cashier_client, submission_id)
    await verify_analysis(cashier_client, first["id"])

    # One of the two documents in the upload is still unverified.
    response = await cashier_client.post(
        f"/api/cashout/submissions/{submission_id}/complete",
        json=completion_body(),
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "SUBMISSION_UNVERIFIED"
