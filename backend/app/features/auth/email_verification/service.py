# backend/app/features/auth/email_verification/service.py

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from functools import partial
from importlib.resources import files
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.dependencies.background import PostCommitTasks
from app.errors import AppError
from app.features.users.model import User
from app.integrations.email import EmailClient
from app.security.crypto import hash_secret_token

from .model import EmailVerification

logger = logging.getLogger("app.email")

# Six numeric digits (leading zeros allowed).
_CODE_DIGITS = 6
_SUBJECT = "Your Whiskey District verification code"
# The email body template ships with this feature; render it with the code.
_TEMPLATE = (
    files("app.features.auth.email_verification")
    .joinpath("templates", "verify_email.html")
    .read_text(encoding="utf-8")
)


def _generate_code() -> str:
    return f"{secrets.randbelow(10**_CODE_DIGITS):0{_CODE_DIGITS}d}"


def _render_html(*, code: str, ttl_minutes: int) -> str:
    return _TEMPLATE.replace("{{code}}", code).replace(
        "{{ttl_minutes}}", str(ttl_minutes)
    )


async def send_new_code(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    email_client: EmailClient,
    user_id: UUID,
) -> None:
    """Post-commit job: issue a fresh code and email it via the email client.

    Runs after the triggering request (register/resend) has committed, so it
    owns its session and transaction. Supersedes any outstanding code. Delivery
    is best-effort — a send failure is logged, not raised (the user can resend).
    """
    ttl_minutes = settings.EMAIL_VERIFICATION_CODE_TTL_MINUTES

    async with sessionmaker() as db:
        user = await User.find_by_id(db, user_id)
        if user is None or user.email_verified_at is not None:
            return

        # user_id is unique: clear any existing row before issuing the new one.
        await db.execute(
            delete(EmailVerification).where(EmailVerification.user_id == user.id)
        )
        code = _generate_code()
        db.add(
            EmailVerification(
                user_id=user.id,
                code_hash=hash_secret_token(code),
                expires_at=datetime.now(UTC) + timedelta(minutes=ttl_minutes),
            )
        )
        await db.commit()
        recipient = user.email

    try:
        await email_client.send(
            to=recipient,
            subject=_SUBJECT,
            html=_render_html(code=code, ttl_minutes=ttl_minutes),
        )
    except Exception:
        logger.exception("Failed to send verification email to %s", recipient)


async def resend(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    post_commit: PostCommitTasks,
    email_client: EmailClient,
    user: User,
) -> None:
    """Queue a fresh verification code for the current user.

    Rejects an already-verified user. Otherwise queues the same post-commit
    job `register` uses, so the code is issued and the email sent only once
    the request transaction commits.
    """
    if user.email_verified_at is not None:
        raise AppError("VERIFICATION_ALREADY_VERIFIED")

    post_commit.add(
        partial(send_new_code, sessionmaker, email_client=email_client, user_id=user.id)
    )


async def verify_email(db: AsyncSession, *, user: User, code: str) -> User:
    """Confirm a submitted code, marking the user verified on success."""
    if user.email_verified_at is not None:
        raise AppError("VERIFICATION_ALREADY_VERIFIED")

    verification = (
        await db.execute(
            select(EmailVerification)
            .where(
                EmailVerification.user_id == user.id,
                EmailVerification.consumed_at.is_(None),
            )
            .order_by(EmailVerification.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if verification is None or verification.expires_at <= datetime.now(UTC):
        raise AppError("VERIFICATION_CODE_EXPIRED")

    if not secrets.compare_digest(verification.code_hash, hash_secret_token(code)):
        raise AppError("VERIFICATION_CODE_INVALID")

    now = datetime.now(UTC)
    verification.consumed_at = now
    user.email_verified_at = now
    return user


__all__ = ["resend", "send_new_code", "verify_email"]
