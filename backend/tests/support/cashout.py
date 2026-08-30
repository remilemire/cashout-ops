# backend/tests/support/cashout.py

"""Drivers for the cashout submission workflow over the HTTP API.

Each helper asserts the expected status code (with the response body in the
failure message) and returns the parsed payload, so tests read as workflow
steps rather than HTTP plumbing.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from httpx import AsyncClient

from app.document_ai import (
    DocumentAnalysis,
    DocumentClassificationResponse,
    FieldIssue,
)
from app.features.cashout.data.types import TipoutDepartment
from app.features.cashout.extraction.schemas import (
    ServerSummaryReportData,
    TouchBistroReportData,
)
from app.features.cashout.extraction.types import CashoutDocumentClassification

from .api import csrf_headers
from .documents import SAMPLE_PDF_UPLOAD, SAMPLE_PNG_UPLOAD
from .fakes import FakeAIClient

if TYPE_CHECKING:
    # Type-only: importing the plugin module at runtime would beat pytest's
    # own (assertion-rewriting) import of it and trigger a rewrite warning.
    from .fixtures.outbox import OutboxDrain


_EXTRACTED = ServerSummaryReportData(
    grand_total=Decimal("1234.56"), grand_total_transaction_count=42
)

# The TouchBistro report the cross-check is written against: its card
# payments and card orders are exactly what the one server summary above
# reports, so the pair reconciles. Every source figure on a cashout data row
# comes from here.
_TOUCHBISTRO_EXTRACTED = TouchBistroReportData(
    food_net_sales=Decimal("800.00"),
    drink_net_sales=Decimal("400.00"),
    total_net_sales=Decimal("1200.00"),
    card_transaction_count=42,
    cash_payment_total=Decimal("150.00"),
    card_payment_total=Decimal("1234.56"),
    card_tip_total=Decimal("180.00"),
)

# The same payloads as the API serializes them, for asserting on responses:
# Decimal lands in JSONB as a string.
SERVER_SUMMARY_EXTRACTED = _EXTRACTED.model_dump(mode="json")
TOUCHBISTRO_EXTRACTED = _TOUCHBISTRO_EXTRACTED.model_dump(mode="json")

# Server-summary values as a user would type them: messy strings the schema
# must coerce (Money strips the comma; the count string parses to an int).
# Validated, they dump to exactly SERVER_SUMMARY_EXTRACTED.
MANUAL_ENTRY_DATA = {
    "grand_total": "1,234.56",
    "grand_total_transaction_count": "42",
}

# The same for the TouchBistro report: validated, these dump to exactly
# TOUCHBISTRO_EXTRACTED, so a hand-typed pair reconciles like an extracted one.
TOUCHBISTRO_MANUAL_ENTRY_DATA = {
    "food_net_sales": "800.00",
    "drink_net_sales": "400.00",
    "total_net_sales": "1,200.00",
    "card_transaction_count": "42",
    "cash_payment_total": "150.00",
    "card_payment_total": "$1,234.56",
    "card_tip_total": "180.00",
}


def manual_entry_body(
    classification: str = "server_summary_report",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The manual-entry payload, for either manual endpoint."""
    return {"classification": classification, "data": data or dict(MANUAL_ENTRY_DATA)}


def touchbistro_manual_entry_body() -> dict[str, Any]:
    """The manual-entry payload for the TouchBistro half of a cashout."""
    return manual_entry_body("touchbistro_report", dict(TOUCHBISTRO_MANUAL_ENTRY_DATA))


def configure_server_summary(ai_client: FakeAIClient) -> None:
    """Point the fake AI at a SERVER_SUMMARY_REPORT classification + extraction."""
    ai_client.classification = DocumentClassificationResponse[
        CashoutDocumentClassification
    ](value=CashoutDocumentClassification.SERVER_SUMMARY_REPORT, confidence=0.95)
    ai_client.extraction = DocumentAnalysis[ServerSummaryReportData](
        data=_EXTRACTED,
        confidence=0.9,
        issues=[FieldIssue(path="grand_total", message="partially legible")],
    )


def configure_touchbistro(ai_client: FakeAIClient) -> None:
    """Point the fake AI at a TOUCHBISTRO_REPORT classification + extraction."""
    ai_client.classification = DocumentClassificationResponse[
        CashoutDocumentClassification
    ](value=CashoutDocumentClassification.TOUCHBISTRO_REPORT, confidence=0.95)
    ai_client.extraction = DocumentAnalysis[TouchBistroReportData](
        data=_TOUCHBISTRO_EXTRACTED, confidence=0.9, issues=[]
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


async def upload_manual_document(
    client: AsyncClient,
    submission_id: str,
    *,
    body: dict[str, Any],
    file: tuple[str, bytes, str] = SAMPLE_PDF_UPLOAD,
) -> dict[str, Any]:
    """Upload a document with manually entered details.

    Returns the created analysis — already VERIFIED: nothing was enqueued, so
    there is no outbox to drain and nothing to poll.
    """
    response = await client.post(
        f"/api/cashout/submissions/{submission_id}/documents/manual",
        files={"file": file},
        data={"payload": json.dumps(body)},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def enter_manual_document(
    client: AsyncClient, document_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    response = await client.post(
        f"/api/cashout/documents/{document_id}/manual",
        json=body,
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
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


async def upload_reconcilable_documents(
    client: AsyncClient,
    submission_id: str,
    *,
    ai_client: FakeAIClient,
    drain: OutboxDrain,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Upload a cashout that reconciles, and return its two analyses.

    The TouchBistro report every source figure comes from, plus the one
    server summary whose grand totals match its card payments and card
    orders — the smallest set completion accepts. Distinct files: the same
    bytes twice in one submission are rejected as a duplicate.
    """
    configure_touchbistro(ai_client)
    touchbistro = await upload_document(client, submission_id, drain=drain)
    configure_server_summary(ai_client)
    summary = await upload_document(
        client, submission_id, drain=drain, file=SAMPLE_PNG_UPLOAD
    )
    return touchbistro, summary


async def prepare_completable_submission(
    client: AsyncClient, *, ai_client: FakeAIClient, drain: OutboxDrain
) -> str:
    """A fresh submission holding a verified, reconcilable pair of documents."""
    submission_id = await create_submission(client)
    touchbistro, summary = await upload_reconcilable_documents(
        client, submission_id, ai_client=ai_client, drain=drain
    )
    await verify_analysis(client, touchbistro["id"])
    await verify_analysis(client, summary["id"])
    return submission_id


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
    "MANUAL_ENTRY_DATA",
    "SERVER_SUMMARY_EXTRACTED",
    "TOUCHBISTRO_MANUAL_ENTRY_DATA",
    "TOUCHBISTRO_EXTRACTED",
    "complete_submission",
    "completion_body",
    "configure_server_summary",
    "configure_touchbistro",
    "create_submission",
    "enter_manual_document",
    "manual_entry_body",
    "poll_analysis",
    "prepare_completable_submission",
    "touchbistro_manual_entry_body",
    "unsubmit_submission",
    "unverify_analysis",
    "upload_document",
    "upload_manual_document",
    "upload_reconcilable_documents",
    "verify_analysis",
]
