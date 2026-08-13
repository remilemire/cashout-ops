# backend/app/features/auth/external_identities/repository.py

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.oauth.issuers import OAuthIssuer

from .model import ExternalIdentity


async def find_by_issuer_subject(
    db: AsyncSession, *, issuer: OAuthIssuer, subject: str
) -> ExternalIdentity | None:
    stmt = select(ExternalIdentity).where(
        ExternalIdentity.issuer == issuer,
        ExternalIdentity.subject == subject,
    )

    return (await db.execute(stmt)).scalar_one_or_none()


async def add(db: AsyncSession, identity: ExternalIdentity) -> bool:
    """Stage the link and flush, reporting whether the insert took.

    Flushing here surfaces unique/FK violations at the insert rather than at
    commit. The SAVEPOINT is what makes that survivable: a concurrent first
    sign-in that linked the same identity moments earlier violates one of the
    unique indexes, and without the savepoint that failed flush would poison
    the whole request transaction — leaving the caller a session it can no
    longer commit even though it handled the loss.
    """
    try:
        async with db.begin_nested():
            db.add(identity)
            await db.flush()
    except IntegrityError:
        return False

    return True


__all__ = ["find_by_issuer_subject", "add"]
