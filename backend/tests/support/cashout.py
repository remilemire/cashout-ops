# backend/tests/support/cashout.py

"""Drivers for the cashout submission workflow over the HTTP API.

Each helper asserts the expected status code (with the response body in the
failure message) and returns the parsed payload, so tests read as workflow
steps rather than HTTP plumbing.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from httpx import AsyncClient

from app.document_ai import DocumentAnalysis, DocumentClassification, FieldIssue
from app.features.cashout.data.types import TipoutDepartment
from app.features.cashout.extraction.schemas import ServerSummaryReportData
from app.features.cashout.extraction.types import CashoutDocumentClassification

from .api import csrf_headers
from .documents import SAMPLE_PDF_UPLOAD
from .fakes import FakeAIClient

if TYPE_CHECKING:
    # Type-only: importing the plugin module at runtime would beat pytest's
    # own (assertion-rewriting) import of it and trigger a rewrite warning.
    from .fixtures.outbox import OutboxDrain


_EXTRACTED = ServerSummaryReportData(
    grand_total=Decimal("1234.56"), grand_total_transaction_count=42
)

# The same payload as the API serializes it, for asserting on responses:
# Decimal lands in JSONB as a string.
SERVER_SUMMARY_EXTRACTED = _EXTRACTED.model_dump(mode="json")


def configure_server_summary(ai_client: FakeAIClient) -> None:
    """Point the fake AI at a SERVER_SUMMARY_REPORT classification + extraction."""
    ai_client.classification = DocumentClassification[CashoutDocumentClassification](
        value=CashoutDocumentClassification.SERVER_SUMMARY_REPORT, confidence=0.95
    )
    ai_client.extraction = DocumentAnalysis[ServerSummaryReportData](
        data=_EXTRACTED,
        confidence=0.9,
        issues=[FieldIssue(path="grand_total", message="partially legible")],
    )


def completion_body(
    tipout_departments: Sequence[TipoutDepartment] = (TipoutDepartment.KITCHEN,),
) -> dict[str, Any]:
    """The completion payload, for tests that post to the endpoint directly."""
    return {
        "tipoutDepartments": [department.value for department in tipout_departments]
    }


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
    drain: OutboxDrain,
    file: tuple[str, bytes, str] = SAMPLE_PDF_UPLOAD,
) -> dict[str, Any]:
    """Upload a document and drain the outbox so its extraction runs.

    Returns the upload response — the freshly created EXTRACTING analysis.
    The enqueued extraction has completed by the time this returns (as the
    dispatcher would deliver it in production), so a subsequent poll sees
    the outcome.
    """
    response = await client.post(
        f"/api/cashout/submissions/{submission_id}/documents",
        files={"file": file},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    await drain()
    return response.json()


async def poll_analysis(client: AsyncClient, analysis_id: str) -> dict[str, Any]:
    """One poll is deterministic here: `upload_document` drained the outbox,
    so the extraction outcome is already recorded."""
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


async def unverify_analysis(client: AsyncClient, analysis_id: str) -> dict[str, Any]:
    response = await client.post(
        f"/api/cashout/analyses/{analysis_id}/unverify",
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def complete_submission(
    client: AsyncClient,
    submission_id: str,
    *,
    tipout_departments: Sequence[TipoutDepartment] = (
        TipoutDepartment.KITCHEN,
        TipoutDepartment.BAR,
    ),
) -> dict[str, Any]:
    """Close out a cashout, tipping out to `tipout_departments`.

    The default picks two of the four so the unselected ones stay NULL, which
    is what records that they were not tipped out.
    """
    response = await client.post(
        f"/api/cashout/submissions/{submission_id}/complete",
        json=completion_body(tipout_departments),
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def unsubmit_submission(
    client: AsyncClient, submission_id: str
) -> dict[str, Any]:
    response = await client.post(
        f"/api/cashout/submissions/{submission_id}/unsubmit",
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    return response.json()


__all__ = [
    "SERVER_SUMMARY_EXTRACTED",
    "complete_submission",
    "completion_body",
    "configure_server_summary",
    "create_submission",
    "poll_analysis",
    "unsubmit_submission",
    "unverify_analysis",
    "upload_document",
    "verify_analysis",
]
