# backend/tests/integration/test_cashout_documents.py

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.support.api import csrf_headers
from tests.support.cashout import (
    complete_submission,
    configure_server_summary,
    create_submission,
    upload_document,
    verify_analysis,
)
from tests.support.documents import SAMPLE_PDF_BYTES
from tests.support.fakes import FakeAIClient, FakeDocumentStorage
from tests.support.fixtures.clients import ClientFactory
from tests.support.fixtures.outbox import OutboxDrain


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
    configure_server_summary(ai_client)
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

    # The same file is still allowed in a *different* submission.
    other_submission_id = await create_submission(cashier_client)
    await upload_document(cashier_client, other_submission_id, drain=drain_outbox)
