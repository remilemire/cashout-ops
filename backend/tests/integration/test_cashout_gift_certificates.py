"""Gift certificates participate in the same verified completion workflow."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from tests.support.api import csrf_headers
from tests.support.cashout import (
    TOUCHBISTRO_MANUAL_ENTRY_DATA,
    completion_body,
    create_manual_upload,
    create_submission,
    manual_entry_body,
    unverify_analysis,
    verify_analysis,
)


@pytest.mark.parametrize(
    ("count", "total", "expected_code", "expected_ctx"),
    [
        (2, "50.00", None, {}),
        (
            3,
            "50.00",
            "RECONCILE_GIFT_CARD_TRANSACTION_MISMATCH",
            {
                "integratedGiftCardTransactionCount": 3,
                "giftCertificateCount": 2,
            },
        ),
        (
            1,
            "50.00",
            "RECONCILE_GIFT_CARD_TRANSACTION_MISMATCH",
            {
                "integratedGiftCardTransactionCount": 1,
                "giftCertificateCount": 2,
            },
        ),
        (
            2,
            "50.01",
            "RECONCILE_GIFT_CARD_PAYMENT_MISMATCH",
            {
                "integratedGiftCardPaymentTotal": "50.01",
                "giftCertificateTotal": "50.00",
            },
        ),
    ],
)
async def test_completion_cross_checks_verified_gift_certificates(
    cashier_client: AsyncClient,
    admin_client: AsyncClient,
    count: int,
    total: str,
    expected_code: str | None,
    expected_ctx: dict[str, Any],
) -> None:
    submission_id = await create_submission(cashier_client)
    await create_manual_upload(cashier_client, submission_id, body=manual_entry_body())
    await create_manual_upload(
        cashier_client,
        submission_id,
        body=manual_entry_body(
            "touchbistro_report",
            {
                **TOUCHBISTRO_MANUAL_ENTRY_DATA,
                "integrated_gift_card_transaction_count": count,
                "integrated_gift_card_payment_total": total,
            },
        ),
        file=("touchbistro.pdf", b"%PDF-1.4 touchbistro", "application/pdf"),
    )
    for position in range(2):
        certificate = await create_manual_upload(
            cashier_client,
            submission_id,
            body=manual_entry_body("gift_certificate", {"amount": "$20.00"}),
            file=(
                f"certificate-{position}.pdf",
                f"%PDF-1.4 certificate {position}".encode(),
                "application/pdf",
            ),
        )
        assert certificate["classification"] == "gift_certificate"
        assert certificate["schemaName"] == "GiftCertificateData"
        assert certificate["schemaVersion"] == 1
        assert certificate["verifiedDataJson"] == {"amount": "20.00"}
        # Reconciliation must use corrections (25 + 25), not extraction (20 + 20).
        await unverify_analysis(cashier_client, certificate["id"])
        await verify_analysis(
            cashier_client, certificate["id"], {"verifiedData": {"amount": "25.00"}}
        )

    response = await cashier_client.post(
        f"/api/cashout/submissions/{submission_id}/complete",
        json=completion_body(),
        headers=csrf_headers(cashier_client),
    )
    detail = (
        await cashier_client.get(f"/api/cashout/submissions/{submission_id}")
    ).json()
    rows = (await admin_client.get("/api/cashout/data")).json()
    if expected_code is None:
        assert response.status_code == 200, response.text
        assert detail["status"] == "completed"
        assert len(rows) == 1
        assert rows[0]["cardPaymentTotal"] == "1234.56"
        assert rows[0]["cashPaymentTotal"] == "150.00"
    else:
        assert response.status_code == 409, response.text
        assert response.json() == {
            "kind": "CONFLICT",
            "code": expected_code,
            "ctx": expected_ctx,
        }
        assert detail["status"] == "processing"
        assert rows == []
