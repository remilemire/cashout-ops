# backend/tests/support/cashout.py

"""Drivers for the cashout submission workflow over the HTTP API.

Each helper asserts the expected status code (with the response body in the
failure message) and returns the parsed payload, so tests read as workflow
steps rather than HTTP plumbing.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from app.documents import DocumentAnalysis, DocumentClassification, FieldIssue
from app.features.cashout.extraction.schemas import ManualNoteData
from app.features.cashout.types import CashoutDocumentClassification

from .api import csrf_headers
from .documents import SAMPLE_PDF_UPLOAD
from .fakes import FakeAIClient


def configure_manual_note(ai_client: FakeAIClient, note: str = "cash $100") -> None:
    """Point the fake AI at a MANUAL_NOTE classification + extraction result."""
    ai_client.classification = DocumentClassification[CashoutDocumentClassification](
        value=CashoutDocumentClassification.MANUAL_NOTE, confidence=0.95
    )
    ai_client.extraction = DocumentAnalysis[ManualNoteData](
        data=ManualNoteData(note=note),
        confidence=0.9,
        issues=[FieldIssue(path="note", message="partially legible")],
    )


async def create_submission(client: AsyncClient) -> str:
    response = await client.post(
        "/api/cashout/submissions", headers=csrf_headers(client)
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def upload_document(
    client: AsyncClient,
    submission_id: str,
    *,
    file: tuple[str, bytes, str] = SAMPLE_PDF_UPLOAD,
) -> dict[str, Any]:
    """Upload a document; returns the freshly created EXTRACTING analysis."""
    response = await client.post(
        f"/api/cashout/submissions/{submission_id}/documents",
        files={"file": file},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def poll_analysis(client: AsyncClient, analysis_id: str) -> dict[str, Any]:
    """One poll is deterministic here: the ASGI transport awaits the whole
    request lifecycle, including the post-commit extraction job."""
    response = await client.get(f"/api/cashout/analyses/{analysis_id}")
    assert response.status_code == 200, response.text
    return response.json()


async def verify_analysis(
    client: AsyncClient, analysis_id: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    response = await client.post(
        f"/api/cashout/analyses/{analysis_id}/verify",
        json=body or {},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def complete_submission(
    client: AsyncClient, submission_id: str
) -> dict[str, Any]:
    response = await client.post(
        f"/api/cashout/submissions/{submission_id}/complete",
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    return response.json()
