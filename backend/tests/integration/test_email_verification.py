# backend/tests/integration/test_email_verification.py

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.email_verification.model import EmailVerification
from app.features.users.model import User
from tests.support.api import csrf_headers
from tests.support.fakes import FakeEmailClient

CASHIER_EMAIL = "cashier@test.com"


async def _latest_verification(db: AsyncSession, *, email: str) -> EmailVerification:
    db.expire_all()
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    verification = (
        await db.execute(
            select(EmailVerification)
            .where(EmailVerification.user_id == user.id)
            .order_by(EmailVerification.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    assert verification is not None, f"no verification row for {email}"
    return verification


# ================================
# ---------- Registration --------
# ================================


async def test_register_emails_code_and_leaves_account_unverified(
    unverified_client: AsyncClient,
    email_client: FakeEmailClient,
    db_session: AsyncSession,
) -> None:
    me = await unverified_client.get("/api/users/me")
    assert me.json()["emailVerifiedAt"] is None

    # The post-commit job emailed a single code and left a matching row.
    assert [email.to for email in email_client.sent] == [CASHIER_EMAIL]
    await _latest_verification(db_session, email=CASHIER_EMAIL)


# ================================
# ------------- Gate -------------
# ================================


async def test_unverified_user_is_blocked_from_guarded_routes(
    unverified_client: AsyncClient,
) -> None:
    # /users/me stays reachable, but a verification-guarded route is blocked.
    assert (await unverified_client.get("/api/users/me")).status_code == 200

    response = await unverified_client.get("/api/cashout/submissions")
    assert response.status_code == 403
    assert response.json()["code"] == "EMAIL_NOT_VERIFIED"


async def test_verifying_unlocks_guarded_routes(
    unverified_client: AsyncClient, email_client: FakeEmailClient
) -> None:
    code = email_client.latest_code(to=CASHIER_EMAIL)
    await unverified_client.post(
        "/api/email-verification/verify",
        json={"code": code},
        headers=csrf_headers(unverified_client),
    )

    response = await unverified_client.get("/api/cashout/submissions")
    assert response.status_code == 200


# ================================
# ------------ Verify ------------
# ================================


async def test_verify_marks_user_verified(
    unverified_client: AsyncClient, email_client: FakeEmailClient
) -> None:
    code = email_client.latest_code(to=CASHIER_EMAIL)

    response = await unverified_client.post(
        "/api/email-verification/verify",
        json={"code": code},
        headers=csrf_headers(unverified_client),
    )

    assert response.status_code == 200, response.text
    assert response.json()["emailVerifiedAt"] is not None
    me = await unverified_client.get("/api/users/me")
    assert me.json()["emailVerifiedAt"] is not None


async def test_verify_wrong_code_is_invalid(unverified_client: AsyncClient) -> None:
    response = await unverified_client.post(
        "/api/email-verification/verify",
        json={"code": "000000"},
        headers=csrf_headers(unverified_client),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VERIFICATION_CODE_INVALID"


async def test_verify_expired_code(
    unverified_client: AsyncClient,
    email_client: FakeEmailClient,
    db_session: AsyncSession,
) -> None:
    code = email_client.latest_code(to=CASHIER_EMAIL)
    verification = await _latest_verification(db_session, email=CASHIER_EMAIL)
    verification.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()

    response = await unverified_client.post(
        "/api/email-verification/verify",
        json={"code": code},
        headers=csrf_headers(unverified_client),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VERIFICATION_CODE_EXPIRED"


async def test_verify_already_verified_conflicts(
    unverified_client: AsyncClient, email_client: FakeEmailClient
) -> None:
    code = email_client.latest_code(to=CASHIER_EMAIL)
    headers = csrf_headers(unverified_client)
    first = await unverified_client.post(
        "/api/email-verification/verify", json={"code": code}, headers=headers
    )
    assert first.status_code == 200

    response = await unverified_client.post(
        "/api/email-verification/verify", json={"code": code}, headers=headers
    )
    assert response.status_code == 409
    assert response.json()["code"] == "VERIFICATION_ALREADY_VERIFIED"


async def test_verify_requires_authentication(client: AsyncClient) -> None:
    # Pass the double-submit CSRF check (matching cookie + header) so the
    # request reaches the auth gate rather than stopping at require_csrf.
    client.cookies.set("csrf_token", "test-token")

    response = await client.post(
        "/api/email-verification/verify",
        json={"code": "123456"},
        headers={"x-csrf-token": "test-token"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


# ================================
# ------------ Resend ------------
# ================================


async def test_resend_issues_a_new_code_and_supersedes_the_old(
    unverified_client: AsyncClient, email_client: FakeEmailClient
) -> None:
    old_code = email_client.latest_code(to=CASHIER_EMAIL)
    headers = csrf_headers(unverified_client)

    resent = await unverified_client.post(
        "/api/email-verification/resend", headers=headers
    )
    assert resent.status_code == 204

    new_code = email_client.latest_code(to=CASHIER_EMAIL)
    assert new_code != old_code

    # The superseded code no longer verifies; the fresh one does.
    stale = await unverified_client.post(
        "/api/email-verification/verify", json={"code": old_code}, headers=headers
    )
    assert stale.status_code == 400
    ok = await unverified_client.post(
        "/api/email-verification/verify", json={"code": new_code}, headers=headers
    )
    assert ok.status_code == 200


async def test_resend_after_verification_conflicts(
    unverified_client: AsyncClient, email_client: FakeEmailClient
) -> None:
    code = email_client.latest_code(to=CASHIER_EMAIL)
    headers = csrf_headers(unverified_client)
    await unverified_client.post(
        "/api/email-verification/verify", json={"code": code}, headers=headers
    )

    response = await unverified_client.post(
        "/api/email-verification/resend", headers=headers
    )
    assert response.status_code == 409
    assert response.json()["code"] == "VERIFICATION_ALREADY_VERIFIED"
