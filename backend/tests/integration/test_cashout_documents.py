# backend/tests/integration/test_cashout_documents.py

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient
from PIL import Image

from app.core.config import settings
from app.integrations.ocr import TextDetectionError
from app.lib.documents import DocumentContent, DocumentContentType
from tests.support.api import csrf_headers
from tests.support.cashout import (
    complete_submission,
    configure_server_summary,
    create_submission,
    manual_entry_body,
    poll_analysis,
    upload_document,
    upload_manual_document,
    upload_reconcilable_documents,
    verify_analysis,
)
from tests.support.documents import (
    SAMPLE_PDF_BYTES,
    SAMPLE_PHOTO_BYTES,
    SAMPLE_PHOTO_TEXT_BOXES,
    SAMPLE_PHOTO_UPLOAD,
)
from tests.support.fakes import FakeAIClient, FakeDocumentStorage, FakeTextDetector
from tests.support.fixtures.clients import ClientFactory
from tests.support.fixtures.outbox import OutboxDrain

_PHOTO_CONTENT = DocumentContent(
    data=SAMPLE_PHOTO_BYTES, content_type=DocumentContentType.PNG
)


def _cropped_key(storage: FakeDocumentStorage) -> str:
    (key,) = [key for key in storage.objects if key.endswith("-cropped")]
    return key


async def test_document_content_served_to_owner_and_admin(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    url = f"/api/cashout/documents/{created['cashoutDocumentId']}/content"

    owner = await cashier_client.get(url)
    assert owner.status_code == 200
    assert owner.headers["content-type"].startswith("application/pdf")
    assert owner.content == SAMPLE_PDF_BYTES

    admin = await admin_client.get(url)
    assert admin.status_code == 200


async def test_document_content_with_missing_file_is_not_found(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    drain_outbox: OutboxDrain,
) -> None:
    # The row can outlive its stored bytes (the backing store lost them). To
    # the viewer the document is gone: a 404 under the shared contract, not an
    # uncaught storage error surfacing as a 500.
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    storage.objects.clear()

    response = await cashier_client.get(
        f"/api/cashout/documents/{created['cashoutDocumentId']}/content"
    )

    assert response.status_code == 404
    assert response.json()["code"] == "DOCUMENT_NOT_FOUND"


async def test_delete_document_from_processing_submission(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
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
    submission_id = await create_submission(cashier_client)
    touchbistro, summary = await upload_reconcilable_documents(
        cashier_client, submission_id, ai_client=ai_client, drain=drain_outbox
    )
    await verify_analysis(cashier_client, touchbistro["id"])
    await verify_analysis(cashier_client, summary["id"])
    await complete_submission(cashier_client, submission_id)

    response = await cashier_client.delete(
        f"/api/cashout/documents/{touchbistro['cashoutDocumentId']}",
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "SUBMISSION_COMPLETED"
    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    assert len(detail["documents"]) == 2
    assert storage.objects


async def test_delete_document_requires_employee_or_admin(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    make_client: ClientFactory,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
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
    assert response.json()["ctx"] == {"maxSizeMb": 1}
    # Rejected before its bytes were written to storage.
    assert len(storage.objects) == stored_before


async def test_upload_rejects_duplicate_document(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    drain_outbox: OutboxDrain,
) -> None:
    configure_server_summary(ai_client)
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

    # The same file is still allowed in a *different* submission (another
    # day's — one live cashout per business day).
    other_submission_id = await create_submission(
        cashier_client, business_date="2026-08-28"
    )
    await upload_document(cashier_client, other_submission_id, drain=drain_outbox)


# ---------- Cropping ----------


async def test_upload_stores_a_crop_and_extracts_from_it(
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
    document_id = created["cashoutDocumentId"]

    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    (document,) = detail["documents"]
    assert document["croppedContentType"] == "image/png"

    # The original is untouched, and still what /content serves.
    original = await cashier_client.get(f"/api/cashout/documents/{document_id}/content")
    assert original.content == SAMPLE_PHOTO_BYTES

    # The crop is the printed area plus its margin: the boxes span
    # (160, 120)–(480, 350), 320 by 230, so the 3% margin is 10 pixels.
    cropped = await cashier_client.get(f"/api/cashout/documents/{document_id}/cropped")
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


async def test_retrying_the_extraction_reuses_the_stored_crop(
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
        f"/api/cashout/documents/{created['cashoutDocumentId']}/extract",
        headers=csrf_headers(cashier_client),
    )
    assert response.status_code == 200, response.text
    await drain_outbox()

    # The rerun read the crop stored at upload; detection did not run again.
    assert [call[0] for call in ai_client.calls] == [crop_content, crop_content]
    assert len(text_detector.calls) == 1


async def test_upload_without_detectable_text_stays_uncropped(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    drain_outbox: OutboxDrain,
) -> None:
    # The default detector finds nothing: the photo is stored as-is, the AI
    # reads it as-is, and there is no crop to serve.
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(
        cashier_client, submission_id, drain=drain_outbox, file=SAMPLE_PHOTO_UPLOAD
    )
    document_id = created["cashoutDocumentId"]

    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    (document,) = detail["documents"]
    assert document["croppedContentType"] is None
    assert len(storage.objects) == 1
    assert ai_client.calls[0][0] == _PHOTO_CONTENT

    cropped = await cashier_client.get(f"/api/cashout/documents/{document_id}/cropped")
    assert cropped.status_code == 404
    assert cropped.json()["code"] == "DOCUMENT_NOT_FOUND"


async def test_cropped_content_with_missing_file_is_not_found(
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
        f"/api/cashout/documents/{created['cashoutDocumentId']}/cropped"
    )

    assert response.status_code == 404
    assert response.json()["code"] == "DOCUMENT_NOT_FOUND"


async def test_manual_upload_is_cropped_too(
    cashier_client: AsyncClient,
    storage: FakeDocumentStorage,
    text_detector: FakeTextDetector,
) -> None:
    # No AI runs for a manual entry, but the document previews like any
    # other: the crop is made at upload, not by the extraction.
    text_detector.boxes = SAMPLE_PHOTO_TEXT_BOXES
    submission_id = await create_submission(cashier_client)

    await upload_manual_document(
        cashier_client,
        submission_id,
        body=manual_entry_body(),
        file=SAMPLE_PHOTO_UPLOAD,
    )

    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    (document,) = detail["documents"]
    assert document["croppedContentType"] == "image/png"
    assert len(storage.objects) == 2


async def test_upload_survives_a_failed_detection(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
    text_detector: FakeTextDetector,
    drain_outbox: OutboxDrain,
) -> None:
    # Cropping is best-effort: a detector that cannot run costs the crop,
    # never the upload or its extraction.
    configure_server_summary(ai_client)
    text_detector.error = TextDetectionError("model down")
    submission_id = await create_submission(cashier_client)

    created = await upload_document(
        cashier_client, submission_id, drain=drain_outbox, file=SAMPLE_PHOTO_UPLOAD
    )

    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    (document,) = detail["documents"]
    assert document["croppedContentType"] is None
    assert len(storage.objects) == 1
    analysis = await poll_analysis(cashier_client, created["id"])
    assert analysis["status"] == "needs_verification"
    assert ai_client.calls[0][0] == _PHOTO_CONTENT


async def test_delete_document_removes_the_crop_too(
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
    assert len(storage.objects) == 2

    response = await cashier_client.delete(
        f"/api/cashout/documents/{created['cashoutDocumentId']}",
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 204
    assert storage.objects == {}
